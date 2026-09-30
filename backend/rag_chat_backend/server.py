from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .answer import Engine
from .index import open_index
from .qwen import QwenClient

MAX_BODY = 16 * 1024


def make_engine() -> Engine:
    model = None
    if os.environ.get("QWEN_BASE_URL"):
        model = QwenClient(os.environ["QWEN_BASE_URL"], os.environ.get("QWEN_API_KEY", ""), os.environ.get("QWEN_MODEL", "qwen"),
                           extra_headers=json.loads(os.environ.get("QWEN_EXTRA_HEADERS") or "{}"))
    return Engine(db=open_index(Path(os.environ["RAG_INDEX_PATH"])), profile=os.environ.get("RAG_PROFILE", "PNCP corpus profile"),
                  release=os.environ.get("RAG_RELEASE", "v1"), dataset_slug=os.environ["RAG_DATASET_SLUG"],
                  manifest_sha256=os.environ.get("RAG_MANIFEST_SHA256"), model=model)


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
                assert isinstance(question, str) and set(body) == {"question"}
            except Exception:
                return self._send(400, {"error": "invalid request"})
            self._send(200, engine.answer(question))

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
