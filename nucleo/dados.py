"""Leitura dos checklists (JSON ou PDF) para DataFrames."""
import json
from pathlib import Path

import pandas as pd

from .leitor_pdf import converter as converter_pdf

ROTULOS_ITENS = {
    1: "Leitor de crachá",
    2: "Botões / emergência / painel",
    3: "Sirene",
    4: "Condições gerais do equipamento",
    5: "Fixação ao solo",
    6: "Corda de tracionamento",
    7: "Corrente e amarração",
    8: "Carga dentro do limite",
    9: "Demarcação no solo",
    10: "Treinamento do operador",
    11: "Liberação final segura",
}


def assinatura_pasta(pasta: Path) -> tuple:
    return tuple(sorted((p.name, p.stat().st_mtime_ns) for p in pasta.glob("checklist_*.*")
                        if p.suffix in (".json", ".pdf")))


def _registros(pasta: Path):
    for arquivo in sorted(pasta.glob("checklist_*.json")):
        yield arquivo, lambda a=arquivo: json.loads(a.read_text(encoding="utf-8"))
    for pdf in sorted(pasta.glob("checklist_*.pdf")):
        if not pdf.with_suffix(".json").exists():
            yield pdf, lambda a=pdf: converter_pdf(a)


def carregar_checklists(pasta: Path):
    linhas, linhas_resp, erros = [], [], []
    for arquivo, ler in _registros(pasta):
        try:
            reg = ler()
            linhas.append({
                "id": reg["id"],
                "data_hora": pd.to_datetime(reg["data_hora"]),
                "operador": reg["operador"],
                "matricula": reg.get("matricula", ""),
                "equipamento": reg.get("equipamento", ""),
                "status": reg["status"],
                "itens_nao_ok": sum(r["resposta"] != "OK" for r in reg["respostas"]),
                "origem": reg.get("origem", ""),
                "pdf": arquivo.with_suffix(".pdf").name,
            })
            for r in reg["respostas"]:
                linhas_resp.append({
                    "id": reg["id"],
                    "item": r["item"],
                    "rotulo": ROTULOS_ITENS.get(r["item"], r["pergunta"][:40]),
                    "pergunta": r["pergunta"],
                    "resposta": r["resposta"],
                })
        except Exception as e:
            erros.append(f"{arquivo.name}: {e}")

    colunas = ["id", "data_hora", "operador", "matricula", "equipamento",
               "status", "itens_nao_ok", "origem", "pdf"]
    checklists = pd.DataFrame(linhas, columns=colunas).sort_values("data_hora", ascending=False)
    respostas = pd.DataFrame(linhas_resp, columns=["id", "item", "rotulo", "pergunta", "resposta"])
    return checklists, respostas, erros
