"""Resolve citações contra os identificadores próprios dos registros canônicos."""

import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path

from baseline import NUMERO, PROCESSO, ROOT


OCR = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1",
                     "S": "5", "s": "5", "g": "9", "G": "9"})
MARCA_NUMERO = re.compile(r"\bN\s*(?:[º°.]|o|‚)?\s*" + NUMERO, re.IGNORECASE)
MARCA_CURTO = re.compile(r"\bN\s*(?:[º°.]|o|‚)?\s*(\d{1,2})(?!\d)", re.IGNORECASE)
STF_CAB = re.compile(r"(?:RECURSO EXTRAORDINÁRIO(?: COM AGRAVO)?|AÇÃO PENAL|"
                     r"HABEAS CORPUS|MANDADO DE SEGURANÇA|"
                     r"AÇÃO DIRETA DE INCONSTITUCIONALIDADE)\s+" + NUMERO, re.IGNORECASE)
AUTOS_TST = re.compile(
    r"Vistos, relatados e discutidos estes autos.{0,350}?n\s*\.?\s*[º°]\s*",
    re.IGNORECASE | re.DOTALL,
)
SUMULA = re.compile(
    r"(?:s[uú]mula|s[uú]m\.?|5[uú]mula)\s*(vinculante)?\s*"
    r"(?:n[º°.]?\s*)?(\d{1,4})", re.IGNORECASE
)
ARTIGO = re.compile(r"\bart(?:igo)?\.?\s*(\d[\d.]*)", re.IGNORECASE)
LEIS = {"4737": "CE", "1001": "CPM", "8078": "CDC", "5452": "CLT",
        "10406": "CC", "64": "LC64", "13105": "CPC", "3689": "CPP"}


def numero(texto):
    """Extrai dígitos, recuperando confusões de OCR dentro do identificador."""
    match = re.search(NUMERO, texto, re.IGNORECASE)
    if not match:
        return None
    bruto = re.sub(r"(?:\s*[-–/]\s*|\s+)[OolISsgG]$", "", match.group())
    return "".join(c for c in bruto.translate(OCR) if c.isdigit())


def sem_acentos(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.upper())
                   if unicodedata.category(c) != "Mn")


def fonte_lei(texto):
    texto = " ".join(sem_acentos(texto).split())
    for palavra, fonte in (
        ("CONSTITUICAO", "CF"), ("CONSOLIDACAO DAS LEIS", "CLT"),
        ("CODIGO DE DEFESA DO CONSUMIDOR", "CDC"),
        ("CODIGO DE PROCESSO CIVIL", "CPC"),
        ("CODIGO DE PROCESSO PENAL", "CPP"),
        ("CODIGO PENAL MILITAR", "CPM"),
        ("CODIGO ELEITORAL", "CE"), ("CODIGO CIVIL", "CC"),
    ):
        if palavra in texto:
            return fonte
    for sigla in ("CPC", "CLT", "CPP", "CPM", "CDC"):
        if re.search(rf"\b{sigla}\b", texto):
            return sigla
    lei = re.search(r"(?:LEI(?: COMPLEMENTAR)?|DECRETO-LEI)\s+N[º°.]?\s*([\d.]+)",
                    texto)
    if lei:
        return LEIS.get("".join(c for c in lei.group(1) if c.isdigit()))
    return None


def numeros_principais(texto, tribunal):
    """Números associados ao processo próprio, não a precedentes mencionados."""
    if tribunal == "TST":
        autos = AUTOS_TST.search(texto)
        trecho = texto[autos.end():autos.end() + 120] if autos else ""
        chave = numero(trecho)
        return [chave] if chave else []

    cabecalho = texto[:1200]
    match = (MARCA_NUMERO.search(cabecalho[:350])
             if tribunal in ("STJ", "TSE", "STM") else None)
    match = (match or PROCESSO.search(cabecalho)
             or (STF_CAB.search(cabecalho[:500]) if tribunal == "STF" else None)
             or MARCA_NUMERO.search(cabecalho))
    if not match:
        curto = MARCA_CURTO.search(cabecalho[:350]) if tribunal == "STJ" else None
        return [curto.group(1)] if curto else []
    chave = numero(match.group())
    if not chave:
        return []
    chaves = [chave]
    if tribunal == "TSE":
        # Alguns acórdãos eleitorais trazem, no cabeçalho, número antigo e CNJ.
        alias = re.match(r"\s*\(\s*(" + NUMERO + r")\s*\)", cabecalho[match.end():],
                         re.IGNORECASE)
        if alias:
            chaves.append(numero(alias.group(1)))
    return chaves


class Resolvedor:
    def __init__(self, banco=ROOT / "files/desafio1_bracis.db"):
        self.acordaos = defaultdict(list)
        self.sumulas = defaultdict(list)
        self.dispositivos = defaultdict(list)
        con = sqlite3.connect(f"file:{Path(banco).resolve()}?mode=ro", uri=True)
        try:
            for id_canonico, tribunal, natureza, texto in con.execute(
                "SELECT id, tribunal, natureza, texto FROM documentos"
            ):
                if natureza == "acordao":
                    registro = (id_canonico, tribunal, sem_acentos(texto[:350]))
                    for chave in numeros_principais(texto, tribunal):
                        self.acordaos[chave].append(registro)
                elif natureza == "sumula":
                    match = SUMULA.search(texto[:100])
                    if match:
                        self.sumulas[match.group(2)].append(
                            (id_canonico, tribunal, bool(match.group(1))))
                elif natureza == "dispositivo":
                    match = ARTIGO.search(texto[:100])
                    fonte = fonte_lei(texto.split("\n", 1)[0])
                    if match and fonte:
                        artigo = int(match.group(1).replace(".", ""))
                        self.dispositivos[artigo, fonte].append(id_canonico)
        finally:
            con.close()

    def resolver(self, trecho, tipo):
        if tipo == "lei":
            artigo = ARTIGO.search(trecho)
            fonte = fonte_lei(trecho)
            chave = (int(artigo.group(1).replace(".", "")), fonte) if artigo else None
            ids = self.dispositivos.get(chave, []) if chave else []
        elif SUMULA.search(trecho):
            match = SUMULA.search(trecho)
            tribunal = re.search(r"\b(?:STF|STJ|TST|TSE|STM)\b", trecho, re.IGNORECASE)
            ids = [id for id, tr, vinculante in self.sumulas[match.group(2)]
                   if (not tribunal or tr == tribunal.group().upper())
                   and (not match.group(1) or vinculante)]
            chave = f"súmula {match.group(2)}"
        elif re.search(r"relatoria|relator|Rel\.\s*Min\.", trecho, re.IGNORECASE):
            chave, ids = None, []
        else:
            chave = numero(trecho)
            candidatos = self.acordaos.get(chave, []) if chave else []
            if len(candidatos) > 1:
                citacao = sem_acentos(trecho)
                if "EMBARGOS DE DIVERGENCIA" not in citacao:
                    simples = [c for c in candidatos if "EMBARGOS DE DIVERGENCIA" not in c[2]]
                    if simples:
                        candidatos = simples
            ids = [id for id, _, _ in candidatos]
        ids = sorted(set(ids))
        return {"id_canonico": ids[0] if len(ids) == 1 else None,
                "candidatos": ids, "chave": chave}
