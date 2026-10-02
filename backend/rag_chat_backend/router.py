"""Question router: decides, before any retrieval, whether a question is in scope and whether it asks for
an aggregate (a count, total, ranking or average, answered by SQL) or for records (answered by retrieval).

The model classifies when it is available. Without it, a keyword rule classifies the kind and every
question is treated as in scope, because a wrong refusal costs more than a weak answer.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

ROUTE_SYSTEM = (
    "You route questions for a research chat over Brazilian public data. The selected bases are listed below. "
    "Decide two things. scope: \"in\" when the question asks about the data in those bases (procurement notices, "
    "contracts, suppliers, public bodies, municipalities, education spending, or the bases themselves), \"out\" when it "
    "asks about anything else (general knowledge, other countries, chit-chat, coding help). kind: \"aggregate\" when the "
    "answer is a number or a ranking computed over many records (how many, total, sum, average, median, which has the "
    "most or least, top N, share), \"records\" when the answer is specific records or their content. "
    "Answer with JSON only: {\"scope\": \"in\"|\"out\", \"kind\": \"aggregate\"|\"records\"}."
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


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def keyword_route(question: str) -> Route:
    return Route(in_scope=True, aggregate=bool(_AGGREGATE.search(_fold(question))), by_model=False)


def route(question: str, model, base_labels: list[str]) -> Route:
    """Classify with the model when it answers valid JSON; otherwise fall back to the keyword rule."""
    if model is None or not hasattr(model, "chat_json"):
        return keyword_route(question)
    reply = model.chat_json(ROUTE_SYSTEM, "Selected bases: " + "; ".join(base_labels) + f"\n\nQuestion: {question}")
    if not reply or reply.get("scope") not in {"in", "out"} or reply.get("kind") not in {"aggregate", "records"}:
        return keyword_route(question)
    return Route(in_scope=reply["scope"] == "in", aggregate=reply["kind"] == "aggregate", by_model=True)
