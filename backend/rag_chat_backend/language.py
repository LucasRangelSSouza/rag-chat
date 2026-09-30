from __future__ import annotations

import re

_PT = {"o", "a", "os", "as", "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas", "que", "quais", "qual",
       "quantos", "quantas", "para", "por", "com", "um", "uma", "sobre", "existem", "tem", "há", "ha", "são", "sao",
       "licitações", "licitacoes", "contratações", "contratacoes", "compras", "órgão", "orgao", "município", "municipio",
       "abertas", "prazo", "valor", "quanto", "onde", "como", "me", "mostre", "liste", "você", "voce", "estado"}
_EN = {"the", "of", "in", "on", "what", "which", "how", "many", "much", "are", "is", "there", "for", "with", "about",
       "show", "list", "procurements", "procurement", "tenders", "purchases", "agency", "municipality", "open",
       "deadline", "value", "where", "me", "you", "state", "and", "to", "any", "does", "do"}
_WORD = re.compile(r"[a-zA-ZÀ-ÿ]+")


def detect_language(text: str) -> str:
    """Return 'pt' or 'en'. Portuguese wins ties because the corpus is Brazilian."""
    words = [w.lower() for w in _WORD.findall(text)]
    pt = sum(w in _PT for w in words) + sum(1 for w in words if any(c in w for c in "ãõçáéíóúâêô"))
    en = sum(w in _EN for w in words)
    return "en" if en > pt else "pt"


MESSAGES = {
    "en": {
        "abstain": "The released PNCP corpus does not contain enough matching records to support an answer to this question.",
        "refused": "This assistant only answers research questions about the released PNCP records. It cannot follow instructions that change its role or reveal its configuration.",
        "too_long": "Enter a question of up to 1,000 characters.",
        "pick_base": "Select at least one research base to get a sourced answer.",
        "found": "Found {n} matching records in the released corpus (showing the {k} best matches):",
        "coverage": "Coverage: {profile}, release {release}, data through {cutoff}.",
        "record": "{id} | {orgao} | {municipio}/{uf} | {modalidade} | {objeto}",
    },
    "pt": {
        "abstain": "O corpus PNCP publicado não tem registros suficientes para sustentar uma resposta a esta pergunta.",
        "refused": "Este assistente só responde perguntas de pesquisa sobre os registros PNCP publicados. Ele não segue instruções que mudem seu papel nem revela sua configuração.",
        "too_long": "Digite uma pergunta de até 1.000 caracteres.",
        "pick_base": "Selecione ao menos uma base de pesquisa para receber uma resposta com fontes.",
        "found": "Encontrei {n} registros correspondentes no corpus publicado (mostrando os {k} melhores):",
        "coverage": "Cobertura: {profile}, versão {release}, dados até {cutoff}.",
        "record": "{id} | {orgao} | {municipio}/{uf} | {modalidade} | {objeto}",
    },
}
