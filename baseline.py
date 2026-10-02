"""Extrai e valida citações jurídicas, gerando o CSV de submissão."""

import argparse
import csv
import re
import os
import sqlite3
import tempfile
from pathlib import Path


FLAGS = re.IGNORECASE
MARCADOR = r"n(?:\.?\s*[º°]|\s*o|\.)\.?"
DIGITO = r"(?:\d|[OolISsgG](?![A-Za-z]))"
NUMERO = rf"(?:\d|[lIO](?=[\d.]))(?:{DIGITO}|[\s.,/–-]){{1,50}}{DIGITO}"
UF = r"(?:\s*(?:[/–-]\s*[A-Z]{2}|\(\s*[A-Z]{2,3}\s*\)))?"

MODIFICADOR = (r"(?:EDcl|EDs?|AgInt|AgRg|AgR|AG\.?\s*REG\.?|EMB\.?\s*DECL\.?|"
              r"Agravo Interno|Agravo Regimental|Embargos de Declaração)")
PREFIXO = rf"(?:Terceiro\s+AG\.?REG\.?\s+na\s+|{MODIFICADOR}\s+(?:no|nos|na)\s+){{0,5}}"
CLASSE = (
    r"(?:Agravo\s+Interno\s+na\s+Suspensão\s+de\s+Liminar\s+e\s+de\s+Sentença|"
    r"Agravo\s+Regimental\s+no\s+Agravo\s+de\s+Instrumento|"
    r"Embargos\s+Infringentes\s+e\s+de\s+Nulidade|"
    r"Agravo\s+em\s+Recurso\s+Especial|Recurso\s+Especial\s+Eleitoral|"
    r"Recurso\s+em\s+Habeas\s*(?:/\s*)?Corpus|Recurso\s+em\s+Mandado\s+de\s+Segurança|"
    r"Recurso\s+Especial|Recurso\s+Esp\.?|Recurso\s+Extraordinário|"
    r"Recurso\s+Ordinário|Mandado\s+de\s+Segurança|Conflito\s+de\s+Competência|"
    r"Habeas\s+Corpus|Ação\s+Rescisória|Apelação(?:\s+(?:Criminal|Cível))?|"
    r"Agravo\s+Interno|Reclamação|Recl\.?|Rec\.?\s*Esp\.?|R\.?Esp\.?|"
    r"AgR-REspEl|AgR-REspe|AgR-AI|AREspEl|AgREsp|A\.?REsp|AREsp|REspEl|REspe\.?|"
    r"Ag\.?\s*Int\.?|AgInt|AgRg|R-Rp|RHC|RMS|RSE|Rcl|APL|"
    r"EREsp|RESP|RE\.?|ARE|RO|EIN|CP|AR|H\.?C\.?)"
)
PROCESSO = re.compile(
    rf"(?<!\w){PREFIXO}{CLASSE}\s*(?:{MARCADOR}\s*)?{NUMERO}{UF}", FLAGS
)
TST = re.compile(
    rf"(?<!\w)(?:processo\s+{MARCADOR}\s*)?"
    rf"(?:TST\s*[-–]\s*)?(?:(?:AgARR|AIRR|ARR|RRAg|ROT|RR|Ag|ED|E)\s*[-–]\s*){{1,5}}"
    rf"{NUMERO}", FLAGS
)
TEMA = re.compile(
    r"(?<!\w)Tem[aã]\s*(?:n[º°.]?\s*)?\d[\d.]*\s+da\s+repercuss[aã]o\s+geral", FLAGS
)
SUMULA = re.compile(
    rf"(?<!\w)(?:S[uú]mula|S[uú]m\.?|5[uú]mula)\s*"
    rf"(?:Vinculante\s*)?(?:{MARCADOR}\s*)?\d{{1,4}}"
    r"(?:\s*(?:/\s*)?do\s+(?:STF|STJ|TST|TSE|STM|"
    r"Superior\s+Tribunal\s+(?:de\s+Justiça|Militar|Eleitoral|do\s+Trabalho)|"
    r"Supremo\s+Tribunal\s+Federal))?", FLAGS
)
FONTE_LEI = (
    rf"(?:Lei(?:\s+Complementar)?\s+(?:{MARCADOR}\s*)?\d(?:[\d./-]*\d)?|"
    r"Lei\s+das\s+Eleições|CF\s*/\s*88|"
    r"Constitui\w+\s+(?:da\s+República|Fed[ec]ral)|"
    r"Consolidação\s+das\s+Leis\s+do\s+Trabalho|"
    r"Estatuto\s+da\s+Criança\s+e\s+do\s+Adolescente|"
    r"Código(?:\s+(?:Civil|Eleitoral|Penal\s+Militar|de\s+Defesa\s+do\s+Consumidor|"
    r"de\s+Processo\s+(?:Civil|Penal)))?|CPC|CLT|CPP|CPM|CDC)"
)
LEI = re.compile(
    rf"(?<!\w)art(?:igo)?\.?\s*\d[\d.]*(?:-[A-Z])?[º°]?"
    rf"(?:,\s*(?:§\s*\d+[º°]?(?:-[A-Z])?|(?:inciso\s+)?[IVXLCDM]+|'[a-z]'|[a-z])){{0,3}}"
    rf",?\s+d[ao]s?\s+{FONTE_LEI}", FLAGS
)
TRIBUNAL = r"(?:STF|STJ|TSE|TST|STM)"
PALAVRA_NOME = r"(?-i:[A-ZÀ-Ý][A-Za-zÀ-ÿ]*)"
NOME = rf"{PALAVRA_NOME}(?:\s+(?:{PALAVRA_NOME}|(?-i:d[aeo]s?|e))){{1,6}}"
DESCRITIVAS = [
    rf"julgado\s+do\s+{TRIBUNAL}\s+prof[ec]rido\s+em\s+20\d{{2}}\s+pela\s+relatoria\s+d[ec]\s+{NOME}",
    rf"precedente\s+do\s+{TRIBUNAL}\s+de\s+20\d{{2}},\s+da\s+relatoria\s+de\s+{NOME}",
    rf"acórdão\s+do\s+{TRIBUNAL}\s+julgado\s+em\s+20\d{{2}}\s+sob\s+relatoria\s+de\s+{NOME}",
    rf"(?:Reclamação|Rcl|APL|Recurso\s+em\s+Habeas\s+Corpus|Agravo\s+em\s+Recurso\s+Especial)\s+"
    rf"(?:do\s+{TRIBUNAL},?\s*)?de\s+20\d{{2}},\s+Rel\.\s*Min\.\s+{NOME}",
]
PADROES = [(p, "jurisprudencia") for p in (PROCESSO, TST, SUMULA, TEMA)] + [
    (LEI, "lei")
] + [(re.compile(r"(?<!\w)" + p, FLAGS), "jurisprudencia") for p in DESCRITIVAS]


