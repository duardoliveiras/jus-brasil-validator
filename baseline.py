"""Extrai, resolve e avalia citações do desafio."""

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FLAGS = re.IGNORECASE
MARCADOR = r"n(?:[º°.]|o)\.?"
DIGITO = r"(?:\d|[OolISsgG](?![A-Za-z]))"
NUMERO = rf"\d(?:{DIGITO}|[\s.,/–-]){{1,50}}{DIGITO}"
UF = r"(?:\s*(?:[/–-]\s*[A-Z]{2}|\(\s*[A-Z]{2}\s*\)))?"

MODIFICADOR = r"(?:EDcl|EDs?|AgInt|AgRg|AgR|Agravo Interno|Embargos de Declaração)"
PREFIXO = rf"(?:Terceiro\s+AG\.REG\s+na\s+|{MODIFICADOR}\s+(?:no|nos|na)\s+){{0,5}}"
CLASSE = (
    r"(?:Agravo\s+Interno\s+na\s+Suspensão\s+de\s+Liminar\s+e\s+de\s+Sentença|"
    r"Agravo Regimental no Agravo de Instrumento|"
    r"Agravo em Recurso Especial|Recurso\s+Especial\s+Eleitoral|"
    r"Recurso em Habeas Corpus|Recurso em Mandado de Segurança|"
    r"Recurso\s+Especial|Reclamação|Recl\.?|Rec\.?\s*Esp\.?|R\.?Esp\.?|"
    r"AgR-REspe|AgR-AI|AREspEl|AgREsp|A\.?REsp|AREsp|REspe\.?|"
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
NOME = rf"{PALAVRA_NOME}(?:\s+(?:{PALAVRA_NOME}|(?-i:d[aeo]s?|e))){{1,6}}"
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



def casar(gabarito, candidatos):
    """Casa spans um a um por maior IoU, com limiar de 0,5."""
    opcoes = []
    for gi, g in enumerate(gabarito):
        for pi, p in enumerate(candidatos):
            intersecao = max(0, min(g["fim"], p["fim"]) - max(g["inicio"], p["inicio"]))
            uniao = (g["fim"] - g["inicio"]) + (p["fim"] - p["inicio"]) - intersecao
            if intersecao * 2 >= uniao:
                opcoes.append((-intersecao / uniao, gi, pi))
    usados_g, usados_p, pares = set(), set(), []
    for _, gi, pi in sorted(opcoes):
        if gi not in usados_g and pi not in usados_p:
            usados_g.add(gi)
            usados_p.add(pi)
            pares.append((gi, pi))
    return (pares,
            [i for i in range(len(gabarito)) if i not in usados_g],
            [i for i in range(len(candidatos)) if i not in usados_p])


def avaliar_extracao(gold_path, pred_path, split):
    with gold_path.open(encoding="utf-8-sig", newline="") as f:
        gabarito = list(csv.DictReader(f))
    validacao = set(json.loads((ROOT / "splits.json").read_text(encoding="utf-8"))["validacao"])
    documentos = {g["documento_id"] for g in gabarito}
    por_doc = defaultdict(list)
    with pred_path.open(encoding="utf-8") as f:
        for linha in f:
            p = json.loads(linha)
            if p["documento_id"] not in documentos:
                raise ValueError(f"predição para documento desconhecido: {p['documento_id']}")
            por_doc[p["documento_id"]].append(p)

    gold_por_doc = defaultdict(list)
    for g in gabarito:
        doc = g["documento_id"]
        if split == "validacao" and doc not in validacao:
            continue
        if split == "desenvolvimento" and doc in validacao:
            continue
        gold_por_doc[doc].append(dict(documento_id=doc, citacao_id=g["citacao_id"],
                                      inicio=int(g["inicio"]), fim=int(g["fim"]),
                                      trecho=g["trecho"].replace("\\n", "\n"), tipo=g["tipo"],
                                      nivel=g["nivel"]))

    resumo = defaultdict(lambda: dict(tp=0, fp=0, fn=0))
    perdidas, espurias = [], []
    for doc, golds in sorted(gold_por_doc.items()):
        preds = por_doc[doc]
        pares, sem_gold, sem_pred = casar(golds, preds)
        nivel = golds[0]["nivel"]
        resumo[nivel]["tp"] += len(pares)
        resumo[nivel]["fn"] += len(sem_gold)
        resumo[nivel]["fp"] += len(sem_pred)
        perdidas.extend(golds[i] for i in sem_gold)
        espurias.extend(preds[i] for i in sem_pred)

    def metricas(c):
        tp, fp, fn = c["tp"], c["fp"], c["fn"]
        return dict(c, precisao=tp / (tp + fp) if tp + fp else 0.0,
                    recall=tp / (tp + fn) if tp + fn else 0.0,
                    f1=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)

    total = {k: sum(c[k] for c in resumo.values()) for k in ("tp", "fp", "fn")}
    return dict(split=split, documentos=len(gold_por_doc),
                por_nivel={n: metricas(resumo[n]) for n in sorted(resumo)},
                total=metricas(total), perdidas=perdidas, espurias=espurias)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)
    cmd = sub.add_parser("extract", help="grava candidatos em JSONL")
    cmd.add_argument("--input", type=Path, default=ROOT / "files/txt")
    cmd.add_argument("--output", type=Path, default=ROOT /
                     "runs/candidatos.jsonl")
    cmd = sub.add_parser("eval-extraction", help="mede a extração por IoU >= 0,5")
    cmd.add_argument("--gold", type=Path, default=ROOT / "files/goldenset_offsets.csv")
    cmd.add_argument("--pred", type=Path, default=ROOT / "runs/candidatos.jsonl")
    cmd.add_argument("--split", choices=("desenvolvimento", "validacao", "todos"),
                     default="desenvolvimento")
    cmd.add_argument("--report", type=Path)
    cmd = sub.add_parser("resolve", help="mede a resolução usando os spans do gabarito")
    cmd.add_argument("--gold", type=Path, default=ROOT / "files/goldenset_offsets.csv")
    cmd.add_argument("--banco", type=Path, default=ROOT / "files/desafio1_bracis.db")
    cmd.add_argument("--split", choices=("desenvolvimento", "validacao", "todos"),
                     default="desenvolvimento")
    cmd.add_argument("--report", type=Path)
    cmd = sub.add_parser("predict", help="gera JSONs e submission.csv")
    cmd.add_argument("--input", type=Path, default=ROOT / "files/txt")
    cmd.add_argument("--banco", type=Path, default=ROOT / "files/desafio1_bracis.db")
    cmd.add_argument("--output", type=Path, default=ROOT / "runs/predicoes")
    cmd.add_argument("--submission", type=Path, default=ROOT / "runs/submission.csv")
    cmd = sub.add_parser("score", help="calcula a métrica oficial no gabarito local")
    cmd.add_argument("--gold", type=Path, default=ROOT / "files/goldenset_offsets.csv")
    cmd.add_argument("--submission", type=Path, default=ROOT / "runs/submission.csv")
    cmd.add_argument("--split", choices=("desenvolvimento", "validacao", "todos"),
                     default="desenvolvimento")
    cmd.add_argument("--report", type=Path)
    args = parser.parse_args()

    if args.comando == "predict":
        from resolver import Resolvedor

        arquivos = sorted(args.input.glob("*.txt"))
        if not arquivos:
            parser.error(f"nenhum .txt encontrado em {args.input}")
        args.output.mkdir(parents=True, exist_ok=True)
        existentes = {p.stem for p in args.output.glob("*.json")}
        extras = existentes - {p.stem for p in arquivos}
        if extras:
            parser.error(f"JSONs antigos em {args.output}: {sorted(extras)}")
        resolvedor = Resolvedor(args.banco)
        total = 0
        for arquivo in arquivos:
            with arquivo.open(encoding="utf-8", newline="") as f:
                texto = f.read()
            citacoes = []
            for c in extrair(texto, arquivo.stem):
                resultado = resolvedor.resolver(c["trecho"], c["tipo"])
                id_canonico = resultado["id_canonico"]
                if id_canonico is not None:
                    classe = "real"
                elif not resultado["completo"] or len(resultado["candidatos"]) > 1:
                    classe = "incompleta"
                else:
                    classe = "inventada"
                citacoes.append({k: c[k] for k in ("inicio", "fim", "trecho", "tipo")} |
                                {"classificacao": classe,
                                 "resolucao": {"id_canonico": id_canonico}
                                 if id_canonico is not None else None})
            (args.output / f"{arquivo.stem}.json").write_text(
                json.dumps({"documento_id": arquivo.stem, "citacoes": citacoes},
                           ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            total += len(citacoes)
        args.submission.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, str(ROOT / "files/json_to_submission.py"),
                        str(args.output), str(args.submission)], check=True)
        print(f"{total} citações em {len(arquivos)} documentos.")
        return

    if args.comando == "score":
        try:
            import pandas as pd
            from files import kaggle_metric as metric
        except ImportError as exc:
            parser.error(f"métrica requer pandas; use .venv/bin/python ({exc})")
        validacao = set(json.loads((ROOT / "splits.json").read_text(encoding="utf-8"))["validacao"])
        por_doc = defaultdict(list)
        niveis = {}
        with args.gold.open(encoding="utf-8-sig", newline="") as f:
            for linha in csv.DictReader(f):
                doc = linha["documento_id"]
                if args.split == "validacao" and doc not in validacao:
                    continue
                if args.split == "desenvolvimento" and doc in validacao:
                    continue
                niveis[doc] = int(linha["nivel"])
                por_doc[doc].append(",".join(
                    (linha["inicio"], linha["fim"], linha["classificacao"],
                     linha["id_canonico"] or "-")))
        solucao = pd.DataFrame(
            [{"documento_id": doc, "nivel": niveis[doc],
              "citacoes": "|".join(por_doc[doc])} for doc in sorted(por_doc)])
        submissao = pd.read_csv(args.submission, keep_default_na=False)
        oficial = metric.avaliar(solucao, submissao)
        sub_por_doc = submissao.set_index("documento_id")["citacoes"]
        matriz, erros = {}, []
        for doc, golds_txt in por_doc.items():
            nivel = str(niveis[doc])
            if nivel not in matriz:
                matriz[nivel] = {
                    "classes": {c: {p: 0 for p in (*metric.CLASSES, "ausente")}
                                for c in metric.CLASSES},
                    "link_errado": 0,
                    "espurias": {c: 0 for c in metric.CLASSES},
                }
            golds = metric._parse_solution_cell("|".join(golds_txt), doc)
            preds = metric._parse_submission_cell(sub_por_doc[doc], doc)
            pares, sem_gold, sem_pred = metric._casar(golds, preds)
            for gi, pi in pares:
                g, p = golds[gi], preds[pi]
                matriz[nivel]["classes"][g["classe"]][p["classe"]] += 1
                link_errado = (g["classe"] == p["classe"] == "real"
                               and p["id_canonico"] not in g["doc_ids"])
                if link_errado:
                    matriz[nivel]["link_errado"] += 1
                if g["classe"] != p["classe"] or link_errado:
                    erros.append(dict(documento_id=doc, erro="classe ou link",
                                      esperado=g["classe"], previsto=p["classe"],
                                      inicio=g["inicio"], fim=g["fim"],
                                      id_previsto=p["id_canonico"]))
            for gi in sem_gold:
                g = golds[gi]
                matriz[nivel]["classes"][g["classe"]]["ausente"] += 1
                erros.append(dict(documento_id=doc, erro="não extraída",
                                  esperado=g["classe"], inicio=g["inicio"], fim=g["fim"]))
            casadas = [golds[gi] for gi, _ in pares]
            for pi in sem_pred:
                p = preds[pi]
                if any(metric._contida(p, g) for g in casadas):
                    continue
                matriz[nivel]["espurias"][p["classe"]] += 1
                erros.append(dict(documento_id=doc, erro="espúria",
                                  previsto=p["classe"], inicio=p["inicio"], fim=p["fim"]))
        relatorio = dict(split=args.split, oficial=oficial, matriz=matriz, erros=erros)
        destino = args.report or ROOT / f"runs/score_report_{args.split}.json"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
        print(f"Score oficial ({args.split}): {oficial['score_final']:.4f}")
        for nivel, dados in oficial["niveis"].items():
            print(f"Nível {nivel}: {dados['score']:.4f} "
                  f"(macro-F1={dados['macro_f1']:.4f}, tau={dados['tau']:.4f})")
        print(f"Matriz e erros: {destino}")
        return

    if args.comando == "resolve":
        from resolver import Resolvedor

        resolvedor = Resolvedor(args.banco)
        validacao = set(json.loads((ROOT / "splits.json").read_text(encoding="utf-8"))["validacao"])
        with args.gold.open(encoding="utf-8-sig", newline="") as f:
            linhas = list(csv.DictReader(f))
        resumo = defaultdict(lambda: dict(reais=0, corretos=0, sem_id=0,
                                          id_errado=0, nao_reais_com_id=0))
        erros = []
        for linha in linhas:
            doc = linha["documento_id"]
            if args.split == "validacao" and doc not in validacao:
                continue
            if args.split == "desenvolvimento" and doc in validacao:
                continue
            resultado = resolvedor.resolver(linha["trecho"].replace("\\n", "\n"),
                                           linha["tipo"])
            contagem = resumo[linha["nivel"]]
            esperado = linha["id_canonico"] or None
            obtido = resultado["id_canonico"]
            if linha["classificacao"] == "real":
                contagem["reais"] += 1
                if str(obtido) == esperado:
                    contagem["corretos"] += 1
                elif obtido is None:
                    contagem["sem_id"] += 1
                else:
                    contagem["id_errado"] += 1
            elif obtido is not None:
                contagem["nao_reais_com_id"] += 1
            if (linha["classificacao"] == "real" and str(obtido) != esperado
                    or linha["classificacao"] != "real" and obtido is not None):
                erros.append(dict(documento_id=doc, citacao_id=linha["citacao_id"],
                                  trecho=linha["trecho"].replace("\\n", "\n"),
                                  classe=linha["classificacao"], esperado=esperado,
                                  **resultado))
        totais = {k: sum(c[k] for c in resumo.values())
                  for k in ("reais", "corretos", "sem_id", "id_errado", "nao_reais_com_id")}
        relatorio = dict(split=args.split, por_nivel=dict(sorted(resumo.items())),
                         total=totais, erros=erros)
        destino = args.report or ROOT / f"runs/resolution_report_{args.split}.json"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
        print(f"IDs corretos: {totais['corretos']}/{totais['reais']}; "
              f"sem ID: {totais['sem_id']}; ID errado: {totais['id_errado']}; "
              f"não reais com ID: {totais['nao_reais_com_id']}")
        print(f"Erros detalhados: {destino}")
        return

    if args.comando == "eval-extraction":
        relatorio = avaliar_extracao(args.gold, args.pred, args.split)
        destino = args.report or ROOT / f"runs/extraction_report_{args.split}.json"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
        for nivel, valores in relatorio["por_nivel"].items():
            print(f"Nível {nivel}: P={valores['precisao']:.3f} "
                  f"R={valores['recall']:.3f} F1={valores['f1']:.3f} "
                  f"(TP={valores['tp']}, FP={valores['fp']}, FN={valores['fn']})")
        print(f"Erros detalhados: {destino}")
        return

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
