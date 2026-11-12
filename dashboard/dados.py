"""
Leitura dos checklists (arquivos JSON gerados pelo Raspberry Pi) para DataFrames.

Formato esperado de cada arquivo checklists/checklist_*.json:
{
  "versao_formato": 1,
  "id": "checklist_FULANO_20261111_120051",
  "equipamento": "1172",
  "operador": "FULANO", "matricula": "123",
  "data_hora": "2026-11-11T12:00:51",
  "status": "APROVADO" | "REPROVADO",
  "respostas": [{"item": 1, "pergunta": "...", "resposta": "OK" | "NÃO OK"}, ...]
}
"""
import json
from pathlib import Path

import pandas as pd

from importar_pdfs_antigos import converter as converter_pdf

# Rótulos curtos para os gráficos (o texto completo da pergunta continua no JSON).
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
    """Identifica o 'estado' da pasta (nomes + datas de modificação dos JSON e PDF).
    Se a assinatura não muda, não precisamos reler os arquivos."""
    return tuple(sorted((p.name, p.stat().st_mtime_ns) for p in pasta.glob("checklist_*.*")
                        if p.suffix in (".json", ".pdf")))


def _registros(pasta: Path):
    """Gera (nome_arquivo, registro) para cada checklist.
    Preferência: o JSON. Se um PDF não tiver JSON ao lado (Pi ainda na versão
    antiga), o próprio PDF é lido e convertido no mesmo formato."""
    for arquivo in sorted(pasta.glob("checklist_*.json")):
        yield arquivo, lambda a=arquivo: json.loads(a.read_text(encoding="utf-8"))
    for pdf in sorted(pasta.glob("checklist_*.pdf")):
        if not pdf.with_suffix(".json").exists():
            yield pdf, lambda a=pdf: {**converter_pdf(a), "origem": "pdf"}


def carregar_checklists(pasta: Path):
    """Retorna (checklists, respostas, erros):
    - checklists: 1 linha por checklist
    - respostas:  1 linha por item respondido (formato 'longo', bom para gráficos)
    - erros:      arquivos que não puderam ser lidos
    """
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
        except Exception as e:  # arquivo corrompido não pode derrubar o dashboard
            erros.append(f"{arquivo.name}: {e}")

    colunas = ["id", "data_hora", "operador", "matricula", "equipamento",
               "status", "itens_nao_ok", "origem", "pdf"]
    checklists = pd.DataFrame(linhas, columns=colunas).sort_values("data_hora", ascending=False)
    respostas = pd.DataFrame(linhas_resp, columns=["id", "item", "rotulo", "pergunta", "resposta"])
    return checklists, respostas, erros
