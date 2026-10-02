"""IVFFlat against HNSW on the same halfvec(768) vectors, measured as recall@10 against exact search and latency.

Runs inside the backend image (psycopg, RAG_DATABASE_URL), against a copy of N rows in schema `bench`, so the production
tables and their index are never touched:

  python bench_pgvector.py setup   250000            # copy N rows of pncp.editais_embeddings_qwen into bench.vec
  python bench_pgvector.py run     vectors-qwen.json out.json
  python bench_pgvector.py drop                       # removes schema bench

`run` builds each index in turn (timed, with its size), then for every query vector and every search setting records the
top 10 and the time; recall@10 is the share of the exact top 10 that the indexed search returns.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time

import psycopg

# The bench schema needs a role that can create tables; the chat's own role is read-only.
URL = os.environ.get("BENCH_DATABASE_URL") or os.environ["RAG_DATABASE_URL"]


def connect():
    return psycopg.connect(URL, autocommit=True)


def setup(n: str) -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS bench")
        cur.execute("DROP TABLE IF EXISTS bench.vec")
        start = time.perf_counter()
        # A deterministic sample: the N rows with the smallest md5 of their id.
        cur.execute(f"CREATE TABLE bench.vec AS SELECT numero_controle_pncp id, embedding FROM pncp.editais_embeddings_qwen "
                    f"ORDER BY md5(numero_controle_pncp) LIMIT {int(n)}")
        cur.execute("ANALYZE bench.vec")
        cur.execute("SELECT count(*), pg_size_pretty(pg_relation_size('bench.vec')) FROM bench.vec")
        print("bench.vec", cur.fetchone(), f"{time.perf_counter() - start:.0f}s")


def literal(v):
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def search(cur, vec, setting_sql):
    if setting_sql:
        cur.execute(setting_sql)
    start = time.perf_counter()
    cur.execute("SELECT id FROM bench.vec ORDER BY embedding <=> %s::halfvec LIMIT 10", (vec,))
    return [r[0] for r in cur.fetchall()], (time.perf_counter() - start) * 1000


def index_info(cur):
    cur.execute("SELECT pg_relation_size('bench.vec_idx')")
    return cur.fetchone()[0]


def run(vectors_path: str, out_path: str) -> None:
    vecs = [literal(item["vector"]) for item in json.load(open(vectors_path, encoding="utf-8"))]
    out = {"queries": len(vecs), "configs": []}
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SET statement_timeout = 0")
        cur.execute("SET max_parallel_maintenance_workers = 1")
        cur.execute("SELECT count(*) FROM bench.vec")
        out["rows"] = cur.fetchone()[0]

        # Exact top 10 with no index: the reference for recall.
        cur.execute("DROP INDEX IF EXISTS bench.vec_idx")
        exact, exact_ms = [], []
        for v in vecs:
            ids, ms = search(cur, v, None)
            exact.append(ids)
            exact_ms.append(ms)
        out["exact"] = {"p50_ms": statistics.median(exact_ms), "p95_ms": sorted(exact_ms)[int(0.95 * len(exact_ms)) - 1]}
        print("exact", out["exact"], flush=True)

        builds = [
            ("ivfflat", "lists = 500", "CREATE INDEX vec_idx ON bench.vec USING ivfflat (embedding halfvec_cosine_ops) WITH (lists = 500)",
             [f"SET ivfflat.probes = {p}" for p in (1, 2, 4, 8, 16, 32, 64)]),
            ("hnsw", "m = 16, ef_construction = 64", "CREATE INDEX vec_idx ON bench.vec USING hnsw (embedding halfvec_cosine_ops) WITH (m = 16, ef_construction = 64)",
             [f"SET hnsw.ef_search = {e}" for e in (10, 20, 40, 80, 160, 320)]),
        ]
        for kind, params, ddl, settings in builds:
            cur.execute("DROP INDEX IF EXISTS bench.vec_idx")
            cur.execute("SET maintenance_work_mem = '1GB'")
            start = time.perf_counter()
            cur.execute(ddl)
            build_s = time.perf_counter() - start
            size = index_info(cur)
            print(kind, params, f"built in {build_s:.0f}s, {size / 2**20:.0f} MB", flush=True)
            for setting in settings:
                recalls, times = [], []
                for v, ref in zip(vecs, exact):
                    ids, ms = search(cur, v, setting)
                    recalls.append(len(set(ids) & set(ref)) / 10)
                    times.append(ms)
                row = {"index": kind, "params": params, "setting": setting.replace("SET ", ""), "build_s": round(build_s, 1),
                       "size_mb": round(size / 2**20, 1), "recall_at_10": round(statistics.mean(recalls), 4),
                       "p50_ms": round(statistics.median(times), 2), "p95_ms": round(sorted(times)[int(0.95 * len(times)) - 1], 2)}
                out["configs"].append(row)
                print(row, flush=True)
                json.dump(out, open(out_path, "w", encoding="utf-8"), indent=1)
        cur.execute("DROP INDEX IF EXISTS bench.vec_idx")
    json.dump(out, open(out_path, "w", encoding="utf-8"), indent=1)


def drop() -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS bench CASCADE")
        print("bench dropped")


if __name__ == "__main__":
    {"setup": setup, "run": run, "drop": drop}[sys.argv[1]](*sys.argv[2:])
