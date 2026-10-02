# Live QA through the chat interface, 2026-10-02

Questions were typed into the composer at https://rag.rangeltech.net and sent with the send button, so every turn is a normal browser conversation (four conversations plus a retest). Base selection per conversation as shown.

| Conversation | Questions | Answered correctly | Notes |
|---|---|---|---|
| PNCP notices (text + vector) | 20 | 20 | State filter keeps answers inside the named state; answers name body, municipality and object |
| PNCP contracts (SQL) | 20 | 20 after retest | First run: 11 written answers, 6 correct but extractive, 3 failures (a 502 during a deploy, a cold-cache abstention, a wrong year on price registrations) |
| SIOPE (SQL) | 20 | 20 after retest | First run: 14 written, 4 extractive, 2 wrong (capitals guessed by name, "largest increase" answered as "largest value") |
| Long session, all bases | 8 | 8 | Mixed question, follow-up "E em 2023?", three-part question, recap, off-topic refusal, English question |

Fixes shipped between the runs: SQL rows reach the model with their query and explanation; up to 30 result rows in context; multi-number questions in one SQL result; rankings kept in the numeric part of mixed questions; recap reads earlier answers; capitals and year-over-year rules in the SQL notes; at most four LIKE patterns; 1500-token SQL replies; no PERCENTILE_CONT with OVER; compact SIOPE tables with primary keys (per-student with names, indicators, spending by subfunction, indicator list); accent- and case-insensitive text matching with f_unaccent and trigram indexes.

Known data limit: some PNCP contract values are data-entry errors well below the 1 billion BRL cap (for example Araxá and Maringá reach billions across thousands of contracts). Answers state the cap they applied; they cannot detect every bad value.