# Referências sem identificador: no gabarito extra elas são citações incompletas.
FIM_VAGO = r"(?:(?![,.;:!?]|\n\s*\n)[\s\S]){8,100}"
ALVO_VAGO = r"(?:STJ|STF|TST|TSE|STM|Corte|Tribun\w+|Turma|Se[cç][aã]o|Plen[aá]rio|Supremo|recurso|C[oó]digo|Lei|repercuss[aã]o)"
RELATOR_VAGO = re.compile(
    rf"(?<!\w)(?:ac[oó]rd[aã]o|decis[aã]o|entendimento)\b[\s\S]{{0,80}}?"
    rf"(?:relatad[oa]\s+pel[oa]\s+(?:Min(?:istro|istra)?\.?\s*)?|"
    rf"da\s+relatoria\s+de\s+|Rel\.\s*Min\.\s*){NOME}", FLAGS
)
VAGO_NAO_CITACAO = re.compile(
    r"^(?:orientação\s+dos\s+tribunais\s+superiores\s+é\s+firme|"
    r"julgad[oa]\s+(?:pel[oa]|por)|ac[oó]rd[aã]o\s+(?:recorrido|regional)|"
    r"decis[aã]o\s+(?:agravada|reclamada)|tese\s+(?:ora\s+sustentada|"
    r"firmada\s+em\s+recurso\s+repetitivo))\b", FLAGS
)
VAGAS = [
    (RELATOR_VAGO, "jurisprudencia"),
    (re.compile(r"(?<!\w)precedente\s+(?:STF|STJ|TST|TSE|STM)\b"
                r"[\s\S]{0,90}?\bsem\s+n[uú]mero\s+completo", FLAGS), "jurisprudencia"),
    (re.compile(r"(?<!\w)dispositivo\s+legal\b"
                r"[\s\S]{0,90}?\bsem\s+artigo\s+nem\s+n[uú]mero\s+de\s+lei", FLAGS), "lei"),
    (re.compile(rf"(?<!\w)(?:jurisprud[êe]ncia|orienta[çc][aã]o|entendimento|"
                rf"precedentes?|julgados?|ac[oó]rd[aã]o|decis[aã]o|tese|recurso\s+especial)\b"
                rf"(?=[^,.;:!?]{{0,100}}{ALVO_VAGO}){FIM_VAGO}", FLAGS), "jurisprudencia"),
    (re.compile(rf"(?<!\w)(?:regra|dispositivo|artigo)\b"
                rf"(?=[^,.;:!?]{{0,100}}(?:C[oó]digo|CPC|CLT|Lei|Estatuto)){FIM_VAGO}", FLAGS), "lei"),
]


