"""Etapa 6: compara regex e filtro TF-IDF sem alterar a submissão principal."""

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

from baseline import casar, extrair
from files import kaggle_metric
from resolver import Resolvedor

ROOT = Path(__file__).resolve().parent


def ler_texto(caminho):
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return arquivo.read()


def carregar_extra(pasta):
    planilha = pd.read_excel(pasta / "dataset.xlsx", dtype=str).fillna("")
    dados = {}
    auditoria = dict(linhas=len(planilha), documentos=planilha.documento_id.nunique(),
                     classes=dict(Counter(planilha.classificacao)),
                     corpus_compartilhado_sem_offsets=sum(
                         1 for _ in (pasta / "dataset_compartilhado").rglob("*.txt")),
                     mapeamentos={}, spans_invalidos=0, documentos_descartados=0)
    for doc, grupo in planilha.groupby("documento_id"):
        caminho = pasta / "txt" / f"{doc}.txt"
        if not caminho.exists() and doc.startswith("paulo_"):
            _, nivel, numero = doc.split("_")
            caminho = pasta / "txt" / f"gen_{nivel}_{numero}paulo.txt"
            if not caminho.exists():
                caminho = pasta / "txt" / f"gen_n1_{numero}paulo.txt"
            if caminho.exists():
                auditoria["mapeamentos"][doc] = caminho.stem
        if not caminho.exists():
            auditoria["documentos_descartados"] += 1
            continue
        texto = ler_texto(caminho)
        gold = [dict(inicio=int(float(r.inicio)), fim=int(float(r.fim)),
                     trecho=r.trecho.replace("\\n", "\n"),
                     classificacao=r.classificacao, id_canonico=r.id_canonico)
                for r in grupo.itertuples()]
        invalidos = sum(texto[g["inicio"]:g["fim"]] != g["trecho"] for g in gold)
        auditoria["spans_invalidos"] += invalidos
        if invalidos:
            auditoria["documentos_descartados"] += 1
            continue
        dados[doc] = dict(texto=texto, gold=gold, nivel=int(grupo.nivel.iloc[0]),
                          autor=grupo.autor.iloc[0])
    auditoria["documentos_validos"] = len(dados)
    return dados, auditoria


def carregar_validacao_original():
    validacao = set(json.loads((ROOT / "splits.json").read_text(encoding="utf-8"))["validacao"])
    grupos = defaultdict(list)
    with (ROOT / "files/goldenset_offsets.csv").open(encoding="utf-8-sig", newline="") as arq:
        for linha in csv.DictReader(arq):
            if linha["documento_id"] in validacao:
                grupos[linha["documento_id"]].append(linha)
    return {
        doc: dict(texto=ler_texto(ROOT / "files/txt" / f"{doc}.txt"),
                  nivel=int(linhas[0]["nivel"]),
                  gold=[dict(inicio=int(r["inicio"]), fim=int(r["fim"]),
                             trecho=r["trecho"].replace("\\n", "\n"),
                             classificacao=r["classificacao"], id_canonico=r["id_canonico"])
                        for r in linhas])
        for doc, linhas in grupos.items()
    }


def dividir_por_documento(dados):
    por_autor = defaultdict(list)
    for doc, item in dados.items():
        por_autor[item["autor"]].append(doc)
    treino, teste = set(), set()
    for documentos in por_autor.values():
        documentos.sort(key=lambda doc: hashlib.sha256(doc.encode()).hexdigest())
        qtd_teste = max(1, round(len(documentos) * 0.2))
        teste.update(documentos[:qtd_teste])
        treino.update(documentos[qtd_teste:])
    assert treino.isdisjoint(teste) and treino | teste == dados.keys()
    return treino, teste


def caracteristicas(texto, candidato):
    inicio, fim = candidato["inicio"], candidato["fim"]
    return (texto[max(0, inicio - 80):inicio] + " [CIT] " + candidato["trecho"]
            + " [/CIT] " + texto[fim:fim + 80])


def treinar(dados, documentos):
    exemplos, rotulos = [], []
    for doc in sorted(documentos):
        texto, gold = dados[doc]["texto"], dados[doc]["gold"]
        candidatos = extrair(texto, doc)
        pares, _, _ = casar(gold, candidatos)
        positivos = {pi for _, pi in pares}
        for i, candidato in enumerate(candidatos):
            exemplos.append(caracteristicas(texto, candidato))
            rotulos.append(int(i in positivos))
    if set(rotulos) != {0, 1}:
        raise ValueError("treino precisa de candidatos positivos e negativos")
    modelo = make_pipeline(
        TfidfVectorizer(analyzer="char", ngram_range=(3, 5)),
        LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42),
    )
    modelo.fit(exemplos, rotulos)
    return modelo, Counter(rotulos)


