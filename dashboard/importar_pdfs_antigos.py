"""
Uso único: cria o JSON correspondente para cada PDF antigo de checklists/
(gerados antes de o Raspberry Pi passar a salvar JSON).

    python dashboard/importar_pdfs_antigos.py

PDFs que já têm JSON ao lado são ignorados, então pode rodar mais de uma vez.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader

PASTA = Path(__file__).resolve().parent.parent / "checklists"

# Mesmas perguntas de sistema_gt_rfid_V33.py (na mesma ordem).
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


def valor_apos(linhas, rotulo):
    """No texto extraído, cada valor vem na linha seguinte ao seu rótulo."""
    return linhas[linhas.index(rotulo) + 1].strip()


def converter(pdf: Path) -> dict:
    texto = PdfReader(str(pdf)).pages[0].extract_text()
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]

    respostas = [("OK" if l.startswith("✓") else "NÃO OK") for l in linhas if l[:1] in ("✓", "✗")]
    if len(respostas) != len(PERGUNTAS):
        raise ValueError(f"esperava {len(PERGUNTAS)} respostas, encontrei {len(respostas)}")

    data = datetime.strptime(valor_apos(linhas, "Data/Hora:"), "%d/%m/%Y %H:%M:%S")
    return {
        "versao_formato": 1,
        "id": pdf.stem,
        "origem": "importado_pdf",
        "equipamento": valor_apos(linhas, "Equipamento:"),
        "operador": valor_apos(linhas, "Operador:"),
        "matricula": valor_apos(linhas, "Matrícula:"),
        "data_hora": data.isoformat(timespec="seconds"),
        "status": valor_apos(linhas, "Status:"),
        "observacoes": "",
        "respostas": [{"item": i, "pergunta": p, "resposta": r}
                      for i, (p, r) in enumerate(zip(PERGUNTAS, respostas), 1)],
    }


def main():
    criados, pulados, falhas = 0, 0, 0
    for pdf in sorted(PASTA.glob("checklist_*.pdf")):
        destino = pdf.with_suffix(".json")
        if destino.exists():
            pulados += 1
            continue
        try:
            registro = converter(pdf)
            with open(destino, "w", encoding="utf-8", newline="\n") as f:
                json.dump(registro, f, ensure_ascii=False, indent=2)
                f.write("\n")
            criados += 1
        except Exception as e:
            falhas += 1
            print(f"  FALHA {pdf.name}: {e}", file=sys.stderr)
    print(f"JSON criados: {criados} | já existiam: {pulados} | falhas: {falhas}")


if __name__ == "__main__":
    main()
