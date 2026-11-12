#!/bin/sh
set -eu

REPO_DIR=$(printf '%s' "${CHECKLISTS_REPO:-/dados/checklists-gt}" | tr -d '\r')
REPO_URL=$(printf '%s' "${REPO_URL:-https://github.com/AutomationGBMX/checklists-gt.git}" | tr -d '\r')
GITHUB_TOKEN=$(printf '%s' "${GITHUB_TOKEN:-}" | tr -d '\r')
export GITHUB_TOKEN

git config --global --add safe.directory '*'

if [ -n "$GITHUB_TOKEN" ]; then
    git config --global credential.helper \
        '!f() { echo "username=x-access-token"; echo "password=${GITHUB_TOKEN}"; }; f'
fi

if [ ! -d "$REPO_DIR/.git" ]; then
    echo "[painel] Baixando $REPO_URL ..."
    if ! git clone --quiet -c core.autocrlf=false "$REPO_URL" "$REPO_DIR"; then
        echo "[painel] ERRO ao clonar o repositório. Verifique REPO_URL e GITHUB_TOKEN no .env."
        exit 1
    fi
fi

exec python -m streamlit run /app/dashboard/app.py \
    --server.address="${PAINEL_ENDERECO:-0.0.0.0}" --server.port="${PAINEL_PORTA:-8501}"