def avaliar(dados, modelo, resolvedor):
    solucao = []
    predicoes = {"regex": [], "tfidf": []}
    extracao = {nome: Counter() for nome in predicoes}
    removidos = []
    for doc, item in sorted(dados.items()):
        texto, gold = item["texto"], item["gold"]
        candidatos = extrair(texto, doc)
        chances = (modelo.predict_proba([caracteristicas(texto, c) for c in candidatos])[:, 1]
                   if candidatos else [])
        filtrados = [c for c, chance in zip(candidatos, chances) if chance >= 0.5]
        pares, _, _ = casar(gold, candidatos)
        positivos = {pi for _, pi in pares}
        removidos.extend(dict(documento_id=doc, trecho=c["trecho"],
                              probabilidade=round(float(chance), 4),
                              anotado=i in positivos)
                         for i, (c, chance) in enumerate(zip(candidatos, chances))
                         if chance < 0.5)
        solucao.append(dict(documento_id=doc, nivel=item["nivel"], citacoes="|".join(
            f"{g['inicio']},{g['fim']},{g['classificacao']},{g['id_canonico'] or '-'}"
            for g in gold)))
        for nome, lista in (("regex", candidatos), ("tfidf", filtrados)):
            pares, faltantes, excedentes = casar(gold, lista)
            extracao[nome].update(tp=len(pares), fp=len(excedentes), fn=len(faltantes))
            celula = []
            for c in lista:
                resultado = resolvedor.resolver(c["trecho"], c["tipo"])
                id_canonico = resultado["id_canonico"]
                classe = ("real" if id_canonico is not None else
                          "incompleta" if not resultado["completo"] or
                          len(resultado["candidatos"]) > 1 else "inventada")
                celula.append(f"{c['inicio']},{c['fim']},{classe},{id_canonico or '-'},-")
            predicoes[nome].append(dict(documento_id=doc, citacoes="|".join(celula)))
    resultados = {}
    for nome, linhas in predicoes.items():
        contagem = extracao[nome]
        tp, fp, fn = (contagem[k] for k in ("tp", "fp", "fn"))
        resultados[nome] = dict(
            extracao=dict(contagem, precisao=tp / (tp + fp) if tp + fp else 0,
                          recall=tp / (tp + fn) if tp + fn else 0,
                          f1=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0),
            oficial=kaggle_metric.avaliar(pd.DataFrame(solucao), pd.DataFrame(linhas)),
        )
    return resultados, removidos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extra", type=Path, default=ROOT / "dataset_extra")
    parser.add_argument("--report", type=Path, default=ROOT / "runs/tfidf_experiment.json")
    args = parser.parse_args()
    dados, auditoria = carregar_extra(args.extra)
    treino, teste = dividir_por_documento(dados)
    modelo, rotulos = treinar(dados, treino)
    resolvedor = Resolvedor(ROOT / "files/desafio1_bracis.db")
    extra, removidos_extra = avaliar({doc: dados[doc] for doc in teste}, modelo, resolvedor)
    original, removidos_originais = avaliar(carregar_validacao_original(), modelo, resolvedor)
    relatorio = dict(auditoria=auditoria, treino=dict(documentos=len(treino),
                     positivos=rotulos[1], negativos=rotulos[0]),
                     teste_extra=dict(documentos=sorted(teste), resultados=extra,
                                      removidos=removidos_extra),
                     validacao_original=dict(resultados=original, removidos=removidos_originais))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    for grupo, resultados in (("Extra", extra), ("Original", original)):
        for metodo, valores in resultados.items():
            ex = valores["extracao"]
            print(f"{grupo} {metodo}: P={ex['precisao']:.4f} R={ex['recall']:.4f} "
                  f"F1={ex['f1']:.4f}, score={valores['oficial']['score_final']:.4f} "
                  f"(TP={ex['tp']}, FP={ex['fp']}, FN={ex['fn']})")
    print(f"Relatório: {args.report}")


if __name__ == "__main__":
    main()
