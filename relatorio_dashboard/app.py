import datetime

import pandas as pd
import streamlit as st

from charts import create_causa_raiz_chart, create_sla_trend_chart
from config import EXCEL_PATH, SLA_STATUS_EXCLUIDOS
from data_loader import get_excel_mtime, get_logo_base64, load_css, load_data, load_sla_rules
from tables import build_audit_table, build_consolidated_table
from ui_components import render_kpis, render_meta_cards, render_sla_rules

# ── Configuração da página ──────────────────────────────────────────────
st.set_page_config(
    page_title="UniATEND - Dashboard",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS (lido uma vez, cacheado) ────────────────────────────────────────
st.markdown(f"<style>{load_css()}</style>", unsafe_allow_html=True)

# ── Recursos globais ────────────────────────────────────────────────────
logo_b64  = get_logo_base64()
REGRAS_SLA = load_sla_rules()

# ── Dados (cache invalidado automaticamente quando o Excel muda) ────────
df = load_data(get_excel_mtime())
if df.empty:
    st.stop()

# ── Sidebar ─────────────────────────────────────────────────────────────
with st.sidebar:
    if logo_b64:
        st.markdown(
            f'<div style="display:flex;justify-content:center;padding:1.6rem 0 1.4rem;">'
            f'<img src="data:image/png;base64,{logo_b64}" style="max-width:152px;'
            f'filter:brightness(0) invert(1);" alt="Logo Agrocontar"/></div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div style="height:3px;background:linear-gradient(90deg,#68bd46 0%,'
        'rgba(104,189,70,0.0) 100%);border-radius:2px;margin-bottom:1.4rem;"></div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sidebar-section-title">📅 &nbsp;Configuração do Período</div>', unsafe_allow_html=True)

    min_date = df["Data Abertura"].min().date()
    max_date = df["Data Abertura"].max().date()

    datas = st.date_input(
        "Filtrar Período para Análise",
        value=[min_date, max_date],
        min_value=min_date,
        max_value=max_date,
        format="DD/MM/YYYY",
    )

    if len(datas) != 2:
        st.info("Selecione a data final no calendário para continuar.")

    st.markdown("<div style='margin:1.2rem 0 0.3rem'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div style="height:1px;background:rgba(104,189,70,0.28);'
        'border-radius:1px;margin:0.5rem 0 1.3rem;"></div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sidebar-section-title">🎯 &nbsp;Filtros Operacionais</div>', unsafe_allow_html=True)

    modulos_disp = df["Módulo"].dropna().unique().tolist()
    modulo_selecionado = st.multiselect("Módulos", options=modulos_disp, default=modulos_disp)

    status_disp = df["Status"].dropna().unique().tolist()
    status_concluido = st.multiselect(
        "Status de Atendimento",
        options=status_disp,
        default=[s for s in status_disp if "conclu" in s.lower() or "fechad" in s.lower()],
        help="Apenas estes status entram na conta de SLA.",
    )

    st.markdown(
        '<div style="margin-top:3rem;padding-top:1rem;border-top:1px solid rgba(104,189,70,0.2);'
        'text-align:center;"><span style="color:rgba(255,255,255,0.35);font-size:0.68rem;">'
        'Inovação Agrocontar</span></div>',
        unsafe_allow_html=True,
    )

# ── Aguarda período completo antes de renderizar o conteúdo ────────────
if len(datas) != 2:
    st.stop()

data_inicio, data_fim = datas

# ── Máscaras de filtragem ───────────────────────────────────────────────
data_inicio_prev = pd.Timestamp(data_inicio) - pd.DateOffset(months=1)
data_fim_prev    = pd.Timestamp(data_fim)    - pd.DateOffset(months=1)
texto_comp = f"vs ({data_inicio_prev.strftime('%d/%m')} a {data_fim_prev.strftime('%d/%m')})"


def _mask(inicio, fim):
    return (
        (df["Data Abertura"].dt.date >= inicio)
        & (df["Data Abertura"].dt.date <= fim)
        & df["Módulo"].isin(modulo_selecionado)
    )


df_atual = df[_mask(data_inicio, data_fim)].copy()
df_prev  = df[_mask(data_inicio_prev.date(), data_fim_prev.date())].copy()

if df_atual.empty:
    st.warning("Nenhum dado encontrado no período selecionado.")
    st.stop()

# ── Título e metadados ──────────────────────────────────────────────────
st.markdown(
    '<span class="title-accent"></span>'
    '<h1 style="display:inline">Inteligência de Atendimento: SLA & Qualidade</h1>',
    unsafe_allow_html=True,
)
st.markdown("Visão focada na evolução e cumprimento de metas da operação.")

if EXCEL_PATH.exists():
    mtime = EXCEL_PATH.stat().st_mtime
    ultima_at  = datetime.datetime.fromtimestamp(mtime)
    proxima_at = ultima_at + datetime.timedelta(days=7)
    st.markdown(
        f'<div style="margin-top:6px;font-size:0.8rem;color:#6b7280;">'
        f'Atualização dos Dados: <b>{ultima_at.strftime("%d/%m/%Y às %H:%M")}</b> | '
        f'Próxima atualização prevista: <b>{proxima_at.strftime("%d/%m/%Y")}</b>'
        f'</div>',
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# ── KPIs ────────────────────────────────────────────────────────────────
with st.container(border=True):
    render_kpis(df_atual, df_prev, status_concluido, data_fim.month, texto_comp)

st.markdown("<br>", unsafe_allow_html=True)

# ── Abas ────────────────────────────────────────────────────────────────
tab_comp, tab_cons, tab_det, tab_dados = st.tabs([
    "📊  Visão Comparativa Mês a Mês",
    "📈  Consolidado Operacional",
    "📋  Auditoria (Ticket Individual)",
    "⚙️  Dados & Regras SLA",
])

# ── TAB 1: Comparativa ──────────────────────────────────────────────────
with tab_comp:
    st.markdown("##### Histórico de Tendências e Projeções")

    mask_tend = (df["Data Abertura"].dt.date <= data_fim) & df["Módulo"].isin(modulo_selecionado)
    df_tend = df[mask_tend].copy()

    col_c1, col_c2 = st.columns(2)

    with col_c1:
        with st.container(border=True):
            df_concl   = df_tend[df_tend["Status"].isin(status_concluido)]
            df_sla_val = df_concl[~df_concl["Status SLA"].isin(SLA_STATUS_EXCLUIDOS)]
            fig1 = create_sla_trend_chart(df_sla_val)
            if fig1:
                st.plotly_chart(fig1, use_container_width=True, theme=None)
            else:
                st.info("Sem dados SLA válidos no período para exibir a tendência.")

    with col_c2:
        with st.container(border=True):
            fig2 = create_causa_raiz_chart(df_tend)
            st.plotly_chart(fig2, use_container_width=True, theme=None)

# ── TAB 2: Consolidado ──────────────────────────────────────────────────
with tab_cons:
    st.markdown("##### Tabelas Semânticas do Período Filtrado")

    visao = st.radio("Agrupar dados por:", ["Categoria", "Módulo", "Tipo"], horizontal=True)

    if visao not in df_atual.columns or df_atual[visao].dropna().empty:
        st.warning(f"Sem dados suficientes na coluna '{visao}' para consolidar.")
    else:
        st.dataframe(build_consolidated_table(df_atual, visao), use_container_width=True, hide_index=True)

# ── TAB 3: Auditoria ────────────────────────────────────────────────────
with tab_det:
    st.markdown("##### Auditoria Analítica (Linha a Linha)")

    col_b1, col_b2 = st.columns([2, 1])
    id_busca = col_b1.text_input("🔍 Buscar por ID de Ticket", placeholder="Ex: 12345")

    labels_disp = ["Todos"]
    if "Status_SLA_Label" in df_atual.columns:
        labels_disp += sorted(df_atual["Status_SLA_Label"].dropna().unique().tolist())
    filtro_status = col_b2.selectbox("Filtrar por Status SLA", options=labels_disp)

    st.dataframe(
        build_audit_table(df_atual, id_busca, filtro_status),
        use_container_width=True,
        hide_index=True,
        height=500,
    )

# ── TAB 4: Dados & Regras ───────────────────────────────────────────────
with tab_dados:
    st.markdown("##### Fonte de Dados Utilizada")

    col_dl, col_info = st.columns([1, 2], gap="large")

    with col_dl:
        with st.container(border=True):
            st.markdown(
                '<div style="text-align:center;padding:0.6rem 0 0.4rem;">'
                '<div style="font-size:2.8rem;line-height:1;">📥</div>'
                '<div style="font-weight:700;color:#013d24;font-size:1rem;margin-top:0.5rem;">'
                'relatorio_classificado.xlsx</div>'
                '<div style="font-size:0.78rem;color:#6b7280;margin-top:0.25rem;">'
                'Base completa sem filtros aplicados</div></div>',
                unsafe_allow_html=True,
            )
            st.markdown("<div style='margin-top:0.8rem'></div>", unsafe_allow_html=True)
            if EXCEL_PATH.exists():
                st.download_button(
                    label="⬇️ Baixar Excel",
                    data=EXCEL_PATH.read_bytes(),
                    file_name="relatorio_classificado.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            else:
                st.warning("Arquivo não localizado.")

    with col_info:
        with st.container(border=True):
            d_min  = df["Data Abertura"].min().strftime("%d/%m/%Y")
            d_max  = df["Data Abertura"].max().strftime("%d/%m/%Y")
            mods   = ", ".join(sorted(df["Módulo"].dropna().unique().tolist()))
            st.markdown(
                f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.9rem 1.4rem;padding:0.2rem 0;">'
                f'<div><div style="font-size:0.68rem;font-weight:700;color:#7a9e88;text-transform:uppercase;">Total de Registros</div>'
                f'<div style="font-size:1.4rem;font-weight:700;color:#02683d;">{len(df):,}</div></div>'
                f'<div><div style="font-size:0.68rem;font-weight:700;color:#7a9e88;text-transform:uppercase;">Colunas</div>'
                f'<div style="font-size:1.4rem;font-weight:700;color:#02683d;">{len(df.columns)}</div></div>'
                f'<div><div style="font-size:0.68rem;font-weight:700;color:#7a9e88;text-transform:uppercase;">Período Coberto</div>'
                f'<div style="font-size:0.9rem;font-weight:600;color:#1f2937;">{d_min} → {d_max}</div></div>'
                f'<div><div style="font-size:0.68rem;font-weight:700;color:#7a9e88;text-transform:uppercase;">Módulos</div>'
                f'<div style="font-size:0.9rem;font-weight:600;color:#1f2937;">{mods}</div></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("##### Regras de SLA Atualmente Aplicadas")
    with st.container(border=True):
        st.markdown(
            '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:12px;'
            'padding:0.85rem 1.1rem;margin-bottom:1.4rem;font-size:0.82rem;color:#166534;line-height:1.6;">'
            '<b>Como funciona:</b> cada ticket é classificado por <b>Módulo</b> e <b>Categoria</b>. '
            'O sistema localiza a regra e compara o <b>Tempo Gasto</b> com os limites de '
            '<span style="color:#1d4ed8;font-weight:600;">Piso (mín.)</span> e '
            '<span style="color:#b91c1c;font-weight:600;">Teto (máx.)</span>. '
            'Regras com <i>Prazo Não Aplicável</i> são excluídas do cálculo de estouro.</div>',
            unsafe_allow_html=True,
        )
        render_sla_rules(REGRAS_SLA)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("##### Tolerâncias Máximas de Estouro por Mês")
    render_meta_cards()
