"""Checagem mínima das famílias de extração e dos offsets."""

from baseline import extrair


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


if __name__ == "__main__":
    test_extracao()
