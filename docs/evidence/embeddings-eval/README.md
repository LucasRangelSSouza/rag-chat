# Embeddings benchmark, 2026-10-02

Known-item retrieval over `pncp.editais_embeddings_qwen` (Qwen3-Embedding, 768 dims) and `pncp.editais_embeddings` (Vertex `text-multilingual-embedding-002`, 768 dims), 1.25 million notices each.

- Sample: 45 notices drawn with `setseed(0.42)` and `TABLESAMPLE SYSTEM (0.2)` from `pncp.obt_pncp_editais_semantico`, objects of 80 to 350 characters, present in both tables. 30 were kept and a query was written by hand for each (`queries.json`).
- Runs: `result-*.json` use `ivfflat.probes = 12` (the chat's setting); `exact-*.json` use `probes = 1100`, every list.
- Script: `scripts/eval_embeddings.py` (`embed`, `search`, `report`).

| Run | Model | R@1 | R@5 | R@10 | MRR@10 | Embed ms (median) | Search ms (median) |
|---|---|---|---|---|---|---|---|
| probes 12 | Qwen | 0.400 | 0.600 | 0.600 | 0.461 | 346 | 792 |
| probes 12 | Vertex | 0.367 | 0.600 | 0.633 | 0.454 | 840 | 706 |
| exact | Qwen | 0.500 | 0.733 | 0.733 | 0.583 | 346 | 3149 |
| exact | Vertex | 0.400 | 0.633 | 0.667 | 0.487 | 840 | 4094 |

McNemar on top-1 hits: probes 12, 5 against 4 discordant pairs, p = 1.0; exact, 6 against 3, p = 0.508.
