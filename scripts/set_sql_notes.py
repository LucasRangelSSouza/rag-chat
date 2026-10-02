"""Writes the per-base notes the SQL agent sends to the model into RAG_EXTRA_CORPORA of an env file.

usage: python set_sql_notes.py /opt/rag-chat/.env
"""
import json
import sys

PNCP_SQL = (
    "obt_pncp_contratos has one row per contract. The contract value is valor_global, in nominal BRL. Filter the year with "
    "ano_contrato BETWEEN 2021 AND 2026 (a few rows hold malformed years). nome_municipio and sigla_uf are the municipality "
    "and state of the contracting body. The supplier is nome_razao_social_fornecedor (document ni_fornecedor). "
    "orgao_esfera_id: M municipal, E state, F federal, D federal district, N not informed. orgao_poder_id: E executive, "
    "L legislative, J judiciary, N not informed. Search the contract object with objeto_contrato ILIKE '%term%' (a trigram "
    "index makes this fast); Portuguese words carry accents, so use a stem without the accented letters, for example "
    "'%licita%' or '%softwar%'. Some valor_global values are data-entry errors in the trillions: for sums, averages and "
    "rankings by value add valor_global < 1e10 and say in the explanation that values above 10 billion BRL were excluded. "
    "obt_pncp_atas has one row per price registration (ata): ano_ata, cancelado, objeto_contratacao, nome_orgao. "
    "Return names, never only codes, and always select the measure (the count or the sum) next to the names. "
    "'Por estado' or 'by state' means GROUP BY sigla_uf; orgao_esfera_id is the level of government, not the state."
)

SIOPE_EXTRA = (
    " Years available: 2021 to 2025 only (2025 partial); when a question asks for earlier years, answer with the years that "
    "exist. Always return municipality names (nome_municipio from obt_ibge_municipio or from the siope tables), never only "
    "codes. Per-student values above 100000 BRL are data-entry errors: exclude valor > 100000 from rankings and say so. "
    "Indicator codes in obt_fnde_siope_indicador_municipio_ano (codigo_indicador is text): '24' share of tax revenue applied "
    "in MDE, legal minimum 25 percent; '35' education spending as a share of all spending; '57' investment per student; "
    "'44' per student in early childhood education, '45' in primary education, '46' in secondary education; '28' share of "
    "FUNDEB spent on early childhood education; '36' school meals as a share of education spending; '67' share of FUNDEB "
    "paid to education professionals, legal minimum 70 percent. Filter esfera = 'Municipal' and keep the highest num_periodo "
    "per municipality and year. Subfunction values in obt_fnde_siope_despesa_funcao_municipio_ano start with a code, such "
    "as '365 - Educação Infantil (Creche)', '361 - Ensino Fundamental', '306 - Alimentação e Nutrição', '782 - Transporte "
    "Escolar'; match them with subfuncao LIKE '365%'."
)


def main(path: str) -> None:
    lines = open(path, encoding="utf-8").read().splitlines()
    for i, line in enumerate(lines):
        if line.startswith("RAG_EXTRA_CORPORA="):
            corpora = json.loads(line.split("=", 1)[1])
            for base in corpora:
                if base["id"] == "pncp-sql":
                    base["notes"] = PNCP_SQL
                elif base["id"] == "siope" and SIOPE_EXTRA.strip() not in base.get("notes", ""):
                    base["notes"] = base.get("notes", "") + SIOPE_EXTRA
            lines[i] = "RAG_EXTRA_CORPORA=" + json.dumps(corpora, ensure_ascii=False)
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("notes set")


if __name__ == "__main__":
    main(sys.argv[1])
