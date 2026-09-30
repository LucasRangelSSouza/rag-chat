# Claim-to-evidence map: cited RAG chat

| Claim | Evidence | Status |
|---|---|---|
| Index holds 1,166,977 notices, cutoff 2026-07-31, built in about 10 minutes | Live `/api/health`; `docs/evidence/2026-09-30-live-acceptance.md` | Supported |
| Proxy accepts one field up to 1,000 characters; extra field returns 400 | `app/api/answer/route.ts`; acceptance table | Supported |
| Injection in English and Portuguese is refused in the question language without a model call | Acceptance table; `backend/tests/test_backend.py` | Supported |
| A model reply with a citation not returned by retrieval is discarded | `test_model_citations_must_be_returned_chunks` | Supported |
| Unavailable model is skipped by a cached probe | `QwenClient.available`; deployment check with the upstream down | Supported |
| English and Portuguese questions each got an answer in their own language | Acceptance table; live runs on 2026-09-30 | Supported for the cases tested |
| Glossary bridges English terms to Portuguese records | `backend/tests/test_backend.py` glossary test; live transport question | Supported for glossary terms |
| First request after restart was slow due to a cold index cache | Timing on the host before and after cache warm-up | Supported (observation, one host) |
| Retrieval quality | Not measured | Not claimed |
| Behaviour under load | Not measured | Not claimed |
