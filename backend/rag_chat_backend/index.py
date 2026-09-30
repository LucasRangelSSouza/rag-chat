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


def read_meta(db) -> dict:
    if getattr(db, "is_pg", False):
        return db.meta()
    return {k: json.loads(v) for k, v in db.execute("SELECT k, v FROM meta")}


_STOP = set("a o as os de do da dos das em no na nos nas que qual quais quantos quantas para por com um uma sobre "
            "the of in on what which how many are is there for with about and to any me show list mostre liste "
            "existem existe tem ha sao licitacoes licitacao contratacoes contratacao compras compra registros registro "
            "publicados publicado publicadas record records released release procurement procurements purchases "
            "purchase exist included include listed notices notice bids bid tender tenders corpus dados data "
            "following give find information about records list lists".split())

# Deterministic English to Portuguese glossary for the procurement domain. The corpus text is Portuguese,
# so an English question must be bridged before lexical retrieval.
GLOSSARY = {
    "service": ["servico", "servicos"], "services": ["servico", "servicos"],
    "school": ["escola", "escolar", "escolares"], "schools": ["escola", "escolar", "escolares"],
    "meal": ["merenda", "refeicao", "alimentacao"], "meals": ["merenda", "refeicao", "alimentacao"],
    "lunch": ["merenda", "refeicao"], "food": ["alimento", "alimentos", "alimentacao", "genero"],
    "transport": ["transporte"], "transportation": ["transporte"], "bus": ["onibus"], "vehicle": ["veiculo", "veiculos"],
    "vehicles": ["veiculo", "veiculos"], "cleaning": ["limpeza"], "construction": ["obra", "obras", "construcao"],
    "works": ["obra", "obras"], "medicine": ["medicamento", "medicamentos"], "medicines": ["medicamento", "medicamentos"],
    "drugs": ["medicamento", "medicamentos"], "computer": ["computador", "computadores"], "computers": ["computador", "computadores"],
    "book": ["livro", "livros"], "books": ["livro", "livros"], "uniform": ["uniforme", "uniformes"], "uniforms": ["uniforme", "uniformes"],
    "equipment": ["equipamento", "equipamentos"], "fuel": ["combustivel", "combustiveis"], "health": ["saude"],
    "teacher": ["professor", "docente"], "teachers": ["professor", "docente"], "furniture": ["mobiliario", "moveis"],
    "software": ["software", "sistema"], "internet": ["internet"], "paving": ["pavimentacao", "asfalto"],
    "security": ["seguranca", "vigilancia"], "maintenance": ["manutencao"], "training": ["capacitacao", "treinamento"],
    "stationery": ["papelaria", "expediente"], "supplies": ["material", "materiais", "insumos"], "material": ["material", "materiais"],
    "hospital": ["hospital", "hospitalar"], "ambulance": ["ambulancia"], "tires": ["pneu", "pneus"], "printer": ["impressora"],
    "printing": ["impressao", "grafica"], "energy": ["energia"], "water": ["agua"], "garbage": ["lixo", "residuos"], "waste": ["residuos", "lixo"],
    "sports": ["esportivo", "esportivos", "esporte"], "music": ["musical", "musica"], "event": ["evento", "eventos"], "events": ["evento", "eventos"],
}


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _groups(question: str) -> list[list[str]]:
    """One alternatives-group per meaningful question term; the query ANDs the groups."""
    seen, groups = set(), []
    for term in re.findall(r"[a-z0-9]{3,}", _fold(question)):
        if term in _STOP or term in seen:
            continue
        seen.add(term)
        alts = GLOSSARY.get(term, [term])
        groups.append(list(dict.fromkeys([term, *alts])) if term in GLOSSARY else alts)
    return groups[:5]


def _match(groups: list[list[str]]) -> str:
    return " AND ".join("(" + " OR ".join(f'"{alt}"' for alt in group) + ")" for group in groups)


def search(db, question: str, k: int = 5) -> tuple[int, list[dict]]:
    if getattr(db, "is_pg", False):
        return db.search(question, k)
    groups = _groups(question)
    if not groups:
        return 0, []
    match = _match(groups)
    count = db.execute("SELECT count(*) FROM (SELECT rowid FROM fts WHERE fts MATCH ? LIMIT 100000)", (match,)).fetchone()[0]
    if not count:
        return 0, []
    hits = db.execute(
        "SELECT r.*, bm25(fts) AS score FROM fts JOIN records r ON r.rowid = fts.rowid "
        "WHERE fts MATCH ? ORDER BY score LIMIT ?", (match, k)).fetchall()
    return count, [dict(h) for h in hits]
