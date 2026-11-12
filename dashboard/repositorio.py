"""
Watcher do repositório: descobre se o Raspberry Pi enviou commits novos e,
se sim, baixa-os (git pull).

Conceito: POLLING. A cada N segundos perguntamos ao GitHub "tem novidade?".
A alternativa (webhook, o GitHub avisar a gente) exigiria esta máquina ser
acessível pela internet, o que normalmente não é o caso numa rede corporativa.

Este módulo só LÊ do repositório remoto, nunca faz commit/push. Assim o Pi é
o único que escreve e não existe risco de conflito de merge.
"""
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class EstadoRepositorio:
    commit: str                 # hash curto do commit que estamos exibindo
    mensagem: str               # mensagem do commit (ex.: "Checklist APROVADO - ...")
    data_commit: str            # quando o commit foi feito (ISO)
    commits_recebidos: int      # quantos commits novos chegaram nesta verificação
    verificado_em: datetime
    erro: Optional[str] = None  # preenchido se o fetch/pull falhar (ex.: sem internet)


def _git(repo: Path, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    # GIT_TERMINAL_PROMPT=0: se faltar credencial, falha na hora em vez de travar
    # esperando alguém digitar senha num terminal que não existe.
    ambiente = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", timeout=timeout, env=ambiente,
    )


def _info_head(repo: Path) -> tuple:
    res = _git(repo, "log", "-1", "--format=%h%x1f%cI%x1f%s")
    if res.returncode != 0:
        return "?", "", ""
    commit, data, mensagem = res.stdout.strip().split("\x1f", 2)
    return commit, mensagem, data


def verificar_e_atualizar(repo: Path) -> EstadoRepositorio:
    """
    1. git fetch          -> baixa os commits novos para a pasta .git, SEM mexer nos arquivos
    2. HEAD..@{u}         -> conta quantos commits o remoto tem que nós não temos
    3. git pull --ff-only -> se houver, avança os arquivos até o commit mais novo
    """
    erro = None
    recebidos = 0
    try:
        res_fetch = _git(repo, "fetch", "--quiet")
        if res_fetch.returncode != 0:
            erro = f"git fetch falhou: {res_fetch.stderr.strip()[:200]}"
        else:
            res_atras = _git(repo, "rev-list", "--count", "HEAD..@{u}")
            atras = int(res_atras.stdout.strip() or 0) if res_atras.returncode == 0 else 0
            if atras > 0:
                # --ff-only: só "avança" a cópia local. Se por algum motivo houver
                # commits locais divergentes, ele se recusa em vez de criar um merge.
                res_pull = _git(repo, "pull", "--ff-only", "--quiet")
                if res_pull.returncode != 0:
                    detalhe = res_pull.stderr.strip()
                    if "would be overwritten" in detalhe or "divergent" in detalhe or "Not possible to fast-forward" in detalhe:
                        erro = (f"Há {atras} commit(s) novo(s) no GitHub, mas a pasta {repo} tem alterações "
                                "locais que impedem o pull. Use uma cópia do repositório só para o dashboard "
                                "(veja iniciar_dashboard.bat), onde ninguém edita arquivos.")
                    else:
                        erro = f"git pull falhou: {detalhe[:200]}"
                else:
                    recebidos = atras
    except subprocess.TimeoutExpired:
        erro = "Tempo esgotado ao falar com o GitHub (sem internet?)."
    except FileNotFoundError:
        erro = "Comando 'git' não encontrado no PATH."

    commit, mensagem, data = _info_head(repo)
    return EstadoRepositorio(commit, mensagem, data, recebidos, datetime.now(), erro)


if __name__ == "__main__":
    # Teste rápido pela linha de comando: python dashboard/repositorio.py
    raiz = Path(__file__).resolve().parent.parent
    print(verificar_e_atualizar(raiz))
