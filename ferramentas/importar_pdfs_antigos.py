"""Cria o JSON de cada PDF de checklists/ que ainda não tem."""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.leitor_pdf import converter  # noqa: E402

PASTA = RAIZ / "checklists"


def main():
    criados, pulados, falhas = 0, 0, 0
    for pdf in sorted(PASTA.glob("checklist_*.pdf")):
        destino = pdf.with_suffix(".json")
        if destino.exists():
            pulados += 1
            continue
        try:
            registro = {**converter(pdf), "origem": "importado_pdf"}
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
