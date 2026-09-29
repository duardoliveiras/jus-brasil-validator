"""Checagem mínima da resolução sem usar rótulos do gabarito."""

from resolver import Resolvedor, numero


def test_resolucao():
    resolver = Resolvedor()
    assert numero("1.45g.779") == "1459779"
    assert numero("170076O") == "1700760"
    assert numero("68.244 S") == "68244"
    casos = [
        ("AgInt no RESP 21737l8 - SP", "jurisprudencia", 6490934118),
        ("Súmula 83 do STJ", "jurisprudencia", 1289710642),
        ("art 312 do Código\nde Processo Penal", "lei", 10652044),
        ("AgInt no Recurso Especial nº 1.597.443 - PR", "jurisprudencia", 2684973273),
        ("RE 1.276.977", "jurisprudencia", None),
        ("Rcl de 2024, Rel. Min. Flávio Dino", "jurisprudencia", None),
    ]
    for trecho, tipo, esperado in casos:
        assert resolver.resolver(trecho, tipo)["id_canonico"] == esperado


if __name__ == "__main__":
    test_resolucao()
