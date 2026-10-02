#!/usr/bin/env bash
# Creates the read-only Metabase demo login. Usage: bash metabase_demo_user.sh user@rangeltech.net
set -euo pipefail
set -a; . /opt/demo/runtime-lab/deploy/public-demo/.env; set +a
docker run --rm -it --network public-demo_app -e MB_URL=http://public-demo-metabase-1:3000 -e METABASE_ADMIN_EMAIL -e METABASE_ADMIN_PASSWORD \n  -v /opt/pncp-dashboard/seed:/seed:ro -v /opt/rag-chat-infra/metabase_demo_user.py:/u.py:ro python:3.12-slim python /u.py "$1"
