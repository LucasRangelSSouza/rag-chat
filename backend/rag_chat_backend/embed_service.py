"""Tiny internal service that turns a query into an embedding.

It is the only component that holds the Google service-account key, so the public-facing backend never
sees it. It is not published on any host port; the backend reaches it over the private Compose network.

POST /embed {"text": "..."} -> {"embedding": [768 floats]}
Environment: EMBED_CREDENTIALS_FILE, EMBED_PROJECT, EMBED_LOCATION (default us-central1), EMBED_MODEL.
"""
from __future__ import annotations

import json
import os
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_TEXT = 1000


class VertexEmbedder:
    def __init__(self) -> None:
        from google.oauth2 import service_account

        self.project = os.environ["EMBED_PROJECT"]
        self.location = os.environ.get("EMBED_LOCATION", "us-central1")
        self.model = os.environ.get("EMBED_MODEL", "text-multilingual-embedding-002")
        self.credentials = service_account.Credentials.from_service_account_file(
            os.environ["EMBED_CREDENTIALS_FILE"], scopes=["https://www.googleapis.com/auth/cloud-platform"])
        self._lock = threading.Lock()

    def _token(self) -> str:
        from google.auth.transport.requests import Request

        with self._lock:
            if not self.credentials.valid:
                self.credentials.refresh(Request())
            return self.credentials.token

    def embed(self, text: str) -> list[float]:
        url = (f"https://{self.location}-aiplatform.googleapis.com/v1/projects/{self.project}/locations/{self.location}"
               f"/publishers/google/models/{self.model}:predict")
        body = json.dumps({"instances": [{"content": text[:MAX_TEXT]}]}).encode()
        request = urllib.request.Request(url, data=body, headers={"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)["predictions"][0]["embeddings"]["values"]


def main() -> None:
    embedder = VertexEmbedder()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/embed":
                self.send_response(404); self.end_headers(); return
            try:
                length = int(self.headers.get("content-length") or 0)
                text = json.loads(self.rfile.read(min(length, 8192)))["text"]
                assert isinstance(text, str) and text.strip()
                payload = json.dumps({"embedding": embedder.embed(text)}).encode()
                self.send_response(200)
            except Exception:
                payload = b'{"error":"embedding unavailable"}'
                self.send_response(503)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            self.send_response(200 if self.path == "/healthz" else 404)
            self.end_headers()

        def log_message(self, *args):
            pass

    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8090"))), Handler).serve_forever()


if __name__ == "__main__":
    main()
