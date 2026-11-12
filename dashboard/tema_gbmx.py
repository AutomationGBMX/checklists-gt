"""Identidade visual GBMX (Greenbrier Maxion) para o dashboard."""
import base64
import html
from pathlib import Path

import streamlit as st

VERDE_ESCURO = "#007330"
VERDE = "#008B39"
VERDE_LIMAO = "#9FC63B"
TEXTO = "#1F2A24"
FUNDO = "#F4F5F3"

COR_APROVADO = VERDE
COR_REPROVADO = "#D03B3B"

PASTA_ASSETS = Path(__file__).resolve().parent / "assets"


def arquivo_logo():
    for nome in ("logo_gbmx.png", "logo_gbmx.svg"):
        caminho = PASTA_ASSETS / nome
        if caminho.is_file():
            return caminho
    return None


def _logo_html() -> str:
    logo = arquivo_logo()
    if logo is None:
        return ('<div class="gbmx-logo-texto"><span class="gbmx-logo-sigla">GBMX</span>'
                '<span class="gbmx-logo-nome">GREENBRIER MAXION</span></div>')
    tipo = "image/svg+xml" if logo.suffix == ".svg" else "image/png"
    dados = base64.b64encode(logo.read_bytes()).decode()
    return f'<img class="gbmx-logo-img" src="data:{tipo};base64,{dados}" alt="GBMX">'


_CSS = f"""
<style>
  #MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] {{ display: none !important; }}
  [data-testid="stHeader"] {{ background: transparent; height: 0; }}
  .block-container {{ padding-top: 1.2rem; max-width: 1400px; }}

  .gbmx-cabecalho {{
    display: flex; align-items: center; justify-content: space-between; gap: 16px;
    background: linear-gradient(100deg, {VERDE_ESCURO} 0%, {VERDE_ESCURO} 55%, {VERDE} 100%);
    color: #fff; padding: 18px 26px; border-radius: 8px 8px 0 0;
  }}
  .gbmx-titulo {{ font-size: 1.7rem; font-weight: 700; line-height: 1.15; color: #fff; }}
  .gbmx-subtitulo {{ font-size: 0.95rem; color: #DDEFD9; margin-top: 2px; }}
  .gbmx-faixa {{ height: 6px; background: {VERDE_LIMAO}; border-radius: 0 0 8px 8px; margin-bottom: 14px; }}
  .gbmx-logo-img {{ max-height: 58px; max-width: 220px; }}
  .gbmx-logo-texto {{ display: flex; flex-direction: column; align-items: flex-end; line-height: 1; }}
  .gbmx-logo-sigla {{ color: {VERDE_LIMAO}; font-size: 2.1rem; font-weight: 800; letter-spacing: 1px; }}
  .gbmx-logo-nome {{ color: #fff; font-size: 0.62rem; font-weight: 700; letter-spacing: 1px; margin-top: 3px; }}

  .gbmx-rodape {{
    margin-top: 28px; padding-top: 10px; border-top: 1px solid #DDE3DD;
    text-align: center; color: #6B7A70; font-size: 0.8rem;
  }}
  .gbmx-rodape b {{ color: {VERDE_ESCURO}; }}
  .gbmx-secao {{
    display: inline-block; background: {VERDE}; color: #fff; font-weight: 700;
    padding: 5px 14px; border-radius: 4px; margin: 10px 0 6px 0; font-size: 1rem;
    border-left: 6px solid {VERDE_LIMAO};
  }}

  [data-testid="stMetric"] {{
    background: #fff; border: 1px solid #DDE3DD; border-left: 6px solid {VERDE};
    border-radius: 6px; padding: 10px 16px;
  }}
  [data-testid="stMetricLabel"] p {{ color: {VERDE_ESCURO}; font-weight: 700; }}
  [data-testid="stMetricValue"] {{ color: {TEXTO}; }}

  @media (max-width: 640px) {{
    .gbmx-cabecalho {{ padding: 14px 16px; }}
    .gbmx-titulo {{ font-size: 1.25rem; }}
    .gbmx-logo-img {{ max-height: 40px; }}
  }}
</style>
"""


def aplicar_tema():
    st.markdown(_CSS, unsafe_allow_html=True)


def cabecalho(titulo: str, subtitulo: str = ""):
    sub = f'<div class="gbmx-subtitulo">{html.escape(subtitulo)}</div>' if subtitulo else ""
    st.markdown(
        f'<div class="gbmx-cabecalho"><div><div class="gbmx-titulo">{html.escape(titulo)}</div>{sub}</div>'
        f'{_logo_html()}</div><div class="gbmx-faixa"></div>',
        unsafe_allow_html=True,
    )


def secao(titulo: str):
    st.markdown(f'<div class="gbmx-secao">{html.escape(titulo)}</div>', unsafe_allow_html=True)


def rodape(texto: str = "Desenvolvido por Engenharia de Automação"):
    st.markdown(f'<div class="gbmx-rodape"><b>{html.escape(texto)}</b> · GBMX</div>', unsafe_allow_html=True)
