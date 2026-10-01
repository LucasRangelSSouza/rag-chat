"""Postgres store for a text base: full-text search plus optional vector search (pgvector).

Reads a table that has a generated `fts tsvector` column and the record columns the answer needs. When an
embedding service and an embeddings table are configured, retrieval is hybrid: the text ranking and the
vector ranking are fused with reciprocal rank fusion. The connection role is read-only with a statement
timeout; queries use bound parameters only.
"""
from __future__ import annotations

import json
import re
import threading
import urllib.request
from typing import Any

from .index import _groups

RECORD_COLUMNS = ["numero_controle_pncp", "ano_compra", "data_publicacao_pncp", "data_encerramento_proposta", "sigla_uf",
                  "nome_municipio", "orgao_razao_social", "modalidade_nome", "situacao_compra_nome", "objeto_compra",
                  "categoria_area", "valor_total_estimado"]
_SAFE = re.compile(r"^[a-z0-9]+$")
_ID = re.compile(r"^(\d{14})-\d-(\d+)/(\d{4})$")


def tsquery(groups: list[list[str]]) -> str:
    """AND of OR-groups, each lexeme quoted: ('escola' | 'escolar') & ('merenda')."""
    parts = []
    for group in groups:
        alts = [a for a in group if _SAFE.match(a)]
        if not alts:
            continue
        parts.append("(" + " | ".join(f"'{a}'" for a in alts) + ")")
    return " & ".join(parts)


def portal_link(record_id: str | None) -> str | None:
    match = _ID.match(record_id or "")
    return f"https://pncp.gov.br/app/editais/{match.group(1)}/{match.group(3)}/{int(match.group(2))}" if match else None


def fuse(rankings: list[list[str]], k: int = 60) -> list[str]:
    """Reciprocal rank fusion over ordered id lists."""
    score: dict[str, float] = {}
    for ranking in rankings:
        for position, key in enumerate(ranking):
            score[key] = score.get(key, 0.0) + 1.0 / (k + position + 1)
    return [key for key, _ in sorted(score.items(), key=lambda item: -item[1])]


