# Project memory

## Scope

RAG Chat: corpus-agnostic, bounded, cited research chat. First corpus profile: PNCP (semantic layer of the public PNCP Kaggle catalogue).

## Current state (2026-09-30)

- Interface (Next.js) and same-origin proxy exist with Playwright tests.
- Backend (`backend/`): guardrails, PT/EN language detection, SQLite FTS5 retrieval, optional OpenAI-compatible model client, citation validation. 7 unit tests pass (`cd backend && python -m pytest -q`).
- Not yet done: index built from the pinned PNCP release, live deployment, Qwen smoke evidence.

## Decisions

- Model output is accepted only if every citation tag maps to a retrieved record; otherwise the service falls back to a cited extractive answer.
- Retrieval is lexical BM25 over records; embeddings in the release are not used at query time because the embedding model is not served here.

## Next verifiable task

Build the index from the published semantic Parquet, run the backend beside the interface, and record a dated evidence file.
