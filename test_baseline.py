"""Checagem mínima das famílias de extração e dos offsets."""

from baseline import casar, extrair


def test_extracao():
    texto = (
        "Autos nº 1234567-89.2020.1.00.0000\n\n\n"
        "À vista da Súmula 83 do STJ, do art. 14 do Código de Defesa do Consumidor, "
        "do AgInt no REsp nº 1.234.567/RS e do julgado do STF proferido em 2024 "
        "pela relatoria de Dias Toffoli, decide-se."
    )
    citacoes = extrair(texto, "exemplo")
    assert [c["trecho"] for c in citacoes] == [
        "Súmula 83 do STJ",
        "art. 14 do Código de Defesa do Consumidor",
        "AgInt no REsp nº 1.234.567/RS",
        "julgado do STF proferido em 2024 pela relatoria de Dias Toffoli",
    ]
    assert {c["tipo"] for c in citacoes} == {"lei", "jurisprudencia"}
    assert all(texto[c["inicio"]:c["fim"]] == c["trecho"] for c in citacoes)
    assert all(a["fim"] <= b["inicio"] for a, b in zip(citacoes, citacoes[1:]))


def test_casamento():
    gold = [{"inicio": 0, "fim": 10}, {"inicio": 20, "fim": 30}]
    pred = [{"inicio": 0, "fim": 10}, {"inicio": 0, "fim": 5},
            {"inicio": 20, "fim": 25}, {"inicio": 40, "fim": 50}]
    assert casar(gold, pred) == ([(0, 0), (1, 2)], [], [1, 3])


def test_variantes_perdidas_no_score():
    texto = (
        "Cabeçalho\n\n\n"
        "Agravo em Recurso Especial do STJ,\nde 2023, Rel. Min. Assusete Magalhães. "
        "RE. nº\xa03.647.129-RS. Temã 2.680 da repercussão geral."
    )
    assert [c["trecho"] for c in extrair(texto, "exemplo")] == [
        "Agravo em Recurso Especial do STJ,\nde 2023, Rel. Min. Assusete Magalhães",
        "RE. nº\xa03.647.129-RS",
        "Temã 2.680 da repercussão geral",
    ]


if __name__ == "__main__":
    test_extracao()
    test_casamento()
    test_variantes_perdidas_no_score()
