"""Painel de Checklists GBMX - standalone (sincroniza direto com o GitHub)."""
import json
import os
import shutil
import sys
import threading
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import webview

if getattr(sys, "frozen", False):
    PASTA_PROGRAMA = Path(sys.executable).resolve().parent
    PASTA_RECURSOS = Path(sys._MEIPASS)
else:
    PASTA_PROGRAMA = Path(__file__).resolve().parent
    PASTA_RECURSOS = PASTA_PROGRAMA
    sys.path.insert(0, str(PASTA_PROGRAMA.parent))

from nucleo.dados import ROTULOS_ITENS, ler_registros  # noqa: E402
from nucleo.sincronizador import Sincronizador  # noqa: E402

TITULO = "Painel de Checklists GBMX"
ARQUIVO_INI = PASTA_PROGRAMA / "painel_gbmx.ini"
PASTA_DADOS = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PainelGBMX"
INI_PADRAO = ("# Token do GitHub: só é necessário se o repositório for privado.\n"
              "GITHUB_TOKEN=\n"
              "INTERVALO_SEGUNDOS=30\n")


def ler_config() -> dict:
    if not ARQUIVO_INI.is_file():
        try:
            ARQUIVO_INI.write_text(INI_PADRAO, encoding="utf-8")
        except OSError:
            pass
    config = {}
    try:
        for linha in ARQUIVO_INI.read_text(encoding="utf-8-sig").splitlines():
            chave, sep, valor = linha.partition("=")
            if sep and not linha.lstrip().startswith(("#", ";", "[")):
                config[chave.strip().upper()] = valor.strip()
    except OSError:
        pass
    try:
        intervalo = max(10, int(config.get("INTERVALO_SEGUNDOS", 30)))
    except ValueError:
        intervalo = 30
    return {"token": config.get("GITHUB_TOKEN", ""), "intervalo": intervalo}


def _inicio_periodo(periodo: str):
    hoje = date.today()
    return {"hoje": hoje, "7": hoje - timedelta(days=6), "30": hoje - timedelta(days=29)}.get(periodo)


def _fmt(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")


class Api:
    def __init__(self, sinc: Sincronizador, intervalo: int):
        self._sinc = sinc
        self._intervalo = intervalo
        self._janela = None
        self._trava = threading.Lock()
        self._checklists, self._respostas, self._erros = [], [], []
        self._estado = {"online": None, "verificado_em": "", "erro": None, "commit": sinc.commit[:7]}
        self._recarregar()

    def _recarregar(self):
        linhas, respostas, erros = ler_registros(self._sinc.pasta)
        with self._trava:
            self._checklists, self._erros = linhas, erros
            self._respostas = {}
            for r in respostas:
                self._respostas.setdefault(r["id"], []).append(r)

    def _filtrar(self, filtros) -> list:
        filtros = filtros or {}
        inicio = _inicio_periodo(filtros.get("periodo", "tudo"))
        operadores = set(filtros.get("operadores") or [])
        with self._trava:
            return [c for c in self._checklists
                    if (inicio is None or c["data_hora"][:10] >= inicio.isoformat())
                    and (not operadores or c["operador"] in operadores)]

    def _linha(self, c: dict) -> dict:
        return dict(c, data_hora_fmt=_fmt(c["data_hora"]),
                    tem_pdf=(self._sinc.pasta / c["pdf"]).is_file())

    def iniciar(self):
        return {"intervalo": self._intervalo, "estado": self._estado}

    def obter_resumo(self, filtros=None):
        lista = self._filtrar(filtros)
        aprovados = sum(c["status"] == "APROVADO" for c in lista)
        por_dia = {}
        nao_ok = Counter()
        with self._trava:
            todos_operadores = sorted({c["operador"] for c in self._checklists})
            erros = list(self._erros)
            for c in lista:
                dia = por_dia.setdefault(c["data_hora"][:10], {"APROVADO": 0, "REPROVADO": 0})
                dia[c["status"]] = dia.get(c["status"], 0) + 1
                nao_ok.update(r["item"] for r in self._respostas.get(c["id"], []) if r["resposta"] != "OK")
        return {
            "total": len(lista),
            "aprovados": aprovados,
            "reprovados": len(lista) - aprovados,
            "ultimo": self._linha(lista[0]) if lista else None,
            "por_dia": [{"dia": d, "aprovado": v["APROVADO"], "reprovado": v["REPROVADO"]}
                        for d, v in sorted(por_dia.items())],
            "itens_nao_ok": sorted(({"item": i, "rotulo": r, "quantidade": nao_ok[i]}
                                    for i, r in ROTULOS_ITENS.items()), key=lambda x: -x["quantidade"]),
            "operadores": todos_operadores,
            "erros": erros,
            "estado": self._estado,
        }

    def listar_checklists(self, filtros=None):
        return [self._linha(c) for c in self._filtrar(filtros)]

    def detalhe(self, id_checklist):
        with self._trava:
            c = next((c for c in self._checklists if c["id"] == id_checklist), None)
            respostas = sorted(self._respostas.get(id_checklist, []), key=lambda r: r["item"])
        return {"checklist": self._linha(c), "respostas": respostas} if c else None

    def salvar_pdf(self, id_checklist):
        info = self.detalhe(id_checklist)
        if not info or not info["checklist"]["tem_pdf"]:
            return {"ok": False, "mensagem": "PDF não encontrado."}
        nome = info["checklist"]["pdf"]
        destino = self._janela.create_file_dialog(
            webview.FileDialog.SAVE, save_filename=nome, file_types=("Arquivo PDF (*.pdf)",))
        if isinstance(destino, (list, tuple)):
            destino = destino[0] if destino else None
        if not destino:
            return {"ok": False, "mensagem": ""}
        try:
            shutil.copyfile(self._sinc.pasta / nome, destino)
        except OSError as e:
            return {"ok": False, "mensagem": f"Não foi possível salvar: {e}"}
        return {"ok": True, "mensagem": f"PDF salvo em {destino}"}

    def _laco_sincronizacao(self):
        while True:
            r = self._sinc.sincronizar()
            if r.mudou:
                self._recarregar()
            self._estado = {"online": r.online, "verificado_em": r.verificado_em.strftime("%H:%M:%S"),
                            "erro": r.erro, "commit": r.commit[:7]}
            try:
                self._janela.evaluate_js(f"window.gbmx && gbmx.sincronizado({json.dumps(r.mudou)}, "
                                         f"{json.dumps(self._estado)})")
            except Exception:
                pass
            time.sleep(self._intervalo)


def main():
    config = ler_config()
    sinc = Sincronizador(PASTA_DADOS, config["token"])
    api = Api(sinc, config["intervalo"])
    pagina = (PASTA_RECURSOS / "web" / "painel.html").read_text(encoding="utf-8")
    api._janela = webview.create_window(
        TITULO, html=pagina, js_api=api, width=1360, height=860, min_size=(900, 600),
        maximized=True, background_color="#F4F5F3", text_select=True,
    )
    threading.Thread(target=api._laco_sincronizacao, daemon=True).start()
    webview.start()


if __name__ == "__main__":
    main()