class PgStore:
    is_pg = True

    def __init__(self, dsn: str, table: str = "pncp.obt_pncp_editais_semantico", cutoff: str = "2026-07-31",
                 embed_url: str | None = None, vectors_table: str = "pncp.editais_embeddings") -> None:
        import psycopg  # imported here so the SQLite path needs no Postgres driver

        for name in (table, vectors_table):
            if not re.match(r"^[a-z_]+\.[a-z_0-9]+$", name):
                raise ValueError("invalid table name")
        self._psycopg, self.dsn, self.table, self.cutoff = psycopg, dsn, table, cutoff
        self.embed_url, self.vectors_table = embed_url, vectors_table
        self._lock = threading.Lock()
        self._conn: Any = None
        self._count: int | None = None

    def _connection(self):
        if self._conn is None or self._conn.closed:
            self._conn = self._psycopg.connect(self.dsn, autocommit=True, connect_timeout=5, options="-c hnsw.ef_search=60 -c ivfflat.probes=12")
        return self._conn

    def _run(self, sql: str, params: tuple = ()):
        with self._lock:
            try:
                with self._connection().cursor() as cur:
                    cur.execute(sql, params)
                    columns = [d.name for d in cur.description] if cur.description else []
                    return columns, cur.fetchall() if cur.description else []
            except self._psycopg.OperationalError:
                self._conn = None  # reconnect on the next call
                raise

    def meta(self) -> dict:
        if self._count is None:
            _, rows = self._run("SELECT reltuples::bigint FROM pg_class WHERE oid = %s::regclass", (self.table,))
            self._count = int(rows[0][0]) if rows else 0
        return {"data_cutoff": self.cutoff, "table_count": 1, "record_count": self._count}

    def embed(self, text: str) -> list[float] | None:
        if not self.embed_url:
            return None
        try:
            request = urllib.request.Request(self.embed_url.rstrip("/") + "/embed", data=json.dumps({"text": text[:1000], "kind": "query"}).encode(),
                                             headers={"content-type": "application/json"})
            with urllib.request.urlopen(request, timeout=25) as response:
                vector = json.load(response)["embedding"]
            return vector if isinstance(vector, list) and len(vector) == 768 else None
        except Exception:
            return None

    def _text_ids(self, question: str, limit: int) -> tuple[int, list[str]]:
        query = tsquery(_groups(question))
        if not query:
            return 0, []
        _, counted = self._run(
            f"SELECT count(*) FROM (SELECT 1 FROM {self.table} WHERE fts @@ to_tsquery('portuguese', %s) LIMIT 100000) m", (query,))
        total = int(counted[0][0])
        if not total:
            return 0, []
        _, rows = self._run(
            f"WITH m AS (SELECT numero_controle_pncp, fts FROM {self.table} WHERE fts @@ to_tsquery('portuguese', %s) LIMIT 20000) "
            f"SELECT numero_controle_pncp FROM m ORDER BY ts_rank_cd(fts, to_tsquery('portuguese', %s)) DESC LIMIT %s",
            (query, query, limit))
        return total, [r[0] for r in rows]

    def _vector_ids(self, question: str, limit: int) -> list[str]:
        vector = self.embed(question)
        if vector is None:
            return []
        literal = "[" + ",".join(f"{v:.6f}" for v in vector) + "]"
        try:
            _, rows = self._run(
                f"SELECT numero_controle_pncp FROM {self.vectors_table} ORDER BY embedding <=> %s::halfvec LIMIT %s", (literal, limit))
        except Exception:
            return []
        return [r[0] for r in rows]

    def _records(self, ids: list[str]) -> dict[str, dict]:
        if not ids:
            return {}
        cols = ", ".join(RECORD_COLUMNS)
        names, rows = self._run(f"SELECT {cols} FROM {self.table} WHERE numero_controle_pncp = ANY(%s)", (ids,))
        return {row[0]: {n: (None if v is None else str(v)) for n, v in zip(names, row)} for row in rows}

    def search(self, question: str, k: int = 5) -> tuple[int, list[dict]]:
        """Hybrid retrieval for the chat: text ranking fused with vector ranking when embeddings are available."""
        total, text_ids = self._text_ids(question, 25)
        vector_ids = self._vector_ids(question, 25)
        ordered = fuse([r for r in (text_ids, vector_ids) if r])[:k]
        records = self._records(ordered)
        hits = [records[i] for i in ordered if i in records]
        return (total or len(hits)), hits

    def explore(self, mode: str, question: str, limit: int = 20) -> dict:
        """Search-page API: mode is text, vector, or hybrid. Returns rows ready to render."""
        total, text_ids, vector_ids = 0, [], []
        if mode in ("text", "hybrid"):
            total, text_ids = self._text_ids(question, 40)
        if mode in ("vector", "hybrid"):
            vector_ids = self._vector_ids(question, 40)
        if mode == "text":
            ordered = text_ids
        elif mode == "vector":
            ordered = vector_ids
        else:
            ordered = fuse([r for r in (text_ids, vector_ids) if r])
        ordered = ordered[:limit]
        records = self._records(ordered)
        results = []
        for position, key in enumerate(ordered):
            row = records.get(key)
            if not row:
                continue
            results.append({"id": key, "org": row.get("orgao_razao_social"), "municipality": row.get("nome_municipio"),
                            "uf": row.get("sigla_uf"), "modality": row.get("modalidade_nome"), "published": (row.get("data_publicacao_pncp") or "")[:10],
                            "deadline": (row.get("data_encerramento_proposta") or "")[:10], "value": row.get("valor_total_estimado"),
                            "text": (row.get("objeto_compra") or "")[:400], "link": portal_link(key), "rank": position + 1})
        return {"mode": mode, "query": question, "total": total or len(results), "results": results,
                "vector_available": bool(self.embed_url)}
