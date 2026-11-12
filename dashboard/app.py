"""
Dashboard dos checklists do Guincho Tracionador (GT).

Rodar:  python -m streamlit run dashboard/app.py
        (ou dar dois cliques em dashboard/iniciar_dashboard.bat)

Fluxo a cada INTERVALO segundos:
  1. verifica o GitHub (git fetch) e, se houver commit novo do Pi, faz git pull
  2. se os arquivos JSON mudaram, relê os dados
  3. redesenha os indicadores, gráficos e tabela
"""
import os
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import altair as alt
import pandas as pd
import streamlit as st

from dados import ROTULOS_ITENS, assinatura_pasta, carregar_checklists
from repositorio import verificar_e_atualizar

# --- Configuração (pode ser sobrescrita por variáveis de ambiente) ----------
# Por padrão usa a cópia dedicada "checklists-gt-dados" (ao lado da pasta do
# projeto), onde ninguém edita arquivos — assim o git pull nunca é bloqueado.
_COPIA_DEDICADA = Path(__file__).resolve().parent.parent.parent / "checklists-gt-dados"
REPO = Path(os.environ.get("CHECKLISTS_REPO", _COPIA_DEDICADA))
PASTA_CHECKLISTS = REPO / "checklists"
INTERVALO = int(os.environ.get("INTERVALO_SEGUNDOS", "30"))

# Cores de STATUS (não de série): sempre acompanhadas de ícone + texto.
COR_STATUS = {"APROVADO": "#0ca30c", "REPROVADO": "#d03b3b"}
ICONE_STATUS = {"APROVADO": "✅ APROVADO", "REPROVADO": "❌ REPROVADO"}

st.set_page_config(page_title="Checklists GT", page_icon="✅", layout="wide")


