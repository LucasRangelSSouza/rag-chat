from __future__ import annotations

import re
import unicodedata

MAX_QUESTION_CHARS = 1000

_INJECTION = [
    r"ignore (all |the )?(previous|prior|above) (instructions|prompts?)",
    r"disregard (all |the )?(previous|prior|above)",
    r"(reveal|show|print|repeat) (your |the )?(system|hidden|initial) (prompt|instructions?)",
    r"you are now", r"act as (an? )?(unrestricted|jailbroken|dan)", r"developer mode", r"jailbreak",
    r"ignore (todas )?(as )?instru[cç][õo]es", r"desconsidere (as )?instru[cç][õo]es",
    r"(revele|mostre|imprima|repita) (o |seu )?(prompt|instru[cç][õo]es) (do sistema|de sistema|inicial)",
    r"voc[eê] agora [eé]", r"finja (que )?(voc[eê] )?(é|e) ",
    r"api[_ -]?key", r"senha|password|token de acesso",
]
_INJECTION_RE = [re.compile(p, re.I) for p in _INJECTION]


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def check_question(question: str) -> str | None:
    """Return None if acceptable, else a reason code: too_long, empty, injection."""
    if not question or not question.strip():
        return "empty"
    if len(question) > MAX_QUESTION_CHARS:
        return "too_long"
    folded = _fold(question)
    for pattern in _INJECTION_RE:
        if pattern.search(question) or pattern.search(folded):
            return "injection"
    return None
