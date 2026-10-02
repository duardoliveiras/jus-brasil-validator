"""Checagem mínima das famílias de extração e dos offsets."""

import csv
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from baseline import extrair, prever


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
    citacoes = extrair(texto, "exemplo")
    assert [c["trecho"] for c in citacoes] == [
        "Apelação Criminal nº 7000075-58.2022.7.00.0000/PR",
        "artigo 93, inciso IX, da CF/88",
        "artigo 43 da Lei 8.112",
        "precedente STJ sobre responsabilidade civil, sem número completo",
    ]
    assert citacoes[-1]["vago"]
    legal = extrair("Cabeçalho\n\n\ndispositivo legal sobre acesso à informação, "
                    "sem artigo nem número de lei", "exemplo")
    assert len(legal) == 1 and legal[0]["vago"] and legal[0]["tipo"] == "lei"


def test_refinamento_vagas():
    texto = "Cabeçalho\n\n\nprecedentes da Segunda / Seção sobre a cumulação dos danos."
    citacoes = extrair(texto, "teste")
    assert [c["trecho"] for c in citacoes] == ["precedentes da Segunda / Seção"]
    assert all(texto[c["inicio"]:c["fim"]] == c["trecho"] for c in citacoes)
    assert all(c["vago"] for c in citacoes)

    texto = ("Cabeçalho\n\n\ndecisão recorrida violou a regra do Código Civil "
             "sobre responsabilidade extracontratual.")
    citacoes = extrair(texto, "teste")
    assert any(c["trecho"].startswith("regra do Código Civil") for c in citacoes)
    assert not any(c["trecho"].startswith("decisão recorrida") for c in citacoes)
    assert all(texto[c["inicio"]:c["fim"]] == c["trecho"] for c in citacoes)
    assert all(a["fim"] <= b["inicio"] for a, b in zip(citacoes, citacoes[1:]))

    texto = ("Cabeçalho\n\n\nprecedentes do Superior Tribunal de Justiça "
             "sobre a responsabilidade civil.")
    assert [c["trecho"] for c in extrair(texto, "teste")] == [
        "precedentes do Superior Tribunal de Justiça sobre a responsabilidade civil"
    ]


def test_execucao():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        banco = root / "base #?.db"
        pasta = root / "textos"
        pasta.mkdir()
        with sqlite3.connect(banco) as con:
            con.execute("CREATE TABLE documentos (id INTEGER, tribunal TEXT, "
                        "natureza TEXT, texto TEXT)")
            con.executemany("INSERT INTO documentos VALUES (?, ?, ?, ?)", [
                (7, "STJ", "acordao", "RECURSO ESPECIAL Nº 1.234.567 - RS"),
                (8, "STJ", "acordao", "RECURSO ESPECIAL Nº 9.876.543 - RS"),
                (9, "STJ", "acordao", "RECURSO ESPECIAL Nº 9.876.543 - RS"),
                (10, None, "dispositivo", "art. 14 do Código de Defesa do Consumidor"),
                (11, "STJ", "sumula", "Súmula 83 do STJ"),
            ])
        texto = ("À vista 😃\r\nREsp nº 1.234.567/RS. REsp nº 8.888.888/RS. "
                 "REsp nº 9.876.543/RS. jurisprudência desta Corte. "
                 "art. 14 do Código de Defesa do Consumidor. Súmula 83 do STJ.")
        (pasta / "a.txt").write_bytes(texto.encode("utf-8"))
        (pasta / "b.txt").write_text("Sem citações.", encoding="utf-8")
        saida = root / "resultado" / "saida.csv"
        original = banco.read_bytes()
        assert prever(banco, pasta, saida) == (2, 6)
        with saida.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        assert rows[1] == {"documento_id": "b", "citacoes": "-"}
        esperado = [
            ("REsp nº 1.234.567/RS", "real", "7"),
            ("REsp nº 8.888.888/RS", "inventada", "-"),
            ("REsp nº 9.876.543/RS", "incompleta", "-"),
            ("jurisprudência desta Corte", "incompleta", "-"),
            ("art. 14 do Código de Defesa do Consumidor", "real", "10"),
            ("Súmula 83 do STJ", "real", "11"),
        ]
        blocos = rows[0]["citacoes"].split("|")
        assert len(blocos) == len(esperado)
        for bloco, (trecho, classe, ident) in zip(blocos, esperado):
            inicio, fim, cp, ip, conf = bloco.split(",")
            assert texto[int(inicio):int(fim)] == trecho
            assert (cp, ip, conf) == (classe, ident, "1.0000")
        anterior = saida.read_bytes()
        script = Path(__file__).resolve().parent / "run.sh"
        subprocess.run(["bash", str(script), str(banco), str(pasta), str(saida)],
                       cwd=root, check=True)
        assert saida.read_bytes() == anterior and banco.read_bytes() == original
        (pasta / "c.txt").write_bytes(b"\xff")
        try:
            prever(banco, pasta, saida)
        except UnicodeDecodeError:
            pass
        else:
            raise AssertionError("UTF-8 inválido deveria falhar")
        assert saida.read_bytes() == anterior
        assert list(saida.parent.iterdir()) == [saida]
        for destino in (banco, pasta / "a.txt"):
            try:
                prever(banco, pasta, destino)
            except ValueError:
                pass
            else:
                raise AssertionError("saída não pode sobrescrever entrada")
        pasta_vazia = root / "vazia"
        pasta_vazia.mkdir()
        for db, txt in ((root / "ausente.db", pasta), (banco, pasta_vazia)):
            try:
                prever(db, txt, saida)
            except ValueError:
                pass
            else:
                raise AssertionError("entrada inválida deveria falhar")


if __name__ == "__main__":
    test_extracao()
    test_variantes_perdidas_no_score()
    test_casos_extras_e_cabecalho()
    test_refinamento_vagas()
    test_execucao()
    print("Extração e execução: OK")