VAGAS_REFINADAS = [
    (re.compile(r"(?<!\w)(?:reiterados\s+)?(?:precedentes?|jurisprud[êe]ncia|"
                r"orienta[çc][aã]o|entendimento|tese)\b[\s\S]{0,65}?"
                r"(?:Tribunal\s+Superior\s+(?:do\s+Trabalho|Eleitoral)|"
                r"Superior\s+Tribunal\s+(?:de\s+Justiça|Militar)|"
                r"(?:Primeira|Segunda|Terceira)\s*(?:/\s*)?(?:Turma|Seção)"
                r"(?:\s+do\s+(?:STJ|STF|TST|TSE|STM))?|"
                r"desta\s*(?:/\s*)?Corte(?:\s+(?:Militar|castrense))?|"
                r"Supremo\s+em\s+tema\s+de\s+repercussão\s+geral)", FLAGS),
     "jurisprudencia"),
]


def extrair(texto, documento_id):
    # ponytail: cabeçalho sintético usa separador triplo; rever se o formato mudar.
    separador = texto.find("\n\n\n")
    inicio_corpo = separador + 3 if separador >= 0 else 0
    candidatos = []
    for padrao, tipo in PADROES:
        for match in padrao.finditer(texto, inicio_corpo):
            candidatos.append((match.start(), match.end(), tipo))

    escolhidos = []
    for inicio, fim, tipo in sorted(candidatos, key=lambda c: (c[0], -(c[1] - c[0]))):
        if escolhidos and inicio < escolhidos[-1]["fim"]:
            continue
        escolhidos.append(dict(documento_id=documento_id, inicio=inicio, fim=fim,
                               trecho=texto[inicio:fim], tipo=tipo))
    padroes = VAGAS[:3] + VAGAS_REFINADAS + VAGAS[3:]
    for padrao, tipo in padroes:
        for match in padrao.finditer(texto, inicio_corpo):
            inicio, fim = match.span()
            trecho = texto[inicio:fim]
            if padrao is VAGAS_REFINADAS[0][0] and re.match(
                    r"\s+(?:relatad[oa]|sobre|que)\b", texto[fim:], FLAGS):
                if not re.search(r"\b(?:Corte|Seção|Turma)\b", trecho, FLAGS) or re.match(
                        r"\s+relatad[oa]\b", texto[fim:], FLAGS):
                    continue
            if re.match(r"decis[aã]o\s+recorrida\b", trecho, FLAGS):
                continue
            if trecho.isupper() or VAGO_NAO_CITACAO.search(trecho):
                continue
            if any(inicio < c["fim"] and fim > c["inicio"] for c in escolhidos):
                continue
            escolhidos.append(dict(documento_id=documento_id, inicio=inicio, fim=fim,
                                   trecho=texto[inicio:fim], tipo=tipo, vago=True))
    return sorted(escolhidos, key=lambda c: c["inicio"])


def prever(banco, pasta, saida):
    from resolver import Resolvedor

    if not banco.is_file():
        raise ValueError(f"banco não encontrado: {banco}")
    if not pasta.is_dir():
        raise ValueError(f"pasta de textos não encontrada: {pasta}")
    arquivos = sorted(pasta.glob("*.txt"))
    if not arquivos:
        raise ValueError(f"nenhum .txt encontrado em {pasta}")
    if saida.resolve() in {banco.resolve(), *(p.resolve() for p in arquivos)}:
        raise ValueError("a saída não pode sobrescrever uma entrada")
    resolvedor = Resolvedor(banco)
    saida.parent.mkdir(parents=True, exist_ok=True)
    temporario = None
    total = 0
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                         dir=saida.parent, delete=False) as csvfile:
            temporario = Path(csvfile.name)
            writer = csv.writer(csvfile)
            writer.writerow(["documento_id", "citacoes"])
            for arquivo in arquivos:
                with arquivo.open(encoding="utf-8", newline="") as entrada:
                    texto = entrada.read()
                blocos = []
                for c in extrair(texto, arquivo.stem):
                    ident, classe = None, "incompleta"
                    if not c.get("vago"):
                        r = resolvedor.resolver(c["trecho"], c["tipo"])
                        ident = r["id_canonico"]
                        classe = ("real" if ident is not None else "incompleta" if
                                  not r["completo"] or len(r["candidatos"]) > 1 else "inventada")
                    blocos.append(f"{c['inicio']},{c['fim']},{classe},"
                                  f"{ident if ident is not None else '-'},1.0000")
                writer.writerow([arquivo.stem, "|".join(blocos) or "-"])
                total += len(blocos)
        os.replace(temporario, saida)
    finally:
        if temporario is not None:
            temporario.unlink(missing_ok=True)
    return len(arquivos), total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("banco", type=Path, help="base SQLite original")
    parser.add_argument("textos", type=Path, help="pasta com arquivos .txt UTF-8")
    parser.add_argument("saida", type=Path, help="CSV de saída")
    args = parser.parse_args()
    try:
        documentos, citacoes = prever(args.banco, args.textos, args.saida)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"erro: {exc}\n")
    print(f"{args.saida}: {documentos} documentos, {citacoes} citações.")


if __name__ == "__main__":
    main()
