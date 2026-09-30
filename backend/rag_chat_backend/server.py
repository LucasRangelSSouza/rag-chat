from __future__ import annotations

import json
import os
import sys
import threading
from urllib.parse import parse_qs, urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .answer import Corpus, Engine
from .index import open_index
from .qwen import QwenClient

MAX_BODY = 16 * 1024


def warm_index(path: Path) -> None:
    """Read the index once so the first visitor does not pay for a cold page cache."""
    def run() -> None:
        with path.open("rb") as stream:
            while stream.read(8 << 20):
                pass
    threading.Thread(target=run, daemon=True).start()


def make_engine() -> Engine:
    """Build the research bases from the environment.

    Postgres mode (RAG_DATABASE_URL): the first base is RAG_TABLE; extra bases come from
    RAG_EXTRA_CORPORA, a JSON list of {id, label, table, dataset_slug, release, cutoff}.
    SQLite mode (RAG_INDEX_PATH): a single base, kept as a fallback.
    """
    corpora: dict[str, Corpus] = {}
    slug = os.environ["RAG_DATASET_SLUG"]
    release = os.environ.get("RAG_RELEASE", "v1")
    manifest = os.environ.get("RAG_MANIFEST_SHA256")
    base_id = os.environ.get("RAG_BASE_ID", "pncp")
    base_label = os.environ.get("RAG_PROFILE", "PNCP procurement")
    if os.environ.get("RAG_DATABASE_URL"):
        from .pg_store import PgStore

        dsn = os.environ["RAG_DATABASE_URL"]
        cutoff = os.environ.get("RAG_CUTOFF", "2026-07-31")
        corpora[base_id] = Corpus(base_id, base_label,
                                  PgStore(dsn, os.environ.get("RAG_TABLE", "pncp.obt_pncp_editais_semantico"), cutoff, embed_url=os.environ.get("EMBED_URL"),
                                          vectors_table=os.environ.get("RAG_VECTORS_TABLE", "pncp.editais_embeddings")),
                                  slug, release, manifest)
        for extra in json.loads(os.environ.get("RAG_EXTRA_CORPORA") or "[]"):
            if extra.get("type") == "sql":
                from .sql_agent import SqlStore

                store = SqlStore(os.environ["RAG_SQL_DATABASE_URL"], extra["tables"], extra.get("cutoff", "n/a"), extra.get("notes", ""))
            else:
                store = PgStore(dsn, extra["table"], extra.get("cutoff", cutoff))
            corpora[extra["id"]] = Corpus(extra["id"], extra["label"], store, extra["dataset_slug"], extra.get("release", "v1"),
                                          extra.get("manifest_sha256"))
    else:
        path = Path(os.environ["RAG_INDEX_PATH"])
        warm_index(path)
        corpora[base_id] = Corpus(base_id, base_label, open_index(path), slug, release, manifest)
    model = None
    if os.environ.get("QWEN_BASE_URL"):
        model = QwenClient(os.environ["QWEN_BASE_URL"], os.environ.get("QWEN_API_KEY", ""), os.environ.get("QWEN_MODEL", "qwen"),
                           extra_headers=json.loads(os.environ.get("QWEN_EXTRA_HEADERS") or "{}"))
    return Engine(corpora=corpora, model=model)


def handler(engine: Engine):
    class H(BaseHTTPRequestHandler):
        def _send(self, code: int, payload: dict) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path in ("/healthz", "/v1/health"):
                return self._send(200, engine.health())
            parsed = urlparse(self.path)
            if parsed.path == "/v1/search":
                params = parse_qs(parsed.query)
                mode = (params.get("mode") or ["hybrid"])[0]
                query = (params.get("q") or [""])[0].strip()
                try:
                    limit = max(1, min(25, int((params.get("limit") or ["20"])[0])))
                except ValueError:
                    limit = 20
                store = next((c.store for c in engine.corpora.values() if hasattr(c.store, "explore")), None)
                if store is None or mode not in ("text", "vector", "hybrid") or not (3 <= len(query) <= 200):
                    return self._send(400, {"error": "invalid search"})
                try:
                    return self._send(200, store.explore(mode, query, limit))
                except Exception:
                    return self._send(503, {"error": "search unavailable"})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/v1/answer":
                return self._send(404, {"error": "not found"})
            length = int(self.headers.get("content-length") or 0)
            if length > MAX_BODY:
                return self._send(413, {"error": "too large"})
            try:
                body = json.loads(self.rfile.read(length))
                question = body["question"]
                corpora = body.get("corpora", [])
                assert isinstance(question, str) and set(body) <= {"question", "corpora"}
                assert isinstance(corpora, list) and len(corpora) <= 5 and all(isinstance(c, str) and len(c) <= 40 for c in corpora)
            except Exception:
                return self._send(400, {"error": "invalid request"})
            self._send(200, engine.answer(question, corpora))

        def log_message(self, *args):
            pass
    return H


def main() -> None:
    engine = make_engine()
    port = int(os.environ.get("PORT", "8080"))
    print(f"rag-chat backend on :{port}", file=sys.stderr)
    ThreadingHTTPServer(("0.0.0.0", port), handler(engine)).serve_forever()


if __name__ == "__main__":
    main()
