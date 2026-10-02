"""Question router: one model call, before any retrieval, decides

- scope: whether the question is about the selected bases at all;
- kind: "aggregate" (a count, total, ranking or average, answered by SQL), "records" (specific records, answered by
  retrieval) or "mixed" (both in one question);
- standalone: the question rewritten to stand alone, using the earlier questions of the conversation, so a follow-up
  such as "and in 2023?" is searched as a full question;
- bases: which of the selected bases the question needs.

Without the model, a keyword rule classifies the kind, every selected base is used and every question is in scope,
because a wrong refusal costs more than a weak answer.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

ROUTE_SYSTEM = (
    "You route questions for a research chat over Brazilian public data. The selected bases are listed below with their ids, "
    "followed by the earlier questions of the conversation, oldest first, and the new question. Decide: "
    "scope: \"in\" when the new question asks about the data in those bases (procurement notices, contracts, suppliers, "
    "public bodies, municipalities, education spending, or the bases themselves) or follows up on an earlier question, "
    "\"out\" when it asks about anything else (general knowledge, other countries, chit-chat, coding help). "
    "standalone: the new question rewritten as a complete question in its own language, filling in what a follow-up leaves "
    "out (place, year, topic) from the earlier questions; repeat it unchanged when it already stands alone. "
    "kind: \"aggregate\" when the answer is a number or a ranking computed over many records (how many, total, sum, average, "
    "median, which has the most or least, top N, share, comparison of totals), \"records\" when the answer is specific "
    "records or their content, \"mixed\" when the question asks for both. "
    "numeric_part: when kind is \"mixed\", the part of the standalone question that asks for the number, written as a "
    "complete question; otherwise an empty string. "
    "bases: the ids of the selected bases needed to answer; notice search answers records about published notices, the "
    "contracts base answers counts and values of contracts and price registrations, the education base answers education "
    "spending by municipality. "
    "Answer with JSON only: {\"scope\": \"in\"|\"out\", \"standalone\": \"...\", \"kind\": \"aggregate\"|\"records\"|\"mixed\", "
    "\"numeric_part\": \"...\", \"bases\": [\"id\", ...]}."
)

_AGGREGATE = re.compile(
    r"\b(quant[oa]s?|total|soma|somad[oa]|media|mediana|ranking|maior(es)?|menor(es)?|mais|menos|top \d+|percentual|"
    r"proporcao|participacao|how many|how much|number of|sum|average|mean|median|most|least|largest|smallest|"
    r"highest|lowest|share|count)\b"
)


@dataclass(frozen=True)
class Route:
    in_scope: bool
    aggregate: bool
    by_model: bool
    mixed: bool = False
    standalone: str = ""
    bases: tuple[str, ...] = field(default_factory=tuple)
    numeric_part: str = ""


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def keyword_route(question: str, base_ids: list[str] | None = None) -> Route:
    return Route(in_scope=True, aggregate=bool(_AGGREGATE.search(_fold(question))), by_model=False,
                 standalone=question, bases=tuple(base_ids or ()))


def route(question: str, model, bases: list[tuple[str, str]] | list[str], history: list[str] | None = None) -> Route:
    """Classify with the model when it answers valid JSON; otherwise fall back to the keyword rule.

    `bases` is a list of (id, label) pairs; a plain list of labels is accepted for older callers.
    """
    pairs = [b if isinstance(b, tuple) else (b, b) for b in bases]
    ids = [i for i, _ in pairs]
    if model is None or not hasattr(model, "chat_json"):
        return keyword_route(question, ids)
    earlier = "\n".join(f"- {h}" for h in (history or [])[-4:]) or "(none)"
    prompt = ("Selected bases:\n" + "\n".join(f"- {i}: {label}" for i, label in pairs)
              + f"\n\nEarlier questions:\n{earlier}\n\nNew question: {question}")
    reply = model.chat_json(ROUTE_SYSTEM, prompt)
    if not reply or reply.get("scope") not in {"in", "out"} or reply.get("kind") not in {"aggregate", "records", "mixed"}:
        return keyword_route(question, ids)
    standalone = reply.get("standalone") if isinstance(reply.get("standalone"), str) and reply["standalone"].strip() else question
    chosen = tuple(b for b in (reply.get("bases") or []) if b in ids) or tuple(ids)
    numeric = reply.get("numeric_part") if isinstance(reply.get("numeric_part"), str) else ""
    return Route(in_scope=reply["scope"] == "in", aggregate=reply["kind"] in {"aggregate", "mixed"}, by_model=True,
                 mixed=reply["kind"] == "mixed", standalone=standalone.strip()[:1000], bases=chosen,
                 numeric_part=numeric.strip()[:1000])
