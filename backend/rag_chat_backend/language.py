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
        "abstain": "The selected research bases do not contain enough matching records to support an answer to this question. Try other words, another base, or a narrower period or place.",
        "refused": "This assistant only answers research questions about the released public data. It cannot follow instructions that change its role or reveal its configuration.",
        "too_long": "Enter a question of up to 1,000 characters.",
        "pick_base": "Select at least one research base to get a sourced answer.",
        "off_topic": "This question is outside the selected research bases. Ask about Brazilian procurement notices, contracts or education spending, or clear the bases for a general answer without sources.",
        "needs_sql": "This question asks for a count, total or ranking, and no SQL base returned a result for it. Select a SQL base (contracts or education spending) to get a computed answer; a list of matching notices would not answer it.",
        "sql_result": "SQL query result (open \"SQL and result\" below to see the query):",
        "found": "Found {n} matching records in the selected bases (showing the {k} best matches):",
        "coverage": "Coverage: {profile}, release {release}, data through {cutoff}.",
        "record": "{id} | {orgao} | {municipio}/{uf} | {modalidade} | {objeto}",
    },
    "pt": {
        "abstain": "As bases selecionadas não têm registros suficientes para sustentar uma resposta a esta pergunta. Tente outras palavras, outra base ou um período ou lugar mais específico.",
        "refused": "Este assistente só responde perguntas de pesquisa sobre os dados públicos publicados. Ele não segue instruções que mudem seu papel nem revela sua configuração.",
        "too_long": "Digite uma pergunta de até 1.000 caracteres.",
        "pick_base": "Selecione ao menos uma base de pesquisa para receber uma resposta com fontes.",
        "off_topic": "Esta pergunta está fora das bases de pesquisa selecionadas. Pergunte sobre editais, contratos ou gasto com educação, ou desmarque as bases para receber uma resposta geral sem fontes.",
        "needs_sql": "Esta pergunta pede uma contagem, um total ou um ranking, e nenhuma base SQL devolveu resultado. Selecione uma base SQL (contratos ou gasto com educação) para receber uma resposta calculada; uma lista de editais não responderia a pergunta.",
        "sql_result": "Resultado da consulta SQL (abra \"SQL and result\" abaixo para ver a consulta):",
        "found": "Encontrei {n} registros correspondentes nas bases selecionadas (mostrando os {k} melhores):",
        "coverage": "Cobertura: {profile}, versão {release}, dados até {cutoff}.",
        "record": "{id} | {orgao} | {municipio}/{uf} | {modalidade} | {objeto}",
    },
}
