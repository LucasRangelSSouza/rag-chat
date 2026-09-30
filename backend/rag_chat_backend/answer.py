from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .guardrails import check_question
from .index import read_meta, search
from .language import MESSAGES, detect_language

CITE = re.compile(r"\[C(\d+)\]")


@dataclass
class Engine:
    db: Any
    profile: str
    release: str
    dataset_slug: str
    manifest_sha256: str | None
    model: Any = None  # model client or None (cited extractive mode)

    def health(self) -> dict:
        meta = read_meta(self.db)
        model_status = "extractive"
        if self.model is not None:
            model_status = "ready" if getattr(self.model, "available", self.model.ready)() else "extractive"
        return {"status": "ready", "corpus_name": self.profile, "release_version": self.release,
                "data_cutoff": meta.get("data_cutoff"), "table_count": meta.get("table_count"),
                "record_count": meta.get("record_count"), "model_status": model_status}

    def _citation(self, hit: dict, tag: int) -> dict:
        try:
            version = int(self.release.lstrip("v").split(".")[0])
        except ValueError:
            version = 1
        c = {"chunk_id": f"C{tag}:{hit['numero_controle_pncp']}", "document_id": hit["numero_controle_pncp"],
             "title": f"{hit.get('orgao_razao_social') or 'PNCP record'} - {hit['numero_controle_pncp']}"[:240],
             "source_uri": f"https://www.kaggle.com/datasets/{self.dataset_slug}",
             "record_ids": [hit["numero_controle_pncp"]], "dataset": {"slug": self.dataset_slug, "version": version}}
        if self.manifest_sha256:
            c["dataset"]["manifest_sha256"] = self.manifest_sha256
        return c

    def answer(self, question: str) -> dict:
        lang = detect_language(question)
        msg = MESSAGES[lang]
        reason = check_question(question)
        if reason == "too_long":
            return {"status": "refused", "answer": msg["too_long"], "citations": [], "safety_reason": reason}
        if reason:
            return {"status": "refused", "answer": msg["refused"], "citations": [], "safety_reason": reason}
        meta = read_meta(self.db)
        total, hits = search(self.db, question, k=5)
        if total == 0 or not hits:
            return {"status": "abstained", "answer": msg["abstain"], "citations": [], "safety_reason": None}
        cov = msg["coverage"].format(profile=self.profile, release=self.release, cutoff=meta.get("data_cutoff", "?"))
        lines = [msg["record"].format(id=h["numero_controle_pncp"], orgao=h.get("orgao_razao_social") or "-",
                                      municipio=h.get("nome_municipio") or "-", uf=h.get("sigla_uf") or "-",
                                      modalidade=h.get("modalidade_nome") or "-",
                                      objeto=(h.get("objeto_compra") or "-")[:220]) for h in hits]
        tagged = [f"[C{i + 1}] {line}" for i, line in enumerate(lines)]
        citations = [self._citation(h, i + 1) for i, h in enumerate(hits)]
        text = None
        if self.model is not None and getattr(self.model, "available", lambda: True)():
            text = self.model.complete(question, tagged)
        if text and text != "NO_ANSWER":
            used = {int(n) for n in CITE.findall(text)}
            if used and used <= set(range(1, len(hits) + 1)):
                cited = [citations[i - 1] for i in sorted(used)]
                return {"status": "answered", "answer": f"{text}\n\n{cov}", "citations": cited, "safety_reason": None}
        body = msg["found"].format(n=total, k=len(hits)) + "\n" + "\n".join(tagged) + "\n\n" + cov
        return {"status": "answered", "answer": body, "citations": citations, "safety_reason": None}
