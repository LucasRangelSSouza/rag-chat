# Live click-through

Run: 2026-09-30T20:56:31.809Z

| Check | Result | Seconds | Detail |
|---|---|---:|---|
| chat loads and lists the research bases | pass | 3 | 3 bases |
| text base answers with citations | pass | 15 |  |
| SIOPE SQL base shows the query as evidence | FAIL | 150 | locator.waitFor: Timeout 150000ms exceeded. |
| no base selected gives a plain, ungrounded reply | pass | 15 |  |
| explorer text search returns notices | FAIL | 38 | page.goto: Timeout 30000ms exceeded. |
| explorer semantic search answers or explains | FAIL | 30 | locator.click: Timeout 30000ms exceeded. |
| PNCP dashboard frame renders charts | pass | 0 |  |
| SIOPE dashboard frame renders charts | pass | 11 |  |
