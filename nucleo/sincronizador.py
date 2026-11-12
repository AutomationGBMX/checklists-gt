"""Mantém uma cópia local de checklists/ do GitHub sem precisar do git."""
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

DONO_REPO = "AutomationGBMX/checklists-gt"
BRANCH = "main"
PASTA_REMOTA = "checklists"
API = f"https://api.github.com/repos/{DONO_REPO}"
REFS = f"https://github.com/{DONO_REPO}.git/info/refs?service=git-upload-pack"
RAW = f"https://raw.githubusercontent.com/{DONO_REPO}"
EXTENSOES = (".json", ".pdf")


class LimiteGitHub(Exception):
    def __init__(self, ate: float):
        super().__init__(f"Limite de requisições do GitHub atingido até {datetime.fromtimestamp(ate):%H:%M:%S}.")
        self.ate = ate


@dataclass
class Resultado:
    online: bool
    mudou: bool
    commit: str
    verificado_em: datetime
    baixados: list = field(default_factory=list)
    removidos: list = field(default_factory=list)
    erro: Optional[str] = None


def sha_blob(dados: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(dados) + dados).hexdigest()


def gravar_atomico(destino: Path, dados: bytes):
    tmp = destino.with_name(destino.name + ".tmp")
    tmp.write_bytes(dados)
    os.replace(tmp, destino)


class Sincronizador:
    def __init__(self, pasta_base: Path, token: str = ""):
        self.pasta = pasta_base / "checklists"
        self.pasta.mkdir(parents=True, exist_ok=True)
        self._arquivo_estado = pasta_base / "estado.json"
        self._estado = self._ler_estado()
        self._bloqueado_ate = 0.0
        self._sessao = requests.Session()
        self._sessao.headers["User-Agent"] = "PainelGBMX"
        self._token = token.strip()

    @property
    def commit(self) -> str:
        return self._estado.get("commit", "")

    def _ler_estado(self) -> dict:
        try:
            return json.loads(self._arquivo_estado.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _salvar_estado(self):
        gravar_atomico(self._arquivo_estado, json.dumps(self._estado, indent=1).encode("utf-8"))

    def _verificar_limite(self, resp: requests.Response):
        if resp.status_code in (403, 429) and (
                "Retry-After" in resp.headers or resp.headers.get("X-RateLimit-Remaining") == "0"):
            if "Retry-After" in resp.headers:
                ate = time.time() + int(resp.headers["Retry-After"])
            else:
                ate = float(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
            self._bloqueado_ate = ate
            raise LimiteGitHub(ate)
        resp.raise_for_status()

    def _api(self, caminho: str, **cabecalhos) -> requests.Response:
        if self._token:
            cabecalhos["Authorization"] = f"Bearer {self._token}"
        resp = self._sessao.get(f"{API}{caminho}", headers=cabecalhos, timeout=20)
        if resp.status_code != 304:
            self._verificar_limite(resp)
        return resp

    def _commit_remoto(self) -> str:
        # Endpoint do "git fetch": não consome o limite de 60 req/h da API.
        auth = ("x-access-token", self._token) if self._token else None
        try:
            resp = self._sessao.get(REFS, auth=auth, timeout=15)
            resp.raise_for_status()
            alvo = f" refs/heads/{BRANCH}".encode()
            for linha in resp.content.split(b"\n"):
                linha = linha.split(b"\0")[0]
                if linha.endswith(alvo):
                    return linha[-len(alvo) - 40:-len(alvo)].decode()
        except requests.RequestException:
            if not self._token:
                raise
        return self._commit_pela_api()

    def _commit_pela_api(self) -> str:
        etag = self._estado.get("etag", "")
        resp = self._api(f"/commits/{BRANCH}", **({"If-None-Match": etag} if etag else {}))
        if resp.status_code == 304:
            return self.commit
        self._estado["etag"] = resp.headers.get("ETag", "")
        return resp.json()["sha"]

    def _arquivos_remotos(self, commit: str) -> dict:
        arvore = self._api(f"/git/trees/{commit}?recursive=1").json()
        prefixo = PASTA_REMOTA + "/"
        return {
            item["path"][len(prefixo):]: item["sha"]
            for item in arvore["tree"]
            if item["type"] == "blob" and item["path"].startswith(prefixo)
            and "/" not in item["path"][len(prefixo):] and item["path"].endswith(EXTENSOES)
        }

    def _baixar(self, commit: str, nome: str, sha: str) -> bytes:
        if self._token:
            resp = self._api(f"/git/blobs/{sha}", Accept="application/vnd.github.raw")
        else:
            resp = self._sessao.get(f"{RAW}/{commit}/{PASTA_REMOTA}/{nome}", timeout=60)
            resp.raise_for_status()
        if sha_blob(resp.content) != sha:
            raise ValueError(f"{nome}: conteúdo baixado não confere com o GitHub")
        return resp.content

    def sincronizar(self) -> Resultado:
        agora = datetime.now()
        if time.time() < self._bloqueado_ate:
            return Resultado(False, False, self.commit, agora,
                             erro=str(LimiteGitHub(self._bloqueado_ate)))
        try:
            commit = self._commit_remoto()
            if commit == self.commit and self._locais_completos():
                return Resultado(True, False, commit, agora)

            remotos = self._arquivos_remotos(commit)
            conhecidos = self._estado.get("arquivos", {})
            baixados = []
            for nome, sha in sorted(remotos.items()):
                if conhecidos.get(nome) != sha or not (self.pasta / nome).is_file():
                    gravar_atomico(self.pasta / nome, self._baixar(commit, nome, sha))
                    conhecidos[nome] = sha
                    baixados.append(nome)
                    self._estado["arquivos"] = conhecidos
                    self._salvar_estado()

            removidos = []
            for local in self.pasta.iterdir():
                if local.name not in remotos:
                    local.unlink(missing_ok=True)
                    removidos.append(local.name)

            mudou = commit != self.commit or bool(baixados or removidos)
            self._estado.update(commit=commit, arquivos=remotos)
            self._salvar_estado()
            return Resultado(True, mudou, commit, agora, baixados, removidos)
        except LimiteGitHub as e:
            return Resultado(False, False, self.commit, agora, erro=str(e))
        except (requests.RequestException, ValueError, KeyError, OSError) as e:
            return Resultado(False, False, self.commit, agora, erro=_mensagem(e))

    def _locais_completos(self) -> bool:
        return all((self.pasta / nome).is_file() for nome in self._estado.get("arquivos", {}))


def _mensagem(e: Exception) -> str:
    if isinstance(e, (requests.ConnectionError, requests.Timeout)):
        return "Sem conexão com o GitHub."
    if isinstance(e, requests.HTTPError) and e.response is not None and e.response.status_code in (401, 404):
        return "Repositório não encontrado ou sem permissão (confira o GITHUB_TOKEN no painel_gbmx.ini)."
    return str(e)[:300]
