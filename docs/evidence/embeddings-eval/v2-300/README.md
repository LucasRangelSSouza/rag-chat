# Embeddings benchmark, 300 queries (2026-10-02)

Known-item retrieval over 1.25 million procurement notices: `pncp.editais_embeddings_qwen` (Qwen3-Embedding, 768 dims) against `pncp.editais_embeddings` (Vertex `text-multilingual-embedding-002`, 768 dims).

- Queries: `../queries-300.json`. 30 from the first benchmark (`set: v1-hand-30`) plus 270 new (`set: v2-270`): notices sampled with `TABLESAMPLE SYSTEM (0.5) REPEATABLE (77)`, objects of 80 to 350 characters, present in both tables, not in the first 30. Each query is a paraphrase of one notice's object, written the way a person searches, by Claude (Anthropic), a model from neither family under test. The target is that notice.
- Runs: `res-*-p12.json` use `ivfflat.probes = 12` (the chat's setting); `res-*-p1100.json` visit every list (exact).
- Decision rule fixed before the run: "Qwen is better" only if the 95% bootstrap interval of the R@1 difference, exact search, excludes zero.

| Run | Model | R@1 | R@5 | R@10 | MRR@10 |
|---|---|---|---|---|---|
| exact | Qwen | 0.487 | 0.743 | 0.780 | 0.592 |
| exact | Vertex | 0.383 | 0.613 | 0.677 | 0.481 |
| probes 12 | Qwen | 0.417 | 0.613 | 0.647 | 0.504 |
| probes 12 | Vertex | 0.350 | 0.543 | 0.603 | 0.433 |

Exact: top-1 hits only by Qwen 55, only by Vertex 24, McNemar p = 0.0006; R@1 difference 0.104, 95% bootstrap interval 0.047 to 0.163. The rule is met.
Probes 12: 58 against 38, p = 0.052; difference 0.067, interval 0.003 to 0.130.

`summary.json` has every metric, the medians of embedding and search time, and the split by query set.
