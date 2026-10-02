# Live click-through

Run: 2026-10-01T23:18:40.464Z

| Check | Result | Seconds | Detail |
|---|---|---:|---|
| chat loads and lists the research bases | pass | 9 | 3 bases |
| text base answers with citations | FAIL | 138 | locator.waitFor: Timeout 120000ms exceeded. |
| SIOPE SQL base shows the query as evidence | pass | 21 |  |
| no base selected gives a plain, ungrounded reply | pass | 15 |  |
| explorer text search returns notices | FAIL | 76 | locator.waitFor: Timeout 60000ms exceeded. |
| explorer semantic search answers or explains | pass | 14 |  |
| PNCP dashboard frame renders charts | pass | 0 |  |
| SIOPE dashboard frame renders charts | pass | 10 |  |
