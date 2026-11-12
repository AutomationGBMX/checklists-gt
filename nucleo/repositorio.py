"""Acompanha o repositório no GitHub (git fetch / pull)."""
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class EstadoRepositorio:
    commit: str
    mensagem: str
    data_commit: str
    commits_recebidos: int
    verificado_em: datetime
    erro: Optional[str] = None


def _git(repo: Path, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
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
    raiz = Path(__file__).resolve().parent.parent
    print(verificar_e_atualizar(raiz))
