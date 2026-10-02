from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .guardrails import check_question
from .index import read_meta, search
from .language import MESSAGES, detect_language
from .router import route

CITE = re.compile(r"\[C(\d+)\]")
MAX_CORPORA = 5
MAX_RESULT_ROWS = 25


@dataclass
class Corpus:
    """One selectable research base: a store plus the pinned release it was built from."""
    id: str
    label: str
    store: Any
    dataset_slug: str
    release: str = "v1"
    manifest_sha256: str | None = None


def _norm(hit: dict) -> dict:
    """Generic record view (id, org, municipality, uf, kind, text) for any store."""
    if "numero_controle_pncp" in hit:
        return {"id": hit["numero_controle_pncp"], "org": hit.get("orgao_razao_social"), "municipality": hit.get("nome_municipio"),
                "uf": hit.get("sigla_uf"), "kind": hit.get("modalidade_nome"), "text": hit.get("objeto_compra")}
    return {k: hit.get(k) for k in ("id", "org", "municipality", "uf", "kind", "text")}


def _merge(per_corpus: list[tuple[Corpus, list[dict]]], k: int) -> list[tuple[Corpus, dict]]:
    """Round-robin the best hits of each selected base so every base is represented."""
    merged, rank = [], 0
    while len(merged) < k and any(rank < len(hits) for _, hits in per_corpus):
        for corpus, hits in per_corpus:
            if rank < len(hits) and len(merged) < k:
                merged.append((corpus, _norm(hits[rank])))
        rank += 1
    return merged


