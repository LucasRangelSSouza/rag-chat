# Building a cited RAG chat on a versioned public-data corpus

A retrieval chat is easy to demo and hard to trust. The failure that matters is not a wrong sentence. It is an answer with no way to check it. I built RAG Chat around one rule: an answer either cites the exact records it used, or the service says it cannot answer.

The first corpus is the semantic layer of a public procurement catalogue from Brazil's national portal (PNCP). The product itself is corpus-agnostic. A deployment loads one pinned corpus profile and nothing else.

## The contract that keeps it honest

A corpus profile pins four things: the Kaggle dataset, its version, the release manifest hash, and the data cutoff. The backend indexes files that match that manifest. Each citation carries the dataset slug, the pinned version, the manifest hash, and the record identifier. The interface reads the release version, cutoff, and record count from the index, not from static copy, so it cannot claim more than the index holds.

In this deployment the index holds 1,166,977 procurement notices published up to 31 July 2026. It is a lexical index (SQLite FTS5), built in about ten minutes.

## Checks run before any model call

The request path has three gates, and none of them needs a model:

1. **Edge limits.** The proxy accepts one field, `question`, up to 1,000 characters. An extra field such as `model` returns 400.
2. **Guardrails.** Prompt-injection patterns in English and Portuguese are refused with a message in the visitor's language.
3. **Scope.** Retrieval must find records that match every meaningful term of the question. If it finds none, the service abstains.

A model is asked to word the answer only after those gates pass, and only from the retrieved records. If the model's reply cites a tag that retrieval did not return, the reply is discarded and the service falls back to a cited extractive answer. If the model upstream is down, a cached probe skips it, so visitors do not wait for a timeout.

## Language follows the question

Answers and abstentions use the language of the question. I checked this on the live deployment with equivalent questions: an English question about school meal procurements got an English answer, and the Portuguese equivalent got a Portuguese answer. Both cited records, and both kept organization names and identifiers untranslated.

English questions raised a retrieval problem I had not planned for. The records are in Portuguese, so "school transport services" matches nothing by itself. I added a small deterministic English-to-Portuguese glossary for common procurement terms, and each question term becomes an OR-group of its Portuguese forms, with the groups joined by AND. The glossary is limited and visible in the code. A term outside it must appear in the record text, otherwise the service abstains.

## What broke on the way

The first live run failed in three ways, and the acceptance test caught all of them.

- An OR query over very common terms scanned most of the index and timed out. Requiring all terms, and capping the match count, brought a typical query to a few tenths of a second once the index file sat in page cache.
- Unrelated questions returned records, because one shared common word matched. The AND rule fixed it.
- The first request after a restart took about 26 seconds while the operating system read the 1.5 GB index from disk. The backend now reads the file at startup, and the container's memory limit is high enough to keep it cached.

## What the live check showed

On 30 September 2026, the deployment answered a supported English question and a supported Portuguese question with model wording and five citations each, in roughly 10 seconds. Out-of-scope questions abstained in about a second without a model call. Injection attempts in both languages were refused in under a second. The oversized question and the extra field were rejected at the edge. The evidence file records each case.

## Limits

- Retrieval is lexical. It answers questions that share words with a record. It does not compare records or compute aggregates beyond a match count.
- The glossary covers common procurement terms only.
- Wording can differ between two runs of the same question, because a model phrases the answer.
- The corpus is a released snapshot, not a live view of the portal, and it does not cover all national procurement.
- One deployment on one day is not a measurement of retrieval quality.

## Reproduce

The repository contains the interface, the backend, the corpus contract, the container files, and the live acceptance record. The backend tests cover language detection, abstention, refusal, the glossary bridge, and the citation validator.
