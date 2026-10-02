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
    "L legislative, J judiciary, N not informed. Compare every text value without accents and in upper case on both sides, using the database function "
    "public.f_unaccent: to search the contract object write public.f_unaccent(upper(objeto_contrato)) LIKE "
    "public.f_unaccent(upper('%ambulância%')), and to match a municipality write public.f_unaccent(upper(nome_municipio)) = "
    "public.f_unaccent(upper('Goiânia')) together with sigla_uf. Indexes exist for exactly these expressions, so keep "
    "them as written. For price registrations use public.f_unaccent(upper(objeto_contratacao)). "
    "Contract objects are written in Portuguese procurement language: translate the topic of an English question and "
    "combine the usual synonyms with OR, for example school meals = '%merenda%' OR '%alimentacao escolar%' OR '%pnae%'; "
    "school transport = '%transporte escolar%'; school uniforms = '%uniforme%'; fuel = '%combust%'; medicines = "
    "'%medicamento%'; ambulance = '%ambulanc%'; software = '%software%' OR '%sistema de gestao%'. "
    "Some valor_global values are data-entry errors (billions for small purchases): for sums, "
    "averages and rankings by value add valor_global < 1e9 and say in the explanation that contracts above 1 billion BRL "
    "were excluded. "
    "obt_pncp_atas has one row per price registration (ata): ano_ata, cancelado, objeto_contratacao, nome_orgao. "
    "Return names, never only codes, and always select the measure (the count or the sum) next to the names. "
    "'Por estado' or 'by state' means GROUP BY sigla_uf; orgao_esfera_id is the level of government, not the state. "
    "Filter places with sigla_uf, which is indexed together with ano_contrato; never filter by nome_regiao, which is slow. "
    "Regions as states: Norte AC, AM, AP, PA, RO, RR, TO; Nordeste AL, BA, CE, MA, PB, PE, PI, RN, SE; Centro-Oeste DF, GO, "
    "MS, MT; Sudeste ES, MG, RJ, SP; Sul PR, RS, SC."
)

SIOPE_EXTRA = (
    " Years available: 2021 to 2025 only (2025 partial); when a question asks for earlier years, answer with the years that "
    "exist. Always return municipality names (nome_municipio from obt_ibge_municipio or from the siope tables), never only "
    "codes. Match names without accents and in upper case on both sides: public.f_unaccent(upper(nome_municipio)) = "
    "public.f_unaccent(upper('Goiânia')). Per-student values above 100000 BRL are data-entry errors: exclude valor > 100000 from rankings and say so. "
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
                elif base["id"] == "siope":
                    # Keep the original notes, replace any earlier version of the extra block.
                    base["notes"] = base.get("notes", "").split(" Years available:")[0] + SIOPE_EXTRA
            lines[i] = "RAG_EXTRA_CORPORA=" + json.dumps(corpora, ensure_ascii=False)
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("notes set")


if __name__ == "__main__":
    main(sys.argv[1])
