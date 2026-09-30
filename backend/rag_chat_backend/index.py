"""SQLite FTS5 index built from the pinned semantic Parquet files of the PNCP release."""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from pathlib import Path

import pyarrow.parquet as pq

FIELDS = ["numero_controle_pncp", "ano_compra", "data_publicacao_pncp", "data_encerramento_proposta", "sigla_uf",
          "nome_municipio", "orgao_razao_social", "modalidade_nome", "situacao_compra_nome", "objeto_compra",
          "categoria_area", "valor_total_estimado"]


def build_index(parquet_path: Path, db_path: Path, meta: dict, batch_rows: int = 50_000) -> int:
    """Index one semantic table. Text fields become searchable; every cited field is stored."""
    if db_path.exists():
        db_path.unlink()
    db = sqlite3.connect(db_path)
    db.execute("PRAGMA journal_mode=OFF")
    db.execute("PRAGMA synchronous=OFF")
    db.execute(f"CREATE TABLE records ({', '.join(f + ' TEXT' for f in FIELDS)})")
    db.execute("CREATE VIRTUAL TABLE fts USING fts5(objeto, orgao, municipio, categoria, "
               "tokenize='unicode61 remove_diacritics 2')")
    db.execute("CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT)")
    pf = pq.ParquetFile(parquet_path)
    present = [f for f in FIELDS if f in pf.schema_arrow.names]
    total = 0
    for batch in pf.iter_batches(batch_size=batch_rows, columns=present):
        rows = batch.to_pylist()
        db.executemany(f"INSERT INTO records ({', '.join(present)}) VALUES ({', '.join('?' * len(present))})",
                       [[None if r[f] is None else str(r[f]) for f in present] for r in rows])
        start = total + 1
        db.executemany("INSERT INTO fts(rowid, objeto, orgao, municipio, categoria) VALUES (?,?,?,?,?)",
                       [(start + i, r.get("objeto_compra") or "", r.get("orgao_razao_social") or "",
                         r.get("nome_municipio") or "", r.get("categoria_area") or "") for i, r in enumerate(rows)])
        total += len(rows)
    meta = {**meta, "record_count": total}
    db.executemany("INSERT INTO meta VALUES (?,?)", [(k, json.dumps(v)) for k, v in meta.items()])
    db.commit()
    db.close()
    return total


def open_index(db_path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db


def read_meta(db: sqlite3.Connection) -> dict:
    return {k: json.loads(v) for k, v in db.execute("SELECT k, v FROM meta")}


_STOP = set("a o as os de do da dos das em no na nos nas que qual quais quantos quantas para por com um uma sobre "
            "the of in on what which how many are is there for with about and to any me show list mostre liste "
            "existem tem ha sao licitacoes contratacoes compras procurements purchases exist".split())


def _terms(question: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", question).encode("ascii", "ignore").decode().lower()
    return [t for t in re.findall(r"[a-z0-9]{3,}", folded) if t not in _STOP][:8]


def search(db: sqlite3.Connection, question: str, k: int = 5) -> tuple[int, list[dict]]:
    terms = _terms(question)
    if not terms:
        return 0, []
    match = " OR ".join(f'"{t}"' for t in terms)
    count = db.execute("SELECT count(*) FROM fts WHERE fts MATCH ?", (match,)).fetchone()[0]
    hits = db.execute(
        "SELECT r.*, bm25(fts) AS score FROM fts JOIN records r ON r.rowid = fts.rowid "
        "WHERE fts MATCH ? ORDER BY score LIMIT ?", (match, k)).fetchall()
    return count, [dict(h) for h in hits]
