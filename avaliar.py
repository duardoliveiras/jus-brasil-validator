"""Avaliação local com a métrica fornecida pela organização."""

import argparse
from pathlib import Path

import pandas as pd

from files.kaggle_metric import avaliar


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gabarito", type=Path)
    parser.add_argument("submissao", type=Path)
    args = parser.parse_args()
    gold = pd.read_csv(args.gabarito, dtype=str, keep_default_na=False)
    rows = []
    for doc, grupo in gold.groupby("documento_id", sort=True):
        blocos = [f"{g.inicio},{g.fim},{g.classificacao},{g.id_canonico or '-'}"
                  for g in grupo.itertuples()]
        rows.append(dict(documento_id=doc, nivel=int(grupo.nivel.iloc[0]),
                         citacoes="|".join(blocos)))
    submission = pd.read_csv(args.submissao, dtype=str, keep_default_na=False)
    resultado = avaliar(pd.DataFrame(rows), submission)
    print(f"Score local: {resultado['score_final']:.4f}")


if __name__ == "__main__":
    main()
