"""Known-item retrieval benchmark for the notice embeddings.

Each query is a paraphrase written by hand from the object of one real notice; that notice is the
target. The script runs in two steps because the embedder and the database live in different
containers:

  python eval_embeddings.py embed  <provider> queries.json vectors-<provider>.json   (embed container)
  python eval_embeddings.py search <table> vectors-<provider>.json result-<provider>.json  (backend container)
  python eval_embeddings.py report result-qwen.json result-vertex.json                 (anywhere)

`embed` uses the same embedder classes as the live service (EMBED_* variables pick the provider).
`search` runs the same cosine query as the chat over one vectors table and records the target's rank.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time


def embed(provider: str, queries_path: str, out_path: str) -> None:
    os.environ["EMBED_PROVIDER"] = provider
    from rag_chat_backend.embed_service import make_embedder

    embedder = make_embedder()
    queries = json.load(open(queries_path, encoding="utf-8"))
    out = []
    for q in queries:
        start = time.perf_counter()
        vector = embedder.embed(q["query"], "query")
        out.append({**q, "vector": vector, "embed_ms": round((time.perf_counter() - start) * 1000, 1)})
    json.dump(out, open(out_path, "w", encoding="utf-8"))
    print(f"embedded {len(out)} queries with {provider}, dim {len(out[0]['vector'])}")


def search(table: str, vectors_path: str, out_path: str, k: int = 10) -> None:
    import psycopg

    items = json.load(open(vectors_path, encoding="utf-8"))
    results = []
    with psycopg.connect(os.environ["RAG_DATABASE_URL"], autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SET ivfflat.probes = 12")  # same setting as the chat (pg_store.py)
        for item in items:
            literal = "[" + ",".join(f"{v:.6f}" for v in item["vector"]) + "]"
            start = time.perf_counter()
            cur.execute(f"SELECT numero_controle_pncp FROM {table} ORDER BY embedding <=> %s::halfvec LIMIT %s", (literal, k))
            ids = [r[0] for r in cur.fetchall()]
            results.append({"id": item["id"], "query": item["query"], "rank": ids.index(item["id"]) + 1 if item["id"] in ids else None,
                            "embed_ms": item["embed_ms"], "search_ms": round((time.perf_counter() - start) * 1000, 1), "top": ids[:5]})
    json.dump({"table": table, "k": k, "results": results}, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    found = sum(r["rank"] is not None for r in results)
    print(f"{table}: target in top {k} for {found} of {len(results)} queries")


def _metrics(results: list[dict]) -> dict:
    n = len(results)
    ranks = [r["rank"] for r in results]
    median = lambda xs: sorted(xs)[len(xs) // 2]
    return {"n": n, "recall@1": sum(r == 1 for r in ranks) / n, "recall@5": sum(r is not None and r <= 5 for r in ranks) / n,
            "recall@10": sum(r is not None for r in ranks) / n, "mrr@10": sum(1 / r for r in ranks if r) / n,
            "embed_ms_median": median([r["embed_ms"] for r in results]), "search_ms_median": median([r["search_ms"] for r in results])}


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value on the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(0, min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def report(*paths: str) -> None:
    runs = {p: json.load(open(p, encoding="utf-8")) for p in paths}
    for path, run in runs.items():
        print(path, run["table"], json.dumps(_metrics(run["results"])))
    if len(runs) == 2:
        a, b = (run["results"] for run in runs.values())
        hit = lambda r: r["rank"] == 1
        only_a = sum(hit(x) and not hit(y) for x, y in zip(a, b))
        only_b = sum(hit(y) and not hit(x) for x, y in zip(a, b))
        print(json.dumps({"top1_only_first": only_a, "top1_only_second": only_b, "mcnemar_p": round(mcnemar_exact(only_a, only_b), 4)}))


if __name__ == "__main__":
    command, *args = sys.argv[1:]
    {"embed": embed, "search": search, "report": report}[command](*args)
