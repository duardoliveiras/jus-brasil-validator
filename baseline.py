"""Extrai candidatos a citação dos textos do desafio."""

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FLAGS = re.IGNORECASE
MARCADOR = r"n(?:[º°.]|o)\.?"
DIGITO = r"(?:\d|[OolISsgG](?![A-Za-z]))"
NUMERO = rf"\d(?:{DIGITO}|[\s.,/–-]){{1,50}}{DIGITO}"
UF = r"(?:\s*(?:[/–-]\s*[A-Z]{2}|\(\s*[A-Z]{2}\s*\)))?"

MODIFICADOR = r"(?:EDcl|EDs?|AgInt|AgRg|AgR|Agravo Interno|Embargos de Declaração)"
PREFIXO = rf"(?:{MODIFICADOR}\s+(?:no|nos|na)\s+){{0,5}}"
CLASSE = (
    r"(?:Agravo Interno na Suspensão de Liminar e de Sentença|"
    r"Agravo Regimental no Agravo de Instrumento|"
    r"Agravo em Recurso Especial|Recurso Especial Eleitoral|"
    r"Recurso em Habeas Corpus|Recurso em Mandado de Segurança|"
    r"Recurso Especial|Reclamação|Rec\.?\s*Esp\.?|R\.?Esp\.?|"
    r"AgR-REspe|AgR-AI|AREspEl|AgREsp|A\.?REsp|AREsp|REspe|"
    r"Ag\.?\s*Int\.?|AgInt|AgRg|R-Rp|RHC|RMS|RSE|Rcl|APL|"
    r"RESP|RE|AR|H\.?C\.?)"
)
PROCESSO = re.compile(
    rf"(?<!\w){PREFIXO}{CLASSE}\s*(?:{MARCADOR}\s*)?{NUMERO}{UF}", FLAGS
)
TST = re.compile(
    rf"(?<!\w)(?:processo\s+{MARCADOR}\s*)?"
    rf"(?:TST\s*[-–]\s*)?(?:(?:AgARR|AIRR|ARR|RR|ED|E)\s*[-–]\s*){{1,5}}"
    rf"{NUMERO}", FLAGS
)
SUMULA = re.compile(
    rf"(?<!\w)(?:S[uú]mula|S[uú]m\.?|5[uú]mula)\s*"
    rf"(?:Vinculante\s*)?(?:{MARCADOR}\s*)?\d{{1,4}}"
    r"(?:\s+do\s+(?:STF|STJ|TST|TSE|STM))?", FLAGS
)
FONTE_LEI = (
    rf"(?:Lei(?:\s+Complementar)?\s+{MARCADOR}\s*\d[\d./-]*|"
    r"Constituição\s+(?:da\s+República|Fed[ec]ral)|"
    r"Consolidação\s+das\s+Leis\s+do\s+Trabalho|"
    r"Código\s+(?:Civil|Eleitoral|Penal\s+Militar|de\s+Defesa\s+do\s+Consumidor|"
    r"de\s+Processo\s+(?:Civil|Penal))|CPC|CLT|CPP|CPM|CDC)"
)
LEI = re.compile(
    rf"(?<!\w)art(?:igo)?\.?\s*\d[\d.]*[º°]?"
    rf"(?:,\s*(?:§\s*\d+[º°]?(?:-[A-Z])?|[IVXLCDM]+|'[a-z]')){{0,3}}"
    rf",?\s+d[ao]s?\s+{FONTE_LEI}", FLAGS
)

TRIBUNAL = r"(?:STF|STJ|TSE|TST|STM)"
PALAVRA_NOME = r"(?-i:[A-ZÀ-Ý][A-Za-zÀ-ÿ]*)"
NOME = rf"{PALAVRA_NOME}(?:\s+(?:{PALAVRA_NOME}|(?-i:d[aeo]s?|e))){{1,6}}(?=[,.;\n]|$)"
DESCRITIVAS = [
    rf"julgado\s+do\s+{TRIBUNAL}\s+prof[ec]rido\s+em\s+20\d{{2}}\s+pela\s+relatoria\s+d[ec]\s+{NOME}",
    rf"precedente\s+do\s+{TRIBUNAL}\s+de\s+20\d{{2}},\s+da\s+relatoria\s+de\s+{NOME}",
    rf"acórdão\s+do\s+{TRIBUNAL}\s+julgado\s+em\s+20\d{{2}}\s+sob\s+relatoria\s+de\s+{NOME}",
    rf"(?:Reclamação|Rcl|APL|Recurso\s+em\s+Habeas\s+Corpus)\s+"
    rf"(?:do\s+{TRIBUNAL},?\s*)?de\s+20\d{{2}},\s+Rel\.\s*Min\.\s+{NOME}",
]
PADROES = [(p, "jurisprudencia") for p in (PROCESSO, TST, SUMULA)] + [
    (LEI, "lei")
] + [(re.compile(r"(?<!\w)" + p, FLAGS), "jurisprudencia") for p in DESCRITIVAS]


def extrair(texto, documento_id):
    # separador triplo delimita o cabeçalho sintético; revisar se o formato final mudar.
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
    return escolhidos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)
    cmd = sub.add_parser("extract", help="grava candidatos em JSONL")
    cmd.add_argument("--input", type=Path, default=ROOT / "files/txt")
    cmd.add_argument("--output", type=Path, default=ROOT /
                     "runs/candidatos.jsonl")
    args = parser.parse_args()

    arquivos = sorted(args.input.glob("*.txt"))
    if not arquivos:
        parser.error(f"nenhum .txt encontrado em {args.input}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with args.output.open("w", encoding="utf-8") as saida:
        for arquivo in arquivos:
            with arquivo.open(encoding="utf-8", newline="") as entrada:
                texto = entrada.read()
            for c in extrair(texto, arquivo.stem):
                if texto[c["inicio"]:c["fim"]] != c["trecho"]:
                    raise ValueError(f"span inválido em {arquivo.name}")
                saida.write(json.dumps(c, ensure_ascii=False) + "\n")
                total += 1
    print(f"{args.output}: {total} candidatos em {len(arquivos)} documentos")


if __name__ == "__main__":
    main()
