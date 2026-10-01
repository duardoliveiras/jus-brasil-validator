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


def test_casos_extras_e_cabecalho():
    texto = (
        "PRECEDENTES INVOCADOS\n\n\n"
        "Apelação Criminal nº 7000075-58.2022.7.00.0000/PR. "
        "artigo 93, inciso IX, da CF/88. "
        "artigo 43 da Lei 8.112. "
        "precedente STJ sobre responsabilidade civil, sem número completo. "
        "DECISÃO MONOCRÁTICA"
    )
    estritas = extrair(texto, "exemplo")
    assert [c["trecho"] for c in estritas] == [
        "Apelação Criminal nº 7000075-58.2022.7.00.0000/PR",
        "artigo 93, inciso IX, da CF/88",
        "artigo 43 da Lei 8.112",
    ]
    amplas = extrair(texto, "exemplo", vagas=True)
    assert [c["trecho"] for c in amplas] == [
        *(c["trecho"] for c in estritas),
        "precedente STJ sobre responsabilidade civil, sem número completo",
    ]
    assert amplas[-1]["vago"]
    legal = extrair("Cabeçalho\n\n\ndispositivo legal sobre acesso à informação, "
                    "sem artigo nem número de lei", "exemplo", vagas=True)
    assert len(legal) == 1 and legal[0]["vago"] and legal[0]["tipo"] == "lei"


def test_refinamento_vagas():
    texto = "Cabeçalho\n\n\nprecedentes da Segunda / Seção sobre a cumulação dos danos."
    citacoes = extrair(texto, "teste", vagas=True, refinadas=True)
    assert [c["trecho"] for c in citacoes] == ["precedentes da Segunda / Seção"]
    assert all(texto[c["inicio"]:c["fim"]] == c["trecho"] for c in citacoes)
    assert all(c["vago"] for c in citacoes)
    assert extrair(texto, "teste") == extrair(texto, "teste", refinadas=True)

    texto = ("Cabeçalho\n\n\ndecisão recorrida violou a regra do Código Civil "
             "sobre responsabilidade extracontratual.")
    citacoes = extrair(texto, "teste", vagas=True, refinadas=True)
    assert any(c["trecho"].startswith("regra do Código Civil") for c in citacoes)
    assert not any(c["trecho"].startswith("decisão recorrida") for c in citacoes)
    assert all(texto[c["inicio"]:c["fim"]] == c["trecho"] for c in citacoes)
    assert all(a["fim"] <= b["inicio"] for a, b in zip(citacoes, citacoes[1:]))

    texto = ("Cabeçalho\n\n\nprecedentes do Superior Tribunal de Justiça "
             "sobre a responsabilidade civil.")
    assert extrair(texto, "teste", vagas=True, refinadas=True) == extrair(
        texto, "teste", vagas=True)


if __name__ == "__main__":
    test_extracao()
    test_casamento()
    test_variantes_perdidas_no_score()
    test_casos_extras_e_cabecalho()
    test_refinamento_vagas()
