"""Painel de Checklists GBMX - aplicativo Windows."""
import html
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import webview

TITULO = "Painel de Checklists GBMX"
PORTA_PADRAO = 8501
ESPERA_DOCKER_S = 180
ESPERA_PAINEL_S = 240
SEM_CONSOLE = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
DOCKER_DESKTOP = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Docker" / "Docker" / "Docker Desktop.exe"


def pasta_do_programa() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def achar_projeto():
    pasta = pasta_do_programa()
    for candidata in (pasta, *pasta.parents):
        if (candidata / "docker-compose.yml").is_file():
            return candidata
    return None


def ler_porta(projeto) -> int:
    env = projeto / ".env" if projeto else None
    if env and env.is_file():
        for linha in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            chave, _, valor = linha.strip().partition("=")
            if chave.strip() == "PORTA" and valor.strip().isdigit():
                return int(valor.strip())
    return PORTA_PADRAO


def painel_no_ar(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/_stcore/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _executar(cmd, cwd=None, timeout=60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=SEM_CONSOLE)


_docker_cmd = None


def comando_docker():
    global _docker_cmd
    if _docker_cmd is None:
        if shutil.which("docker"):
            _docker_cmd = ["docker"]
        elif shutil.which("wsl") and _executar(["wsl", "-e", "sh", "-c", "command -v docker"], timeout=60).returncode == 0:
            _docker_cmd = ["wsl", "-e", "docker"]
        else:
            _docker_cmd = []
    return _docker_cmd


def docker(*args, cwd=None, timeout=60) -> subprocess.CompletedProcess:
    return _executar([*comando_docker(), *args], cwd=cwd, timeout=timeout)


def estado_docker():
    if not comando_docker():
        return None
    try:
        return docker("info", timeout=60).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def tela(titulo: str, detalhe: str = "", erro: bool = False) -> str:
    animacao = "" if erro else '<div class="giro"></div>'
    botao = '<button onclick="pywebview.api.tentar_novamente()">Tentar novamente</button>' if erro else ""
    return f"""<!doctype html><html lang="pt-br"><head><meta charset="utf-8"><style>
      html,body{{margin:0;height:100%;font-family:"Segoe UI",sans-serif}}
      body{{background:linear-gradient(115deg,#006A2C 0%,#007330 55%,#008B39 100%);color:#fff;
           display:flex;align-items:center;justify-content:center}}
      .caixa{{max-width:640px;padding:32px;text-align:center}}
      .sigla{{color:#9FC63B;font-size:64px;font-weight:800;letter-spacing:2px;line-height:1}}
      .nome{{font-size:12px;font-weight:700;letter-spacing:2px;margin:6px 0 28px}}
      h1{{font-size:22px;margin:18px 0 8px}}
      p{{color:#DDEFD9;font-size:14px;line-height:1.5;white-space:pre-wrap;text-align:{'left' if erro else 'center'}}}
      .faixa{{height:6px;background:#9FC63B;width:120px;margin:0 auto;border-radius:3px}}
      .giro{{width:38px;height:38px;margin:26px auto 0;border:4px solid rgba(255,255,255,.25);
             border-top-color:#9FC63B;border-radius:50%;animation:g 1s linear infinite}}
      @keyframes g{{to{{transform:rotate(360deg)}}}}
      .autoria{{position:fixed;bottom:16px;left:0;right:0;text-align:center;color:#BFE0C8;font-size:12px}}
      button{{margin-top:22px;background:#9FC63B;color:#0B2A16;border:0;border-radius:4px;
              padding:10px 22px;font-weight:700;font-size:14px;cursor:pointer}}
    </style></head><body><div class="caixa">
      <div class="sigla">GBMX</div><div class="nome">GREENBRIER MAXION</div><div class="faixa"></div>
      <h1>{html.escape(titulo)}</h1><p>{html.escape(detalhe)}</p>{animacao}{botao}
    </div><div class="autoria">Desenvolvido por Engenharia de Automação</div></body></html>"""


class Inicializador:
    def __init__(self):
        self._janela = None  # com "_" o pywebview não percorre o objeto (evita travar a janela)
        self._rodando = threading.Lock()

    def tentar_novamente(self):
        threading.Thread(target=self.iniciar, daemon=True).start()

    def _mostrar(self, titulo, detalhe="", erro=False):
        self._janela.load_html(tela(titulo, detalhe, erro))

    def iniciar(self):
        if not self._rodando.acquire(blocking=False):
            return
        try:
            self._sequencia()
        except Exception as e:
            self._mostrar("Erro inesperado", str(e), erro=True)
        finally:
            self._rodando.release()

    def _sequencia(self):
        projeto = achar_projeto()
        url = f"http://localhost:{ler_porta(projeto)}"

        self._mostrar("Abrindo o painel…", url)
        if painel_no_ar(url):
            self._janela.load_url(url)
            return

        if projeto is None:
            self._mostrar("Projeto não encontrado",
                          "Coloque o PainelGBMX.exe na pasta do projeto (junto do docker-compose.yml).", erro=True)
            return
        if not (projeto / ".env").is_file():
            self._mostrar("Falta o arquivo .env", f"Copie .env.example para .env em:\n{projeto}", erro=True)
            return

        estado = estado_docker()
        if estado is None:
            self._mostrar("Docker não encontrado",
                          "Instale o Docker Desktop ou o Docker no WSL e abra o programa novamente.", erro=True)
            return
        if not estado:
            if comando_docker() == ["docker"] and DOCKER_DESKTOP.is_file():
                subprocess.Popen([str(DOCKER_DESKTOP)], creationflags=SEM_CONSOLE)
            inicio = time.monotonic()
            while not estado_docker():
                espera = int(time.monotonic() - inicio)
                if espera > ESPERA_DOCKER_S:
                    self._mostrar("O Docker não respondeu",
                                  "Inicie o Docker manualmente e clique em Tentar novamente.", erro=True)
                    return
                self._mostrar("Iniciando o Docker…", f"Aguardando ({espera} s)")
                time.sleep(3)

        self._mostrar("Iniciando o painel…", "Na primeira vez pode levar alguns minutos.")
        resultado = docker("compose", "up", "-d", cwd=str(projeto), timeout=1800)
        if resultado.returncode != 0:
            self._mostrar("Falha ao iniciar o container",
                          (resultado.stderr or resultado.stdout).strip()[-700:], erro=True)
            return

        inicio = time.monotonic()
        while not painel_no_ar(url):
            espera = int(time.monotonic() - inicio)
            if espera > ESPERA_PAINEL_S:
                logs = docker("compose", "logs", "--tail", "15", cwd=str(projeto)).stdout.strip()
                self._mostrar("O painel não respondeu", logs[-700:], erro=True)
                return
            self._mostrar("Iniciando o painel…", f"Aguardando ({espera} s)")
            time.sleep(2)

        self._janela.load_url(url)


def main():
    inicializador = Inicializador()
    inicializador._janela = webview.create_window(
        TITULO, html=tela("Abrindo o painel…"), js_api=inicializador,
        width=1360, height=860, min_size=(900, 600), maximized=True,
        background_color="#007330", text_select=True,
    )
    webview.start(inicializador.iniciar)


if __name__ == "__main__":
    main()
