#!/usr/bin/env bash
# Keeps the demo fast. Runs from cron on the VPS every 30 minutes:
#   1. pulls the tables the SQL bases read into memory (pg_prewarm), so a cold first query does not take 17 s;
#   2. asks the welcome-screen questions through the backend, which fills its 6-hour answer cache.
# The backend is called on the internal network, so these calls do not use visitors' rate limits or quotas.
set -uo pipefail

DB=pncp-db-db-1
PGUSER_IN=$(docker exec "$DB" printenv POSTGRES_USER)
docker exec -i "$DB" psql -U "$PGUSER_IN" -d pncp -qAt >/dev/null <<'SQL'
CREATE EXTENSION IF NOT EXISTS pg_prewarm;
SELECT pg_prewarm('pncp.obt_pncp_contratos', 'read');
SELECT pg_prewarm('pncp.obt_pncp_contratos_objeto_norm_trgm', 'read');
SELECT pg_prewarm('pncp.obt_pncp_contratos_mun_norm', 'read');
SELECT pg_prewarm('pncp.obt_pncp_contratos_ano_uf_mun_idx', 'read');
SELECT pg_prewarm('pncp.obt_pncp_atas', 'read');
SELECT pg_prewarm('pncp.obt_pncp_atas_objeto_norm_trgm', 'read');
SELECT pg_prewarm('pncp.editais_embeddings_qwen_ivf', 'read');
SQL

docker exec -i rag-chat-backend-1 python - <<'PY'
import json, urllib.request
QUESTIONS = [
    ("Quais editais de merenda escolar foram publicados em Goiás?", ["pncp"]),
    ("Qual município assinou mais contratos em 2025?", ["pncp-sql"]),
    ("Qual o município que mais gastou com contratos de software em 2025?", ["pncp-sql"]),
    ("Qual estado tem a maior média de investimento por aluno em 2023?", ["siope"]),
    ("Which notices are about school uniforms?", ["pncp"]),
    ("Quantos municípios declararam ao SIOPE em 2024?", ["siope"]),
]
for question, corpora in QUESTIONS:
    body = json.dumps({"question": question, "corpora": corpora}).encode()
    request = urllib.request.Request("http://localhost:8080/v1/answer", data=body, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.load(response)
        print(data.get("status"), "cached" if data.get("cached") else "fresh", question[:50])
    except Exception as error:  # a slow or failed warm-up must not break the next run
        print("error", type(error).__name__, question[:50])
PY