# --- Camada de cache ---------------------------------------------------------
# ttl = "validade". Se várias abas do navegador estiverem abertas, o git fetch
# roda no máximo uma vez a cada INTERVALO/2 segundos, e não uma vez por aba.
@st.cache_data(ttl=max(5, INTERVALO // 2), show_spinner=False)
def _verificar_repositorio_cache(repo: str) -> dict:
    # Devolve um dict simples: o cache precisa serializar (pickle) o resultado, e
    # uma classe própria quebra quando o Streamlit recarrega o módulo após uma edição.
    return asdict(verificar_e_atualizar(Path(repo)))


def verificar_repositorio(repo: str):
    return SimpleNamespace(**_verificar_repositorio_cache(repo))


# A "assinatura" (nomes + datas dos arquivos) entra na chave do cache:
# enquanto ela não muda, os JSONs não são relidos do disco.
@st.cache_data(show_spinner=False)
def ler_dados(pasta: str, assinatura: tuple):
    return carregar_checklists(Path(pasta))


def filtrar_periodo(df: pd.DataFrame, periodo: str) -> pd.DataFrame:
    hoje = date.today()
    inicio = {
        "Hoje": hoje,
        "Últimos 7 dias": hoje - timedelta(days=6),
        "Últimos 30 dias": hoje - timedelta(days=29),
    }.get(periodo)
    if inicio is None:
        return df
    return df[df["data_hora"].dt.date >= inicio]


# --- Gráficos ----------------------------------------------------------------
def grafico_por_dia(df: pd.DataFrame) -> alt.Chart:
    por_dia = (df.assign(dia=df["data_hora"].dt.normalize())
                 .groupby(["dia", "status"]).size().reset_index(name="quantidade"))
    return (
        alt.Chart(por_dia)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("yearmonthdate(dia):T", title=None, axis=alt.Axis(format="%d/%m", labelAngle=0)),
            y=alt.Y("quantidade:Q", title="Checklists", axis=alt.Axis(tickMinStep=1)),
            color=alt.Color(
                "status:N", title=None,
                scale=alt.Scale(domain=list(COR_STATUS), range=list(COR_STATUS.values())),
                legend=alt.Legend(orient="top"),
            ),
            tooltip=[
                alt.Tooltip("yearmonthdate(dia):T", title="Dia", format="%d/%m/%Y"),
                alt.Tooltip("status:N", title="Status"),
                alt.Tooltip("quantidade:Q", title="Checklists"),
            ],
        )
        .properties(height=280)
    )


def grafico_itens_nao_ok(respostas: pd.DataFrame) -> alt.Chart:
    contagem = (respostas[respostas["resposta"] != "OK"]
                .groupby("item").size()
                .reindex(list(ROTULOS_ITENS), fill_value=0)  # mostra também os itens com zero
                .reset_index(name="quantidade"))
    contagem["rotulo"] = contagem["item"].map(ROTULOS_ITENS)

    base = alt.Chart(contagem).encode(
        y=alt.Y("rotulo:N", title=None, sort=alt.EncodingSortField("quantidade", order="descending")),
        x=alt.X("quantidade:Q", title="Vezes marcado como NÃO OK", axis=alt.Axis(tickMinStep=1)),
        tooltip=[alt.Tooltip("rotulo:N", title="Item"), alt.Tooltip("quantidade:Q", title="NÃO OK")],
    )
    barras = base.mark_bar(color=COR_STATUS["REPROVADO"], cornerRadiusEnd=4, height=14)
    rotulos = base.mark_text(align="left", dx=4).encode(text="quantidade:Q")
    return (barras + rotulos).properties(height=280)


# --- Painel (redesenhado automaticamente a cada INTERVALO segundos) ---------
@st.fragment(run_every=INTERVALO)
def painel():
    estado = verificar_repositorio(str(REPO))

    # Aviso quando um commit novo chega enquanto a página está aberta.
    anterior = st.session_state.get("ultimo_commit")
    if anterior and anterior != estado.commit:
        st.toast(f"Novo commit recebido: {estado.mensagem}", icon="🔄")
    st.session_state["ultimo_commit"] = estado.commit

    if estado.erro:
        st.warning(f"Não foi possível consultar o GitHub — exibindo os últimos dados conhecidos.\n\n{estado.erro}")
    st.caption(
        f"Repositório no commit `{estado.commit}` — “{estado.mensagem}” · "
        f"verificado às {estado.verificado_em:%H:%M:%S} · atualização automática a cada {INTERVALO} s"
    )

    checklists, respostas, erros = ler_dados(str(PASTA_CHECKLISTS), assinatura_pasta(PASTA_CHECKLISTS))
    if erros:
        with st.expander(f"⚠️ {len(erros)} arquivo(s) não puderam ser lidos"):
            st.code("\n".join(erros))

    if checklists.empty:
        st.info("Nenhum checklist em formato JSON encontrado ainda em `checklists/`.\n\n"
                "Eles aparecem assim que o Raspberry Pi enviar o primeiro checklist com a versão nova "
                "do sistema (ou rode `dashboard/importar_pdfs_antigos.py` para importar o histórico).")
        return

    # --- Filtros (uma linha, acima de tudo que eles afetam) ---
    c1, c2 = st.columns([1, 3])
    periodo = c1.selectbox("Período", ["Tudo", "Hoje", "Últimos 7 dias", "Últimos 30 dias"], key="periodo")
    operadores = c2.multiselect("Operador", sorted(checklists["operador"].unique()), key="operadores",
                                placeholder="Todos os operadores")

    df = filtrar_periodo(checklists, periodo)
    if operadores:
        df = df[df["operador"].isin(operadores)]
    resp = respostas[respostas["id"].isin(df["id"])]

    # --- Indicadores ---
    total = len(df)
    aprovados = int((df["status"] == "APROVADO").sum())
    reprovados = total - aprovados
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Checklists", total)
    k2.metric("✅ Aprovados", aprovados)
    k3.metric("❌ Reprovados", reprovados)
    k4.metric("Taxa de aprovação", f"{aprovados / total:.0%}" if total else "—")

    if total == 0:
        st.info("Nenhum checklist no período/filtro selecionado.")
        return

    ultimo = df.iloc[0]
    st.markdown(
        f"**Último checklist:** {ICONE_STATUS[ultimo['status']]} — {ultimo['operador']} "
        f"(matrícula {ultimo['matricula']}) em {ultimo['data_hora']:%d/%m/%Y %H:%M}"
    )

    # --- Gráficos ---
    g1, g2 = st.columns(2)
    with g1:
        st.subheader("Checklists por dia")
        st.altair_chart(grafico_por_dia(df), use_container_width=True)
    with g2:
        st.subheader("Itens marcados como NÃO OK")
        st.altair_chart(grafico_itens_nao_ok(resp), use_container_width=True)

    # --- Tabela + detalhe ---
    st.subheader("Histórico")
    tabela = df.assign(status=df["status"].map(ICONE_STATUS))[
        ["data_hora", "operador", "matricula", "status", "itens_nao_ok", "pdf"]
    ]
    selecao = st.dataframe(
        tabela, hide_index=True, width="stretch",
        on_select="rerun", selection_mode="single-row", key="tabela_historico",
        column_config={
            "data_hora": st.column_config.DatetimeColumn("Data/Hora", format="DD/MM/YYYY HH:mm"),
            "operador": "Operador", "matricula": "Matrícula", "status": "Status",
            "itens_nao_ok": st.column_config.NumberColumn("Itens NÃO OK"),
            "pdf": "Arquivo PDF",
        },
    )
    linhas = selecao["selection"]["rows"]
    if linhas:
        escolhido = df.iloc[linhas[0]]
        col_titulo, col_botao = st.columns([3, 1], vertical_alignment="center")
        col_titulo.markdown(f"**Respostas de {escolhido['operador']} em {escolhido['data_hora']:%d/%m/%Y %H:%M}**")
        arquivo_pdf = PASTA_CHECKLISTS / escolhido["pdf"]
        if arquivo_pdf.is_file():
            col_botao.download_button(
                "⬇️ Baixar PDF",
                data=arquivo_pdf.read_bytes(),
                file_name=arquivo_pdf.name,
                mime="application/pdf",
                on_click="ignore",          # baixar não precisa redesenhar a página
                key=f"baixar_{escolhido['id']}",
                width="stretch",
            )
        else:
            col_botao.caption("PDF não encontrado no repositório.")
        detalhe = respostas[respostas["id"] == escolhido["id"]].sort_values("item")
        st.dataframe(
            detalhe.assign(resposta=detalhe["resposta"].map(lambda r: "✅ OK" if r == "OK" else "❌ NÃO OK"))
                   [["item", "pergunta", "resposta"]],
            hide_index=True, width="stretch",
            column_config={"item": "Nº", "pergunta": "Pergunta", "resposta": "Resposta"},
        )
    else:
        st.caption("Clique numa linha da tabela para ver as respostas daquele checklist.")


st.title("Checklists — Guincho Tracionador 1172")
painel()
