"""Dashboard dos checklists do Guincho Tracionador (GT)."""
import os
import sys
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.dados import ROTULOS_ITENS, assinatura_pasta, carregar_checklists  # noqa: E402
from nucleo.repositorio import verificar_e_atualizar  # noqa: E402
from tema_gbmx import (COR_APROVADO, COR_REPROVADO, aplicar_tema, arquivo_logo,  # noqa: E402
                       cabecalho, rodape, secao)

_COPIA_DEDICADA = Path(__file__).resolve().parent.parent.parent / "checklists-gt-dados"
REPO = Path(os.environ.get("CHECKLISTS_REPO", _COPIA_DEDICADA))
PASTA_CHECKLISTS = REPO / "checklists"
INTERVALO = int(os.environ.get("INTERVALO_SEGUNDOS", "30"))

COR_STATUS = {"APROVADO": COR_APROVADO, "REPROVADO": COR_REPROVADO}
ICONE_STATUS = {"APROVADO": "✅ APROVADO", "REPROVADO": "❌ REPROVADO"}

_logo = arquivo_logo()
st.set_page_config(
    page_title="Checklists GBMX",
    page_icon=str(_logo) if _logo and _logo.suffix == ".png" else "✅",
    layout="wide",
)
aplicar_tema()


@st.cache_data(ttl=max(5, INTERVALO // 2), show_spinner=False)
def _verificar_repositorio_cache(repo: str) -> dict:
    return asdict(verificar_e_atualizar(Path(repo)))


def verificar_repositorio(repo: str):
    return SimpleNamespace(**_verificar_repositorio_cache(repo))


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
                .reindex(list(ROTULOS_ITENS), fill_value=0)
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


@st.fragment(run_every=INTERVALO)
def painel():
    estado = verificar_repositorio(str(REPO))

    anterior = st.session_state.get("ultimo_commit")
    if anterior and anterior != estado.commit:
        st.toast(f"Novo commit recebido: {estado.mensagem}", icon="🔄")
    st.session_state["ultimo_commit"] = estado.commit

    if estado.erro:
        st.warning(f"Não foi possível consultar o GitHub — exibindo os últimos dados conhecidos.\n\n{estado.erro}")
    st.caption(f"Atualização automática a cada {INTERVALO} s · última verificação às {estado.verificado_em:%H:%M:%S}")

    checklists, respostas, erros = ler_dados(str(PASTA_CHECKLISTS), assinatura_pasta(PASTA_CHECKLISTS))
    if erros:
        with st.expander(f"⚠️ {len(erros)} arquivo(s) não puderam ser lidos"):
            st.code("\n".join(erros))

    if checklists.empty:
        st.info("Nenhum checklist em formato JSON encontrado ainda em `checklists/`.\n\n"
                "Eles aparecem assim que o Raspberry Pi enviar o primeiro checklist com a versão nova "
                "do sistema (ou rode `ferramentas/importar_pdfs_antigos.py` para importar o histórico).")
        return

    c1, c2 = st.columns([1, 3])
    periodo = c1.selectbox("Período", ["Tudo", "Hoje", "Últimos 7 dias", "Últimos 30 dias"], key="periodo")
    operadores = c2.multiselect("Operador", sorted(checklists["operador"].unique()), key="operadores",
                                placeholder="Todos os operadores")

    df = filtrar_periodo(checklists, periodo)
    if operadores:
        df = df[df["operador"].isin(operadores)]
    resp = respostas[respostas["id"].isin(df["id"])]

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

    g1, g2 = st.columns(2)
    with g1:
        secao("Checklists por dia")
        st.altair_chart(grafico_por_dia(df), use_container_width=True)
    with g2:
        secao("Itens marcados como NÃO OK")
        st.altair_chart(grafico_itens_nao_ok(resp), use_container_width=True)

    secao("Histórico")
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
                on_click="ignore",
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


cabecalho("Controle de Checklists de Segurança", "Guincho Tracionador 1172 · validação de equipamento antes da operação")
painel()
rodape()
