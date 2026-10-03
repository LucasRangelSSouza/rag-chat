# Fixed 60-question evaluation of the live chat (2026-10-02)

20 questions per base: SIOPE education spending (SQL), PNCP contracts (SQL) and PNCP notices (retrieval). The expected answer of every numeric or name question was computed with SQL written before the run (`truth_sql` in `questions.json`); two questions whose reference returned no data or a zero were replaced before any answer was collected. Notice questions are graded by reading the state and object of every cited notice.

Run: `scripts/qa60.py ask` against https://rag.rangeltech.net, one question at a time, no conversation history; `scripts/qa60.py grade` is mechanical (a number within 0.5%, counts exact; the expected name in the answer; every cited notice in the right state and on topic).

| Base | Correct |
|---|---|
| SIOPE (SQL) | 19 / 20 |
| PNCP contracts (SQL) | 18 / 20 |
| PNCP notices (retrieval) | 18 / 20 |
| All | 55 / 60 |

The five misses, read by hand:
- s20: the agent added a filter nobody asked for (values above 100,000 excluded as typos) and answered 1,838 instead of 1,841. It said so in the answer. Wrong.
- c15: "school uniform contracts" searched only `%uniforme%` and counted 2,448 against 328. Too broad. Wrong.
- c04: "school transport contracts in Bahia" added synonyms to the pattern and counted 370 against 360. A defensible reading that differs from the reference.
- r11, r12: of 5 cited notices, 4 and 2 were in the right state but outside the strict topic list (teaching material instead of school supplies; engineering services that mention schools).