@dataclass
class Engine:
    corpora: dict[str, Corpus]
    model: Any = None  # model client or None (cited extractive mode)

    def _model_ready(self) -> bool:
        return self.model is not None and getattr(self.model, "available", lambda: True)()

    def health(self) -> dict:
        items = []
        for corpus in self.corpora.values():
            meta = read_meta(corpus.store)
            items.append({"id": corpus.id, "label": corpus.label, "release_version": corpus.release,
                          "data_cutoff": meta.get("data_cutoff"), "record_count": meta.get("record_count"),
                          "dataset": corpus.dataset_slug})
        first = items[0] if items else {}
        return {"status": "ready" if items else "unavailable", "corpora": items,
                "corpus_name": first.get("label"), "release_version": first.get("release_version"),
                "data_cutoff": first.get("data_cutoff"), "table_count": len(items), "record_count": first.get("record_count"),
                "model_status": "ready" if self._model_ready() else "extractive"}

    def _citation(self, corpus: Corpus, hit: dict, tag: int) -> dict:
        try:
            version = int(corpus.release.lstrip("v").split(".")[0])
        except ValueError:
            version = 1
        c = {"chunk_id": f"C{tag}:{hit['id']}", "document_id": hit["id"],
             "title": f"{hit.get('org') or corpus.label} - {hit['id']}"[:240],
             "source_uri": f"https://www.kaggle.com/datasets/{corpus.dataset_slug}",
             "record_ids": [hit["id"]], "dataset": {"slug": corpus.dataset_slug, "version": version}}
        if corpus.manifest_sha256:
            c["dataset"]["manifest_sha256"] = corpus.manifest_sha256
        return c

    def answer(self, question: str, corpus_ids: list[str] | None = None) -> dict:
        lang = detect_language(question)
        msg = MESSAGES[lang]
        reason = check_question(question)
        if reason == "too_long":
            return {"status": "refused", "answer": msg["too_long"], "citations": [], "safety_reason": reason}
        if reason:
            return {"status": "refused", "answer": msg["refused"], "citations": [], "safety_reason": reason}
        selected = [self.corpora[c] for c in dict.fromkeys(corpus_ids or []) if c in self.corpora][:MAX_CORPORA]
        if not selected:
            return self._ungrounded(question, msg)
        text_bases = [c for c in selected if not getattr(c.store, "is_sql", False)]
        sql_bases = [c for c in selected if getattr(c.store, "is_sql", False)]
        plan = route(question, self.model if self._model_ready() else None, [c.label for c in selected])
        if not plan.in_scope:
            return {"status": "abstained", "answer": msg["off_topic"], "citations": [], "safety_reason": "off_topic", "grounded": True}
        tagged, citations, total = [], [], 0
        # Aggregates go to SQL first; records go to retrieval first. The other side runs only if the first found nothing.
        order = ("sql", "text") if plan.aggregate and sql_bases else ("text", "sql")
        for step in order:
            if tagged:
                break
            if step == "text":
                total += self._retrieve(question, text_bases, msg, tagged, citations)
            else:
                self._query(question, sql_bases, tagged, citations)
        if not tagged:
            reply = msg["needs_sql"] if plan.aggregate and sql_bases else msg["abstain"]
            return {"status": "abstained", "answer": reply, "citations": [], "safety_reason": None, "grounded": True}
        names = ", ".join(c.label for c in selected)
        cutoffs = sorted({str(read_meta(c.store).get("data_cutoff", "?")) for c in selected})
        cov = msg["coverage"].format(profile=names, release=", ".join(sorted({c.release for c in selected})), cutoff=", ".join(cutoffs))
        text = None
        if self._model_ready():
            language = "Brazilian Portuguese" if lang == "pt" else "English"
            text = self.model.complete(f"{question}\n\n(Answer in {language}.)", tagged)
        if text and len(CITE.sub("", text).strip(" .,;:\n")) < 40:
            text = None  # a reply that is little more than citation tags tells the reader nothing
        if text and text != "NO_ANSWER":
            used = {int(n) for n in CITE.findall(text)}
            if used and used <= set(range(1, len(tagged) + 1)):
                cited = [c for c in citations if int(c["chunk_id"].split(":")[0][1:]) in used or "query" in c]
                return {"status": "answered", "answer": f"{text}\n\n{cov}", "citations": cited, "safety_reason": None, "grounded": True}
        if plan.aggregate and sql_bases and not any("query" in c for c in citations):
            # A list of matching notices is not an answer to "how many" or "which has the most".
            return {"status": "abstained", "answer": f"{msg['needs_sql']}\n\n{cov}", "citations": [], "safety_reason": None, "grounded": True}
        body = msg["found"].format(n=total or len(tagged), k=len(tagged)) + "\n" + "\n".join(tagged) + "\n\n" + cov
        return {"status": "answered", "answer": body, "citations": citations, "safety_reason": None, "grounded": True}

    def _retrieve(self, question: str, bases: list[Corpus], msg: dict, tagged: list[str], citations: list[dict]) -> int:
        per_corpus, total = [], 0
        for corpus in bases:
            count, hits = search(corpus.store, question, k=5)
            total += count
            if hits:
                per_corpus.append((corpus, hits))
        for i, (corpus, h) in enumerate(_merge(per_corpus, 5)):
            tag = len(tagged) + 1
            tagged.append(f"[C{tag}] " + msg["record"].format(id=h["id"], orgao=h.get("org") or "-", municipio=h.get("municipality") or "-",
                                                               uf=h.get("uf") or "-", modalidade=h.get("kind") or "-",
                                                               objeto=(h.get("text") or "-")[:220]))
            citations.append(self._citation(corpus, h, tag))
        return total

    def _query(self, question: str, bases: list[Corpus], tagged: list[str], citations: list[dict]) -> None:
        for corpus in bases:
            try:
                result = corpus.store.ask(question, self.model) if self._model_ready() else {"error": "the SQL agent needs the model"}
            except Exception:  # a failing database or model must end in an abstention, not a server error
                result = {"error": "the SQL agent failed"}
            if "error" in result or not result.get("rows"):
                continue
            first = len(tagged) + 1
            for row in result["rows"][:10]:
                tagged.append(f"[C{first}] " + "; ".join(f"{col}={val}" for col, val in zip(result["columns"], row)))
            citations.append({"chunk_id": f"C{first}:sql", "document_id": corpus.id, "title": f"SQL over {corpus.label}"[:240],
                              "source_uri": f"https://www.kaggle.com/datasets/{corpus.dataset_slug}", "record_ids": [corpus.id],
                              "dataset": {"slug": corpus.dataset_slug, "version": 1},
                              "query": {"sql": result["sql"], "columns": result["columns"], "rows": result["rows"][:MAX_RESULT_ROWS],
                                        "explanation": result.get("explanation", "")}})

    def _ungrounded(self, question: str, msg: dict) -> dict:
        """No research base selected: a plain, short model answer with no retrieval and no citations."""
        if not self._model_ready() or not hasattr(self.model, "general"):
            return {"status": "abstained", "answer": msg["pick_base"], "citations": [], "safety_reason": None, "grounded": False}
        text = self.model.general(question)
        if not text:
            return {"status": "abstained", "answer": msg["pick_base"], "citations": [], "safety_reason": None, "grounded": False}
        return {"status": "answered", "answer": text, "citations": [], "safety_reason": None, "grounded": False}
