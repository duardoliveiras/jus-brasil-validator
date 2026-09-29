"""Confere os documentos, o gabarito e a divisão de desenvolvimento."""

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main():
    textos = {}
    for arquivo in sorted((ROOT / "files/txt").glob("*.txt")):
        with arquivo.open(encoding="utf-8", newline="") as f:
            textos[arquivo.stem] = f.read()

    with (ROOT / "files/goldenset_offsets.csv").open(
        encoding="utf-8-sig", newline=""
    ) as f:
        citacoes = list(csv.DictReader(f))

    validacao = json.loads((ROOT / "splits.json").read_text(encoding="utf-8"))["validacao"]
    if len(validacao) != 6 or len(set(validacao)) != 6 or not set(validacao) <= textos.keys():
        raise ValueError("splits.json deve conter seis documentos distintos da amostra")
    if len(textos) != 26 or len(citacoes) != 192:
        raise ValueError(f"amostra inesperada: {len(textos)} documentos, {len(citacoes)} citações")

    contagem = Counter()
    documentos_no_gabarito = set()
    for linha in citacoes:
        doc = linha["documento_id"]
        if doc not in textos:
            raise ValueError(f"documento ausente: {doc}")
        inicio, fim = int(linha["inicio"]), int(linha["fim"])
        trecho = linha["trecho"].replace("\\n", "\n")
        if not (0 <= inicio < fim <= len(textos[doc])) or textos[doc][inicio:fim] != trecho:
            raise ValueError(f"span inválido: {doc}/{linha['citacao_id']} ({inicio}, {fim})")
        documentos_no_gabarito.add(doc)
        grupo = "validação" if doc in validacao else "desenvolvimento"
        contagem[grupo, linha["nivel"]] += 1

    if documentos_no_gabarito != textos.keys():
        raise ValueError("há documentos sem citações no gabarito")

    print(f"Amostra: {len(textos)} documentos, {len(citacoes)} citações; spans OK")
    for grupo, docs in (("desenvolvimento", textos.keys() - set(validacao)),
                        ("validação", validacao)):
        for nivel in ("1", "2"):
            qtd_docs = sum(doc.startswith(f"gen_n{nivel}_") for doc in docs)
            print(f"{grupo}, nível {nivel}: {qtd_docs} documentos, {contagem[grupo, nivel]} citações")


if __name__ == "__main__":
    main()
