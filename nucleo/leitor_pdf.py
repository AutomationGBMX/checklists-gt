"""Extrai os dados de um PDF de checklist."""
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader

PERGUNTAS = [
    "O leitor de crachá encontra-se em pleno funcionamento?",
    "Os botões de acionamento, emergência e os controles do painel encontram-se em perfeito funcionamento?",
    "A sirene e random do equipamento encontra-se em pleno funcionamento?",
    "O equipamento encontra-se em condições seguras de uso, sem apresentar danos, ruído anormal, trincas, modificações não autorizadas, peças faltantes ou instaladas de forma inadequada?",
    "A fixação do equipamento ao solo está adequada, sem a presença de parafusos soltos?",
    "A corda para tracionamento do equipamento encontra-se em boas condições de uso?",
    "A corrente e os acessórios de amarração da carga encontram-se em boas condições de uso?",
    "A carga a ser tracionada está dentro dos limites operacionais do equipamento?",
    "Existe demarcação no solo que assegure o posicionamento seguro do operador?",
    "Você possui o treinamento obrigatório para a operação do guincho tracionador?",
    "Após a verificação dos itens acima, a operação do guincho tracionador pode ser realizada com segurança?",
]


def _valor_apos(linhas, rotulo):
    return linhas[linhas.index(rotulo) + 1].strip()


def converter(pdf: Path) -> dict:
    texto = PdfReader(str(pdf)).pages[0].extract_text()
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]

    respostas = [("OK" if l.startswith("✓") else "NÃO OK") for l in linhas if l[:1] in ("✓", "✗")]
    if len(respostas) != len(PERGUNTAS):
        raise ValueError(f"esperava {len(PERGUNTAS)} respostas, encontrei {len(respostas)}")

    data = datetime.strptime(_valor_apos(linhas, "Data/Hora:"), "%d/%m/%Y %H:%M:%S")
    return {
        "versao_formato": 1,
        "id": Path(pdf).stem,
        "origem": "pdf",
        "equipamento": _valor_apos(linhas, "Equipamento:"),
        "operador": _valor_apos(linhas, "Operador:"),
        "matricula": _valor_apos(linhas, "Matrícula:"),
        "data_hora": data.isoformat(timespec="seconds"),
        "status": _valor_apos(linhas, "Status:"),
        "observacoes": "",
        "respostas": [{"item": i, "pergunta": p, "resposta": r}
                      for i, (p, r) in enumerate(zip(PERGUNTAS, respostas), 1)],
    }
