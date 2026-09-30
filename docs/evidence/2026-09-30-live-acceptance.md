# Live acceptance record, 2026-09-30

**Scope:** one public deployment of RAG Chat with the PNCP corpus profile, checked through its public HTTPS route. Host, upstream address, and credentials are omitted on purpose.

**Corpus:** the semantic table `obt_pncp_editais_semantico` from the PNCP catalogue, cutoff 2026-07-31, 1,166,977 records indexed with SQLite FTS5 (index built in 590 s).

**Model path:** retrieval and guardrails run first. A Qwen-based checkpoint (an abliterated variant published by a third party) phrases the answer only from retrieved records. Every citation tag must map to a returned record, or the service falls back to a cited extractive answer.

## Results

| Check | Result |
|---|---|
| `/api/health` | `ready`, `record_count` 1,166,977, `model_status` `ready` |
| English question, supported (school meal procurements) | 200, `answered`, 5 citations, English answer, 11.5 s |
| Portuguese question, supported (merenda escolar) | 200, `answered`, 5 citations, Portuguese answer, 10.7 s |
| Out-of-scope English question | 200, `abstained`, no citation, English abstention, 1.5 s, no model call |
| Out-of-scope Portuguese question | 200, `abstained`, no citation, Portuguese abstention, 1.2 s, no model call |
| Prompt injection, English and Portuguese | 200, `refused`, message in the question language, under 1 s, no model call |
| Oversized question (1,001 characters) | 400 at the edge proxy |
| Extra request field (`model`) | 400, only `question` accepted |

## Language compliance

The English answer began "The released records contain the following school meal procurements" and quoted Portuguese record titles unchanged. The Portuguese answer began "Os registros publicados indicam". Identifiers, organization names, and numbers were preserved, not translated.

## Limits of this record

- Retrieval is lexical. A deterministic English-to-Portuguese glossary bridges common procurement terms; a term outside it must appear in the record text, otherwise the service abstains.
- Two runs of the same question can differ in wording because the model phrases the answer.
- The first request after a restart is slower until the index file is in the page cache. The service now reads the file at startup.
- This record covers one deployment on one day. It does not measure retrieval quality.

## Interface check with real clicks (live site, same day)

A Playwright run against the public site typed a Portuguese question, waited for the cited answer, clicked **New research**, asked an English question, and checked the history list (two conversations, titled by their first question). It then reopened the first conversation, reloaded the page (history persisted), and loaded the phone-width layout with no horizontal overflow.

Screenshots (desktop empty state, desktop answer, desktop history, mobile, tablet) are in this folder: `2026-09-30-chat-*.png`. The local suite (18 tests, desktop and mobile, including axe checks) also covers history creation, reopening, persistence across reload, and deletion.
