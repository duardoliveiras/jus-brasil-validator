"""Avalia o baseline no conjunto extra sem misturar desenvolvimento e teste."""

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from baseline import casar, extrair
from files import kaggle_metric
from resolver import Resolvedor
from tfidf_experiment import carregar_extra

ROOT = Path(__file__).resolve().parent


def avaliar(dados, documentos, vagas=False, refinadas=False):
    resolvedor = Resolvedor(ROOT / "files/desafio1_bracis.db")
    solucao, sem_conf, com_conf = [], [], []
    totais = Counter()
    perdidas, espurias, erros_classe = [], [], []
    for doc in sorted(documentos):
        item = dados[doc]
        texto, gold = item["texto"], item["gold"]
        pred = extrair(texto, doc, vagas=vagas, refinadas=refinadas)
        pares, sem_gold, sem_pred = casar(gold, pred)
        totais.update(tp=len(pares), fp=len(sem_pred), fn=len(sem_gold))
        for i in sem_gold:
            g = gold[i]
            perdidas.append(dict(documento_id=doc, classe=g["classificacao"],
                                 trecho=g["trecho"], inicio=g["inicio"],
                                 contexto=texto[max(0, g["inicio"] - 50):g["fim"] + 50]))
        for i in sem_pred:
            p = pred[i]
            espurias.append(dict(documento_id=doc, trecho=p["trecho"],
                                 contexto=texto[max(0, p["inicio"] - 50):p["fim"] + 50]))
        solucao.append(dict(documento_id=doc, nivel=item["nivel"], citacoes="|".join(
            f"{g['inicio']},{g['fim']},{g['classificacao']},{g['id_canonico'] or '-'}"
            for g in gold)))
        blocos = []
        for p in pred:
            if p.get("vago"):
                ident, classe = None, "incompleta"
            else:
                r = resolvedor.resolver(p["trecho"], p["tipo"])
                ident = r["id_canonico"]
                classe = ("real" if ident is not None else "incompleta" if
                          not r["completo"] or len(r["candidatos"]) > 1 else "inventada")
            blocos.append(f"{p['inicio']},{p['fim']},{classe},{ident or '-'}")
        for gi, pi in pares:
            esperado = gold[gi]
            previsto = blocos[pi].split(",")
            if (previsto[2] != esperado["classificacao"] or
                    esperado["classificacao"] == "real" and
                    previsto[3] != esperado["id_canonico"]):
                erros_classe.append(dict(documento_id=doc, trecho=pred[pi]["trecho"],
                                         esperado=esperado["classificacao"],
                                         previsto=previsto[2], id_esperado=esperado["id_canonico"],
                                         id_previsto=previsto[3]))
        sem_conf.append(dict(documento_id=doc, citacoes="|".join(b + ",-" for b in blocos)))
        com_conf.append(dict(documento_id=doc, citacoes="|".join(b + ",1.0000" for b in blocos)))
    tp, fp, fn = (totais[k] for k in ("tp", "fp", "fn"))
    metricas = dict(totais, precisao=tp / (tp + fp) if tp + fp else 0,
                    recall=tp / (tp + fn) if tp + fn else 0,
                    f1=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0)
    solucao = pd.DataFrame(solucao)
    return dict(documentos=len(documentos), extracao=metricas,
                score_sem_confianca=kaggle_metric.avaliar(solucao, pd.DataFrame(sem_conf)),
                score_com_confianca=kaggle_metric.avaliar(solucao, pd.DataFrame(com_conf)),
                perdidas=perdidas, espurias=espurias, erros_classe=erros_classe)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("desenvolvimento", "teste"),
                        default="desenvolvimento")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--vagas", action="store_true", help="inclui referências sem número")
    parser.add_argument("--refinar-vagas", action="store_true",
                        help="ajusta apenas os spans de referências vagas")
    args = parser.parse_args()
    if args.refinar_vagas and not args.vagas:
        parser.error("--refinar-vagas exige --vagas")
    dados, auditoria = carregar_extra(ROOT / "dataset_extra")
    divisao = json.loads((ROOT / "extra_split.json").read_text(encoding="utf-8"))
    desenvolvimento, teste = map(set, (divisao["desenvolvimento"], divisao["teste"]))
    if desenvolvimento & teste or desenvolvimento | teste != dados.keys():
        parser.error("extra_split.json não corresponde aos documentos válidos")
    relatorio = dict(split=args.split, vagas=args.vagas,
                     refinadas=args.refinar_vagas, auditoria=auditoria,
                     **avaliar(dados, divisao[args.split], vagas=args.vagas,
                               refinadas=args.refinar_vagas))
    destino = args.report or ROOT / f"runs/extra_{args.split}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    ex = relatorio["extracao"]
    print(f"{args.split}: {relatorio['documentos']} docs, TP={ex['tp']}, FP={ex['fp']}, "
          f"FN={ex['fn']}, F1={ex['f1']:.4f}; score sem confiança="
          f"{relatorio['score_sem_confianca']['score_final']:.4f}, "
          f"com confiança={relatorio['score_com_confianca']['score_final']:.4f}")
    print(f"Erros: {destino}")


if __name__ == "__main__":
    main()
