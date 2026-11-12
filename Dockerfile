FROM python:3.11-slim

ENV TZ=America/Sao_Paulo \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY dashboard/requirements.txt dashboard/requirements.txt
RUN pip install -r dashboard/requirements.txt

COPY nucleo/ nucleo/
COPY dashboard/ dashboard/

RUN useradd --create-home --uid 1000 painel \
 && mkdir -p /dados \
 && chown painel:painel /dados \
 && chmod +x dashboard/docker-entrypoint.sh

USER painel
WORKDIR /app/dashboard
ENV CHECKLISTS_REPO=/dados/checklists-gt
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PAINEL_PORTA', '8501') + '/_stcore/health', timeout=4)" || exit 1

ENTRYPOINT ["/app/dashboard/docker-entrypoint.sh"]
