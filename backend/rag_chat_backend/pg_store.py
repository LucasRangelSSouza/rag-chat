"""Postgres full-text store for the corpus profile (alternative to the SQLite index).

Reads a table that has a generated `fts tsvector` column and the record columns the answer needs.
The connection role is read-only with a statement timeout; queries use bound parameters only.
"""
from __future__ import annotations

import re
import threading
from typing import Any

from .index import _groups

RECORD_COLUMNS = ["numero_controle_pncp", "ano_compra", "data_publicacao_pncp", "data_encerramento_proposta", "sigla_uf",
                  "nome_municipio", "orgao_razao_social", "modalidade_nome", "situacao_compra_nome", "objeto_compra",
                  "categoria_area", "valor_total_estimado"]
_SAFE = re.compile(r"^[a-z0-9]+$")


def tsquery(groups: list[list[str]]) -> str:
    """AND of OR-groups, each lexeme quoted: ('escola' | 'escolar') & ('merenda')."""
    parts = []
    for group in groups:
        alts = [a for a in group if _SAFE.match(a)]
        if not alts:
            continue
        parts.append("(" + " | ".join(f"'{a}'" for a in alts) + ")")
    return " & ".join(parts)


class PgStore:
    is_pg = True

    def __init__(self, dsn: str, table: str = "pncp.obt_pncp_editais_semantico", cutoff: str = "2026-07-31") -> None:
        import psycopg  # imported here so the SQLite path needs no Postgres driver

        if not re.match(r"^[a-z_]+\.[a-z_0-9]+$", table):
            raise ValueError("invalid table name")
        self._psycopg, self.dsn, self.table, self.cutoff = psycopg, dsn, table, cutoff
        self._lock = threading.Lock()
        self._conn: Any = None
        self._count: int | None = None

    def _connection(self):
        if self._conn is None or self._conn.closed:
            self._conn = self._psycopg.connect(self.dsn, autocommit=True, connect_timeout=5)
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

    def search(self, question: str, k: int = 5) -> tuple[int, list[dict]]:
        query = tsquery(_groups(question))
        if not query:
            return 0, []
        cols = ", ".join(RECORD_COLUMNS)
        _, counted = self._run(
            f"SELECT count(*) FROM (SELECT 1 FROM {self.table} WHERE fts @@ to_tsquery('portuguese', %s) LIMIT 100000) m",
            (query,))
        total = int(counted[0][0])
        if not total:
            return 0, []
        names, rows = self._run(
            f"WITH m AS (SELECT {cols}, fts FROM {self.table} WHERE fts @@ to_tsquery('portuguese', %s) LIMIT 20000) "
            f"SELECT {cols} FROM m ORDER BY ts_rank_cd(fts, to_tsquery('portuguese', %s)) DESC LIMIT %s",
            (query, query, k))
        hits = [{n: (None if v is None else str(v)) for n, v in zip(names, row)} for row in rows]
        return total, hits
