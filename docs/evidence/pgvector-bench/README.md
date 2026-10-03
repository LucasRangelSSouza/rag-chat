# pgvector: IVFFlat against HNSW (2026-10-02)

250,000 Qwen3-Embedding vectors (`halfvec(768)`, the rows with the smallest md5 of their id, copied from `pncp.editais_embeddings_qwen` into a throwaway `bench` schema that was dropped afterwards) and the 300 query vectors of the embeddings benchmark. Postgres 16 with pgvector 0.8.6, in a container limited to 3.4 GiB on the production server, at night.

- Reference: exact search with no index (p50 252 ms, p95 727 ms).
- Recall@10: share of the exact top 10 that the indexed search returns, averaged over the 300 queries.
- IVFFlat: `lists = 500`, built with `maintenance_work_mem = 1GB`, one process: 68 s, 393 MB.
- HNSW: `m = 16, ef_construction = 64`, built with `maintenance_work_mem = 256MB` and no parallel workers (the container's /dev/shm was too small for a 1 GB parallel build): 1,373 s, 467 MB.

`pgvector-bench.json` has every setting. Script: `scripts/bench_pgvector.py`.
