"""Checagem mínima da resolução sem usar rótulos do gabarito."""

from pathlib import Path

from resolver import Resolvedor, numero


def test_resolucao():
    resolver = Resolvedor(Path(__file__).resolve().parent / "files/desafio1_bracis.db")
    assert numero("1.45g.779") == "1459779"
    assert numero("170076O") == "1700760"
    assert numero("68.244 S") == "68244"
    assert numero("Rcl 84.640/BA") == "84640"
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
    fora_da_cobertura = resolver.resolver("art 172 da Lei nº 9.504/1997", "lei")
    assert fora_da_cobertura["id_canonico"] is None and fora_da_cobertura["completo"]
    assert not resolver.resolver("Rcl de 2024, Rel. Min. Flávio Dino", "jurisprudencia")["completo"]
    assert resolver.resolver("artigo 93, inciso IX, da CF/88", "lei")["id_canonico"] == 10626510
    lei_8112 = resolver.resolver("artigo 43 da Lei 8.112", "lei")
    assert lei_8112["completo"] and lei_8112["id_canonico"] is None


if __name__ == "__main__":
    test_resolucao()
    print("Resolução: OK")
