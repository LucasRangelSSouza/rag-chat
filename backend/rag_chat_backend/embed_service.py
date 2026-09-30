"""Tiny internal service that turns a query into an embedding.

It is the only component that holds an embedding credential, so the public-facing backend never sees one.
It is not published on any host port; the backend reaches it over the private Compose network.

POST /embed {"text": "...", "kind": "query" | "document"} -> {"embedding": [floats]}

Providers, chosen with EMBED_PROVIDER (default "vertex"):
  vertex  Google Vertex AI. EMBED_CREDENTIALS_FILE, EMBED_PROJECT, EMBED_LOCATION (us-central1), EMBED_MODEL
          (text-multilingual-embedding-002).
  qwen    Any OpenAI-compatible /v1/embeddings endpoint serving a Qwen3-Embedding model.
          EMBED_BASE_URL, EMBED_API_KEY, EMBED_MODEL (qwen-embedding), EMBED_DIM (768, Matryoshka truncation),
          EMBED_EXTRA_HEADERS (JSON, optional), EMBED_QUERY_INSTRUCT (task text placed in the query prefix).

Query vectors and stored document vectors must come from the same model, so switching the provider also means
reading the vectors table built with that provider (RAG_VECTORS_TABLE in the backend).
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_TEXT = 1000
DEFAULT_INSTRUCT = "Given a question about Brazilian public procurement, retrieve the procurement notices that answer it"


class EmbeddingError(Exception):
    """Raised with a stable code so callers can tell an unreachable endpoint from a bad answer."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


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

    def embed(self, text: str, kind: str = "query") -> list[float]:
        url = (f"https://{self.location}-aiplatform.googleapis.com/v1/projects/{self.project}/locations/{self.location}"
               f"/publishers/google/models/{self.model}:predict")
        body = json.dumps({"instances": [{"content": text[:MAX_TEXT]}]}).encode()
        request = urllib.request.Request(url, data=body, headers={"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.load(response)["predictions"][0]["embeddings"]["values"]
        except (urllib.error.URLError, TimeoutError) as exc:
            raise EmbeddingError("endpoint_unreachable", str(exc)[:120]) from exc


class QwenEmbedder:
    """OpenAI-compatible embeddings endpoint serving Qwen3-Embedding (instruction on the query side only)."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None,
                 dim: int | None = None, extra_headers: dict | None = None, instruct: str | None = None,
                 timeout: float = 25.0, attempts: int = 3, backoff: float = 1.5) -> None:
        self.base_url = (base_url or os.environ["EMBED_BASE_URL"]).rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("EMBED_API_KEY", "")
        self.model = model or os.environ.get("EMBED_MODEL", "qwen-embedding")
        self.dim = int(dim or os.environ.get("EMBED_DIM", "768"))
        self.extra_headers = extra_headers if extra_headers is not None else json.loads(os.environ.get("EMBED_EXTRA_HEADERS") or "{}")
        self.instruct = instruct or os.environ.get("EMBED_QUERY_INSTRUCT", DEFAULT_INSTRUCT)
        self.timeout, self.attempts, self.backoff = timeout, attempts, backoff

    def format(self, text: str, kind: str) -> str:
        text = text[:MAX_TEXT]
        return f"Instruct: {self.instruct}\nQuery:{text}" if kind == "query" else text

    def embed(self, text: str, kind: str = "query") -> list[float]:
        body = json.dumps({"model": self.model, "input": [self.format(text, kind)], "dimensions": self.dim}).encode()
        headers = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        last: EmbeddingError | None = None
        for attempt in range(self.attempts):
            try:
                request = urllib.request.Request(self.base_url + "/embeddings", data=body, headers=headers)
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    vector = json.load(response)["data"][0]["embedding"]
                if len(vector) != self.dim:
                    raise EmbeddingError("bad_dimension", f"expected {self.dim}, got {len(vector)}")
                return vector
            except urllib.error.HTTPError as exc:
                last = EmbeddingError("endpoint_error", f"HTTP {exc.code}")
                if exc.code < 500 and exc.code != 429:
                    break  # a client error will not fix itself on retry
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                last = EmbeddingError("endpoint_unreachable", str(exc)[:120])
            except (KeyError, IndexError, ValueError) as exc:
                raise EmbeddingError("bad_response", str(exc)[:80]) from exc
            if attempt + 1 < self.attempts:
                time.sleep(self.backoff * (attempt + 1))
        raise last or EmbeddingError("endpoint_unreachable")


def make_embedder():
    provider = os.environ.get("EMBED_PROVIDER", "vertex").lower()
    if provider == "qwen":
        return QwenEmbedder()
    if provider == "vertex":
        return VertexEmbedder()
    raise SystemExit(f"unknown EMBED_PROVIDER {provider!r} (vertex or qwen)")


def main() -> None:
    embedder = make_embedder()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/embed":
                self.send_response(404); self.end_headers(); return
            code = 200
            try:
                length = int(self.headers.get("content-length") or 0)
                body = json.loads(self.rfile.read(min(length, 8192)))
                text, kind = body["text"], body.get("kind", "query")
                assert isinstance(text, str) and text.strip() and kind in ("query", "document")
                payload = json.dumps({"embedding": embedder.embed(text, kind)}).encode()
            except EmbeddingError as exc:
                code, payload = 503, json.dumps({"error": exc.code}).encode()
            except Exception:
                code, payload = 400, b'{"error":"bad_request"}'
            self.send_response(code)
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
