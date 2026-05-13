import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import datetime
import os
import base64
import json

# ==============================
# 1. CONFIGURAÇÃO DA PÁGINA
# ==============================
st.set_page_config(
    page_title="UniATEND - Dashboard",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================
# LOGO EM BASE64
# ==============================
def get_logo_base64():
    logo_path = "1775153144791_image.png"
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None

logo_b64 = get_logo_base64()

# ==============================
# CSS CUSTOMIZADO — TEMA AGROCONTAR
# ==============================
st.markdown("""
<style>
/* ── Google Font ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&display=swap');

/* ─────────────────────────────────────────
   BASE (Blindagem contra Dark Mode)
───────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif !important;
}

.stApp {
    background-color: #f0f4f1;
    color: #1f2937; /* Força o texto base escuro */
}

/* ─────────────────────────────────────────
   SIDEBAR
───────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #02683d !important;
    border-right: none !important;
    box-shadow: 8px 0 32px rgba(2, 104, 61, 0.15) !important;
    border-radius: 0 24px 24px 0 !important; 
}

[data-testid="stSidebar"] > div:first-child {
    background: transparent !important;
    padding: 0 !important;
}

[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    padding: 0 1rem 2rem 1rem;
    background: transparent !important;
}

[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span:not([data-baseweb]),
[data-testid="stSidebar"] div.stMarkdown p,
[data-testid="stSidebar"] .stHeader,
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #ffffff !important;
}

[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stWidgetLabel p,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
    color: #b2dfce !important;
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.07em !important;
}

[data-testid="stSidebar"] hr {
    border: none !important;
    border-top: 1px solid rgba(104, 189, 70, 0.3) !important;
    margin: 1rem 0 !important;
}

[data-testid="stSidebar"] .stDateInput > div > div,
[data-testid="stSidebar"] .stMultiSelect > div > div,
[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background-color: rgba(255, 255, 255, 0.12) !important;
    border: 1px solid rgba(104, 189, 70, 0.45) !important;
    border-radius: 10px !important;
    color: #ffffff !important;
    transition: border-color 0.2s;
}

[data-testid="stSidebar"] [data-baseweb="select"] > div:hover,
[data-testid="stSidebar"] .stDateInput > div > div:focus-within {
    border-color: #68bd46 !important;
    background-color: rgba(255,255,255,0.18) !important;
}

[data-testid="stSidebar"] [data-baseweb="select"] input,
[data-testid="stSidebar"] [data-baseweb="select"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] input[type="text"] {
    color: #ffffff !important;
}

[data-testid="stSidebar"] [data-baseweb="tag"] {
    background-color: #68bd46 !important;
    border: none !important;
    border-radius: 6px !important;
}
[data-testid="stSidebar"] [data-baseweb="tag"] span {
    color: #ffffff !important;
}

[data-testid="stSidebar"] [data-baseweb="select"] svg,
[data-testid="stSidebar"] .stDateInput svg {
    fill: rgba(255,255,255,0.7) !important;
}

.sidebar-section-title {
    color: #a8dfc0 !important;
    font-size: 0.68rem !important;
    font-weight: 700 !important;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 0.6rem;
    display: flex;
    align-items: center;
    gap: 6px;
}

/* ─────────────────────────────────────────
   MAIN CONTENT
───────────────────────────────────────── */
.main .block-container {
    padding-top: 1.8rem;
    padding-left: 2.4rem;
    padding-right: 2.4rem;
    max-width: 1440px;
}

.stApp h1 {
    font-size: 1.65rem !important;
    font-weight: 700 !important;
    color: #013d24 !important;
    letter-spacing: -0.02em;
    margin-bottom: 0.1rem;
    line-height: 1.2;
}

.title-accent {
    display: inline-block;
    width: 5px;
    height: 1.5rem;
    background: linear-gradient(180deg, #68bd46 0%, #02683d 100%);
    border-radius: 4px;
    margin-right: 0.55em;
    vertical-align: middle;
}

/* ─────────────────────────────────────────
   METRIC CARDS
───────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #ffffff !important;
    border-radius: 16px !important;
    padding: 1.1rem 1.35rem 0.95rem !important;
    border: 1px solid #dce8e1 !important;
    box-shadow: 0 2px 14px rgba(2, 104, 61, 0.07) !important;
    transition: box-shadow 0.25s ease, transform 0.25s ease !important;
}
[data-testid="stMetric"]:hover {
    box-shadow: 0 8px 28px rgba(2, 104, 61, 0.13) !important;
    transform: translateY(-2px) !important;
}

[data-testid="stMetricLabel"] {
    display: flex;
    align-items: center;
    gap: 6px;
}
[data-testid="stMetricLabel"] > div,
[data-testid="stMetricLabel"] p {
    font-size: 0.73rem !important;
    font-weight: 600 !important;
    color: #7a9e88 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.07em !important;
}

[data-testid="stMetricLabel"] div[data-testid="stTooltipHoverTarget"] svg {
    fill: #a7b5ac !important;
    width: 15px !important;
    height: 15px !important;
}

[data-testid="stMetricValue"] > div {
    font-size: 1.9rem !important;
    font-weight: 700 !important;
    color: #02683d !important;
    line-height: 1.1 !important;
}

[data-testid="stMetricDelta"] > div {
    font-size: 0.78rem !important;
    font-weight: 800 !important;
    margin-top: 0.15rem !important;
}

/* ─────────────────────────────────────────
   CONTAINERS COM BORDA
───────────────────────────────────────── */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 18px !important;
    overflow: hidden !important;
}
[data-testid="stVerticalBlockBorderWrapper"] > div {
    background: #ffffff !important;
    border-radius: 18px !important;
    border: 1px solid #dce8e1 !important;
    box-shadow: 0 3px 18px rgba(2, 104, 61, 0.06) !important;
    padding: 1.2rem 1.4rem !important;
}

/* ─────────────────────────────────────────
   TABS E OUTROS ELEMENTOS
───────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    gap: 0.2rem !important;
    border-bottom: 2px solid #cddfd5 !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    border: none !important;
    border-bottom: 3px solid transparent !important;
    border-radius: 0 !important;
    padding: 0.6rem 1.3rem !important;
    margin-bottom: -2px !important;
    font-size: 0.86rem !important;
    font-weight: 500 !important;
    color: #718a7b !important;
    transition: color 0.18s, border-color 0.18s !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #02683d !important;
}
.stTabs [aria-selected="true"] {
    color: #02683d !important;
    font-weight: 700 !important;
    border-bottom: 3px solid #68bd46 !important;
}
.stTabs [data-baseweb="tab-panel"] {
    padding-top: 1.5rem !important;
}

.stApp h5 {
    color: #02683d !important;
    font-size: 0.78rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.09em !important;
    border-bottom: 1px solid #dce8e1 !important;
    padding-bottom: 0.4rem !important;
    margin-bottom: 1rem !important;
}

.stRadio label p {
    font-size: 0.85rem !important;
    color: #3a4f40 !important;
}
.stRadio [data-baseweb="radio"] div:first-child {
    border-color: #68bd46 !important;
}
.stRadio [data-baseweb="radio"][data-checked="true"] div:first-child {
    background-color: #68bd46 !important;
    border-color: #68bd46 !important;
}

/* ─────────────────────────────────────────
   DATAFRAMES (Tabelas)
───────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border-radius: 12px !important;
    overflow: hidden !important;
    border: 1px solid #dce8e1 !important;
    box-shadow: 0 2px 10px rgba(2, 104, 61, 0.05) !important;
}

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #eaf2ec; }
::-webkit-scrollbar-thumb { background: #9dcfae; border-radius: 6px; }
::-webkit-scrollbar-thumb:hover { background: #68bd46; }

/* ─────────────────────────────────────────
   CARTÕES SLA (aba de regras)
───────────────────────────────────────── */
.sla-card {
    background: #ffffff;
    border: 1px solid #dce8e1;
    border-radius: 14px;
    padding: 1rem 1.2rem;
    box-shadow: 0 2px 10px rgba(2, 104, 61, 0.06);
    margin-bottom: 0.8rem;
    transition: box-shadow 0.2s ease, transform 0.2s ease;
}
.sla-card:hover {
    box-shadow: 0 6px 22px rgba(2, 104, 61, 0.12);
    transform: translateY(-2px);
}
.sla-card-title {
    font-size: 0.9rem;
    font-weight: 700;
    color: #013d24;
    margin-bottom: 0.45rem;
}
.sla-card-modulo {
    display: inline-block;
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 2px 10px;
    border-radius: 20px;
    margin-bottom: 0.6rem;
}
.sla-card-modulo.unifiscal { background: #3362a9; color: #ffffff; }
.sla-card-modulo.unidp     { background: #7b4e99; color: #ffffff; }
.sla-card-modulo.ambos     { background: #fef3c7; color: #92400e; }
.sla-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 0.8rem;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 8px;
    margin-right: 6px;
}
.sla-badge.piso { background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }
.sla-badge.teto { background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; }
.sla-badge.na   { background: #f3f4f6; color: #6b7280; border: 1px solid #e5e7eb; font-style: italic; }
.sla-nota {
    margin-top: 0.5rem;
    font-size: 0.75rem;
    color: #d97706;
    font-style: italic;
}
.download-hero {
    background: linear-gradient(135deg, #02683d 0%, #1a8c55 100%);
    border-radius: 18px;
    padding: 2rem 2.2rem;
    color: #ffffff;
    margin-bottom: 1.6rem;
}
.download-hero h3 {
    color: #ffffff !important;
    font-size: 1.1rem !important;
    margin-bottom: 0.3rem !important;
    border: none !important;
    padding: 0 !important;
    text-transform: none !important;
    letter-spacing: normal !important;
}
.download-hero p {
    color: rgba(255,255,255,0.78) !important;
    font-size: 0.85rem !important;
    margin: 0 !important;
}
            
button[kind="secondary"] {
    background-color: #68bd46 !important;
    color: white !important;
}

button[kind="secondary"]:hover {
    background-color: #02683d !important;
}
</style>
""", unsafe_allow_html=True)

# ─── Paleta Plotly alinhada à marca ───
BRAND_COLORS  = ["#02683d", "#68bd46", "#1a8c55", "#a8d96a", "#014d2d", "#4aae6f"]

# Layout base para todos os gráficos Plotly
def plotly_base_layout(title_text, y_title):
    return dict(
        paper_bgcolor="#ffffff",
        plot_bgcolor="#fafcfb",
        font=dict(family="Inter, sans-serif", color="#3a4f40", size=12),
        title=dict(
            text=title_text,
            font=dict(size=15, color="#02683d", family="Inter, sans-serif", weight="bold"),
            x=0, xanchor="left", pad=dict(l=4)
        ),
        yaxis=dict(
            title=y_title,
            title_font=dict(size=11, color="#5a7264"),
            gridcolor="#e8f0ea",
            gridwidth=1,
            linecolor="#cddfd5",
            tickfont=dict(size=11, color="#3a4f40"),
            zeroline=False,
        ),
        xaxis=dict(
            showgrid=False,
            linecolor="#cddfd5",
            tickfont=dict(size=11, color="#3a4f40"),
        ),
        legend=dict(
            orientation="h",
            yanchor="top", y=-0.15,
            xanchor="center", x=0.5,
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#dce8e1",
            borderwidth=1,
            font=dict(size=11, color="#3a4f40")
        ),
        margin=dict(t=70, l=56, r=24, b=80),
        height=480,
    )

# ==============================
# REGRAS DE NEGÓCIO E LIMITES
# ==============================
BASELINE_HISTORICO = 0.48
METAS_SLA_MENSAL = {4: 0.35, 5: 0.25, 6: 0.15}

# ==============================
# REGRAS SLA
# ==============================
with open("../sla_rules.json", encoding="utf-8") as _f:
    REGRAS_SLA = json.load(_f)

# ==============================
# CARREGAMENTO E LIMPEZA COM TTL NO CACHE
# ==============================
@st.cache_data(ttl=3600)
def load_data():
    try:
        df = pd.read_excel("relatorio_classificado.xlsx")
        if "Data Abertura" in df.columns:
            df["Data Abertura"] = pd.to_datetime(df["Data Abertura"], dayfirst=True, errors="coerce")
            
        colunas_numericas = ["SLA Piso", "SLA Teto", "% Consumo SLA", "Tempo Gasto (Horas)", "Prioridade"]
        for col in colunas_numericas:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
                
        if "Causa Raíz" in df.columns:
            df["Causa_Raiz_Preenchida"] = df["Causa Raíz"].replace(r'^\s*$', np.nan, regex=True).notna()
        else:
            df["Causa_Raiz_Preenchida"] = False
            
        df["Mês/Ano"]  = df["Data Abertura"].dt.to_period("M").dt.to_timestamp()
        df["Mês_Nome"] = df["Data Abertura"].dt.strftime('%b/%Y')
        df["Mes_Int"]  = df["Data Abertura"].dt.month
        return df.dropna(subset=["Data Abertura"])
    except Exception as e:
        st.error(f"Erro ao carregar relatorio_classificado.xlsx: {e}")
        return pd.DataFrame()

df = load_data()
if df.empty:
    st.stop()

# ==============================
# BARRA LATERAL E FILTROS
# ==============================
with st.sidebar:
    if logo_b64:
        st.markdown(
            f"""
            <div style="display:flex; justify-content:center; align-items:center; padding: 1.6rem 0 1.4rem;">
                <img src="data:image/png;base64,{logo_b64}" style="max-width:152px; filter: brightness(0) invert(1);" alt="Logo"/>
            
            </div>
            """, unsafe_allow_html=True
        )

    st.markdown(
        '<div style="height:3px; background: linear-gradient(90deg, #68bd46 0%, rgba(104,189,70,0.0) 100%); border-radius:2px; margin-bottom:1.4rem;"></div>',
        unsafe_allow_html=True
    )

    st.markdown('<div class="sidebar-section-title">📅 &nbsp;Configuração do Período</div>', unsafe_allow_html=True)

    min_date = df["Data Abertura"].min().date()
    max_date = df["Data Abertura"].max().date()
    
    # Tratamento contra o estado incompleto do st.date_input
    datas_selecionadas = st.date_input(
        "Filtrar Período para Análise",
        value=[min_date, max_date],
        min_value=min_date,
        max_value=max_date,
        format="DD/MM/YYYY"
    )
    
    if len(datas_selecionadas) == 2:
        data_inicio, data_fim = datas_selecionadas
    else:
        st.info("👆 Selecione a data final no calendário para atualizar os dados.")
        st.stop()

    st.markdown("<div style='margin:1.2rem 0 0.3rem'></div>", unsafe_allow_html=True)
    st.markdown('<div style="height:1px; background:rgba(104,189,70,0.28); border-radius:1px; margin:0.5rem 0 1.3rem;"></div>', unsafe_allow_html=True)

    st.markdown('<div class="sidebar-section-title">🎯 &nbsp;Filtros Operacionais</div>', unsafe_allow_html=True)

    modulos = df["Módulo"].dropna().unique().tolist()
    modulo_selecionado = st.multiselect("Módulos", options=modulos, default=modulos)

    status_disp = df["Status"].dropna().unique().tolist()
    status_concluido = st.multiselect(
        "Status de Atendimento",
        options=status_disp,
        default=[s for s in status_disp if "conclu" in s.lower() or "fechad" in s.lower()],
        help="Apenas estes status entram na conta de SLA."
    )

    st.markdown(
        """
        <div style="margin-top: 3rem; padding-top: 1rem; border-top: 1px solid rgba(104,189,70,0.2); text-align: center;">
            <span style="color:rgba(255,255,255,0.35); font-size:0.68rem; letter-spacing:0.05em;">
                2026 Inovação Agrocontar
            </span>
        </div>
        """, unsafe_allow_html=True
    )

# --- Processamento de Datas Comparativas ---
data_inicio_prev = pd.Timestamp(data_inicio) - pd.DateOffset(months=1)
data_fim_prev    = pd.Timestamp(data_fim)    - pd.DateOffset(months=1)

texto_comparativo_periodo = f"vs ({data_inicio_prev.strftime('%d/%m')} a {data_fim_prev.strftime('%d/%m')})"

mask_atual = (df["Data Abertura"].dt.date >= data_inicio) & (df["Data Abertura"].dt.date <= data_fim) & df["Módulo"].isin(modulo_selecionado)
mask_prev = (df["Data Abertura"].dt.date >= data_inicio_prev.date()) & (df["Data Abertura"].dt.date <= data_fim_prev.date()) & df["Módulo"].isin(modulo_selecionado)

df_atual = df[mask_atual].copy()
df_prev  = df[mask_prev].copy()

if df_atual.empty:
    st.warning("Nenhum dado encontrado no período selecionado.")
    st.stop()

# ==============================
# TÍTULO DA PÁGINA
# ==============================
st.markdown('<span class="title-accent"></span><h1 style="display:inline">Inteligência de Atendimento: SLA & Qualidade</h1>', unsafe_allow_html=True)
st.markdown("Visão focada na evolução e cumprimento de metas da operação.")

# 📅 Data de atualização técnica
caminho_arquivo = "relatorio_classificado.xlsx"
if os.path.exists(caminho_arquivo):
    timestamp_modificacao = os.path.getmtime(caminho_arquivo)
    ultima_atualizacao = datetime.datetime.fromtimestamp(timestamp_modificacao)
    proxima_atualizacao = ultima_atualizacao + datetime.timedelta(days=7)

    st.markdown(
        f"""
        <div style="margin-top:6px; font-size:0.8rem; color:#6b7280;">
            Atualização dos Dados: <b>{ultima_atualizacao.strftime('%d/%m/%Y às %H:%M')}</b> |
            Próxima atualização prevista: <b>{proxima_atualizacao.strftime('%d/%m/%Y')}</b>
        </div>
        """,
        unsafe_allow_html=True
    )

st.markdown("<br>", unsafe_allow_html=True)

# ==============================
# KPIs GERAIS E INJEÇÃO CORRETIVA DE COR
# ==============================
def calcular_kpis(dados):
    if dados.empty: return 0, 0, 0
    vol = len(dados)
    concluidos = dados[dados["Status"].isin(status_concluido)]
    com_sla = concluidos[~concluidos["Status SLA"].isin(["SLA Não Definido", "Sem Registro de Tempo", "Prazo Não Aplicável"])]
    pct_estouro = (len(com_sla[com_sla["Status SLA"] == "Acima do Teto (Nota: Tempo Corrido Bruto)"]) / len(com_sla)) if len(com_sla) > 0 else 0
    tx_causa = dados["Causa_Raiz_Preenchida"].mean()
    return vol, pct_estouro, tx_causa

vol_at, pct_estouro_at, tx_causa_at = calcular_kpis(df_atual)
vol_pr, pct_estouro_pr, tx_causa_pr = calcular_kpis(df_prev)
meta_atual_num = METAS_SLA_MENSAL.get(data_fim.month, None)

with st.container(border=True):
    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Volume de Tickets", 
        f"{vol_at}", 
        delta=f"{vol_at - vol_pr} {texto_comparativo_periodo}", 
        delta_color="inverse",
        help="Quantidade total de tickets abertos no período filtrado."
    )

    delta_estouro = (pct_estouro_at - pct_estouro_pr) * 100
    col2.metric(
        "% Estouro SLA (Concluídos)",
        f"{pct_estouro_at*100:.1f}%",
        delta=f"{delta_estouro:.1f}% {texto_comparativo_periodo}",
        delta_color="inverse",
        help="Proporção de tickets que foram finalizados e cujo tempo de resolução ultrapassou o teto."
    )

    if meta_atual_num is not None:
        folga = meta_atual_num - pct_estouro_at
        col3.metric(
            f"Tolerância Máxima (Mês {data_fim.month})",
            f"< {meta_atual_num*100:.0f}%",
            delta=f"{folga*100:.1f}% de margem segura" if folga >= 0 else f"{abs(folga)*100:.1f}% acima da tolerância",
            delta_color="normal" if folga >= 0 else "inverse",
            help="Meta gerencial de volume MÁXIMO permitido de tickets fora do SLA para o mês corrente."
        )
    else:
        col3.metric(
            f"Tolerância Máxima (Mês {data_fim.month})", "N/A",
            help="Período opera no Baseline Histórico de 48%. Metas restritivas iniciam a partir de Abril."
        )

    # 🔥 MUDANÇA: Injeção robusta de CSS garantindo que o delta desativado fique Cinza Escuro
    delta_causa = (tx_causa_at - tx_causa_pr) * 100
    cor_delta_causa = "off" if tx_causa_at == 0 else "normal"
    
    if tx_causa_at == 0:
        st.markdown("""
        <style>
        /* Seleciona rigidamente a coluna 4 para injetar a cor cinza-chumbo (#4b5563) de fácil leitura no branco */
        div[data-testid="stHorizontalBlock"] > div:nth-child(4) [data-testid="stMetricDelta"] > div {
            color: #4b5563 !important;
        }
        div[data-testid="stHorizontalBlock"] > div:nth-child(4) [data-testid="stMetricDelta"] svg {
            fill: #4b5563 !important;
        }
        </style>
        """, unsafe_allow_html=True)
        
    col4.metric(
        "% Causa Raiz Documentada",
        f"{tx_causa_at*100:.1f}%",
        delta=f"{delta_causa:.1f}% {texto_comparativo_periodo}",
        delta_color=cor_delta_causa,
        help="Proporção de tickets no período com o campo 'Causa Raíz' preenchido."
    )

st.markdown("<br>", unsafe_allow_html=True)

# ==============================
# ABAS E ESTILIZAÇÃO MESTRE DA TABELA
# ==============================

# 🔥 MUDANÇA: Definição do Header e Listrado Suave (Zebra) 
# Isso obriga a tabela do Streamlit a abandonar o header preto e as linhas brancas maciças
header_styles = [
    {'selector': 'th', 'props': [
        ('background-color', '#e2e8f0 !important'),  # Cinza claro moderno no cabeçalho
        ('color', '#1f2937 !important'),             # Texto escuro para contraste
        ('font-weight', '700 !important'),
        ('border-bottom', '2px solid #cbd5e1 !important')
    ]},
    {'selector': 'td', 'props': [
        ('border-bottom', '1px solid #f1f5f9 !important') # Linha sutil separando células
    ]}
]

# Função para aplicar o efeito Zebra (listra sim, listra não) nas tabelas
def zebra_color(row):
    # Pinta linhas pares com cinza levíssimo (#f8fafc) e ímpares de branco (#ffffff)
    bg = '#f8fafc' if row.name % 2 == 0 else '#ffffff'
    return [f'background-color: {bg}; color: #1f2937'] * len(row)

tab_comp, tab_cons, tab_det, tab_dados = st.tabs([
    "📊  Visão Comparativa Mês a Mês",
    "📈  Consolidado Operacional",
    "📋  Auditoria (Ticket Individual)",
    "⚙️  Dados & Regras SLA"
])

# ─────────────────────────────
# TAB 1 — COMPARATIVA
# ─────────────────────────────
with tab_comp:
    st.markdown("##### Histórico de Tendências e Projeções")

    mask_tendencia = (df["Data Abertura"].dt.date <= data_fim) & df["Módulo"].isin(modulo_selecionado)
    df_tendencia   = df[mask_tendencia].copy()

    col_c1, col_c2 = st.columns(2)

    with col_c1:
        with st.container(border=True):
            df_concl_tend  = df_tendencia[df_tendencia["Status"].isin(status_concluido)]
            df_sla_validos = df_concl_tend[~df_concl_tend["Status SLA"].isin(
                ["SLA Não Definido", "Sem Registro de Tempo", "Prazo Não Aplicável"]
            )]

            if not df_sla_validos.empty:
                df_trend = (
                    df_sla_validos
                    .groupby(["Mês/Ano", "Mês_Nome", "Mes_Int"])["Status SLA"]
                    .agg(lambda s: (s == "Acima do Teto (Nota: Tempo Corrido Bruto)").mean() * 100)
                    .reset_index(name="% Estouro")
                )

                df_trend["Tolerancia_Oficial"] = df_trend["Mes_Int"].map(METAS_SLA_MENSAL) * 100

                fig1 = go.Figure()

                fig1.add_trace(go.Bar(
                    x=df_trend["Mês_Nome"],
                    y=df_trend["% Estouro"],
                    name="% Realizado",
                    marker=dict(color="#02683d", line=dict(width=0), opacity=0.9),
                    text=df_trend["% Estouro"].apply(lambda v: f"{v:.1f}%"),
                    textposition="auto",
                    textfont=dict(color="white", size=12, family="Inter")
                ))

                if df_trend["Tolerancia_Oficial"].notna().any():
                    fig1.add_trace(go.Scatter(
                        x=df_trend["Mês_Nome"],
                        y=df_trend["Tolerancia_Oficial"],
                        mode="lines+markers+text",
                        name="% Máximo Tolerado (Meta)",
                        line=dict(color="#e05c2a", dash="solid", width=2.5),
                        marker=dict(size=10, color="#e05c2a", line=dict(width=2, color="#ffffff")),
                        text=df_trend["Tolerancia_Oficial"].apply(lambda v: f"Máx: {v:.0f}%" if pd.notna(v) else ""),
                        textposition="top center",
                        textfont=dict(color="#e05c2a", size=12, family="Inter"),
                        connectgaps=False
                    ))

                fig1.add_hline(
                    y=BASELINE_HISTORICO * 100,
                    line_dash="dot",
                    line_color="#c49a00",
                    line_width=2,
                    annotation_text=f"Baseline Gerencial ({BASELINE_HISTORICO*100:.0f}%)",
                    annotation_position="top left",
                    annotation_font_color="#c49a00",
                    annotation_font_size=11
                )

                layout = plotly_base_layout("Desempenho de SLA vs Tolerância Redutiva", "% Acima do Teto")
                fig1.update_layout(**layout)
                fig1.update_yaxes(range=[0, max(100, df_trend["% Estouro"].max() + 20)])

                st.plotly_chart(fig1, use_container_width=True, theme=None)

    with col_c2:
        with st.container(border=True):
            df_cr_trend = df_tendencia.groupby(["Mês_Nome", "Mês/Ano", "Módulo"]).agg(
                Vol=("ID", "count"),
                Preench=("Causa_Raiz_Preenchida", "sum")
            ).reset_index()
            df_cr_trend["% Causa Raiz"] = (df_cr_trend["Preench"] / df_cr_trend["Vol"]) * 100
            df_cr_trend = df_cr_trend.sort_values("Mês/Ano")

            fig2 = px.line(
                df_cr_trend,
                x="Mês_Nome", y="% Causa Raiz",
                color="Módulo",
                markers=True, text="% Causa Raiz",
                color_discrete_sequence=BRAND_COLORS
            )
            fig2.update_traces(
                texttemplate="%{text:.1f}%",
                textposition="top center",
                textfont=dict(size=11, family="Inter"),
                line=dict(width=2.2),
                marker=dict(size=9, line=dict(width=2, color="#ffffff"))
            )

            layout2 = plotly_base_layout("Evolução da Qualidade Documental (Causa Raiz)", "% Preenchido")
            fig2.update_layout(**layout2)
            fig2.update_yaxes(range=[0, 115])
            
            st.plotly_chart(fig2, use_container_width=True, theme=None)

# ─────────────────────────────
# TAB 2 — CONSOLIDADO
# ─────────────────────────────
with tab_cons:
    st.markdown("##### Tabelas Semânticas do Período Filtrado")

    visao = st.radio("Agrupar dados consolidados por:", ["Categoria", "Módulo", "Tipo"], horizontal=True)

    if visao not in df_atual.columns or df_atual[visao].dropna().empty:
        st.warning(f"Sem dados suficientes na coluna '{visao}' para consolidar.")
    else:
        df_grp = df_atual.fillna({visao: "Não Definido"}).groupby(visao).agg(
            Total=("ID", "count"),
            T_Medio=("Tempo Gasto (Horas)", "mean"),
            Estourados=("Status SLA", lambda x: (x == "Acima do Teto (Nota: Tempo Corrido Bruto)").sum()),
            No_Prazo=("Status SLA", lambda x: (x.isin(["Dentro do Prazo Nominal", "Abaixo do Piso (Alta Velocidade)"])).sum()),
            Causa_Preenchida=("Causa_Raiz_Preenchida", "sum")
        ).reset_index()

        df_grp["% No Prazo"]    = np.where(df_grp["Total"] > 0, (df_grp["No_Prazo"]         / df_grp["Total"]) * 100, 0)
        df_grp["% Estourado"]   = np.where(df_grp["Total"] > 0, (df_grp["Estourados"]       / df_grp["Total"]) * 100, 0)
        df_grp["% Causa Raiz"]  = np.where(df_grp["Total"] > 0, (df_grp["Causa_Preenchida"]   / df_grp["Total"]) * 100, 0)

        ordem_colunas = [visao, "Total", "% No Prazo", "T_Medio", "Estourados", "% Estourado", "% Causa Raiz"]
        df_grp = df_grp[ordem_colunas]
        
        # Reseta o index para o zebra striping não se perder na matemática
        df_grp = df_grp.reset_index(drop=True)

        def style_no_prazo(val):
            try:
                if pd.isna(val) or val == '': return ''
                if val >= 80:  return 'background-color: #16a34a; color: white; font-weight: bold;' 
                elif val >= 50: return 'background-color: #f59e0b; color: white; font-weight: bold;' 
                else:           return 'background-color: #dc2626; color: white; font-weight: bold;' 
            except: return ''

        def style_estourado(val):
            try:
                if pd.isna(val) or val == '': return ''
                if val >= 50:   return 'background-color: #dc2626; color: white; font-weight: bold;'
                elif val >= 20: return 'background-color: #f59e0b; color: white; font-weight: bold;'
                else:           return 'background-color: #16a34a; color: white; font-weight: bold;'
            except: return ''

        def style_causa_raiz(val):
            try:
                if pd.isna(val) or val == '': return ''
                if val == 0:   return 'color: #9ca3af; font-style: italic;'
                if val >= 80:  return 'background-color: #16a34a; color: white; font-weight: bold;'
                elif val > 0:  return 'background-color: #2563eb; color: white; font-weight: bold;'
                else:          return 'color: #1f2937;'
            except: return ''

        # 🔥 MUDANÇA: Aplica zebra color primeiro, e os mapas sobrepõem as cores das métricas
        styled_table_grp = (
            df_grp.style
            .apply(zebra_color, axis=1)
            .set_table_styles(header_styles)
            .format({
                "T_Medio":      "{:.1f}h",
                "% No Prazo":   "{:.1f}%",
                "% Estourado":  "{:.1f}%",
                "% Causa Raiz": "{:.1f}%"
            })
            .map(style_no_prazo,   subset=["% No Prazo"])
            .map(style_estourado,  subset=["% Estourado"])
            .map(style_causa_raiz, subset=["% Causa Raiz"])
        )

        st.dataframe(styled_table_grp, use_container_width=True, hide_index=True)

# ─────────────────────────────
# TAB 3 — AUDITORIA
# ─────────────────────────────
with tab_det:
    st.markdown("##### Auditoria Analítica (Linha a Linha)")

    colunas_exibicao = [
        "ID", "Data Abertura", "Módulo", "Categoria",
        "SLA Piso", "SLA Teto", "Tempo Gasto (Horas)", "% Consumo SLA", "Status SLA", "Causa Raíz"
    ]
    df_view = df_atual[[c for c in colunas_exibicao if c in df_atual.columns]].copy()

    if "% Consumo SLA" in df_view.columns:
        df_view["% Consumo SLA"] = df_view["% Consumo SLA"] * 100
        
    df_view = df_view.reset_index(drop=True)

    def style_status(val):
        if val == "Acima do Teto (Nota: Tempo Corrido Bruto)":  return "color: white; background-color: #dc2626; font-weight: bold;"
        elif val == "Abaixo do Piso (Alta Velocidade)":         return "color: white; background-color: #2563eb; font-weight: bold;"
        elif val == "Dentro do Prazo Nominal":                  return "color: white; background-color: #16a34a; font-weight: bold;"
        elif val == "SLA Não Definido":                         return "color: white; background-color: #f59e0b; font-weight: bold;"
        return ""

    # 🔥 MUDANÇA: Mesma inteligência de zebra e cabeçalho claro para a tabela longa
    styled_df = (
        df_view.style
        .apply(zebra_color, axis=1)
        .set_table_styles(header_styles)
        .format({
            "Data Abertura":      "{:%d/%m/%Y}",
            "SLA Piso":           "{:.1f}h",
            "SLA Teto":           "{:.1f}h",
            "Tempo Gasto (Horas)":"{:.1f}h",
            "% Consumo SLA":      "{:.1f}%"
        }, na_rep="-")
        .map(style_status, subset=["Status SLA"])
    )

    st.dataframe(styled_df, use_container_width=True, hide_index=True, height=500)

# ─────────────────────────────
# TAB 4 — DADOS & REGRAS SLA
# ─────────────────────────────
with tab_dados:

    # ── Seção 1: Download do Excel ──────────────────────────────────────────
    st.markdown("##### Fonte de Dados Utilizada")

    excel_path = "relatorio_classificado.xlsx"

    col_dl, col_info = st.columns([1, 2], gap="large")

    with col_dl:
        with st.container(border=True):
            st.markdown(
                """
                <div style="text-align:center; padding: 0.6rem 0 0.4rem;">
                    <div style="font-size:2.8rem; line-height:1;">📥</div>
                    <div style="font-weight:700; color:#013d24; font-size:1rem; margin-top:0.5rem;">
                        relatorio_classificado.xlsx
                    </div>
                    <div style="font-size:0.78rem; color:#6b7280; margin-top:0.25rem;">
                        Base completa sem filtros aplicados
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            st.markdown("<div style='margin-top:0.8rem'></div>", unsafe_allow_html=True)

            if os.path.exists(excel_path):
                with open(excel_path, "rb") as f:
                    excel_bytes = f.read()
                st.download_button(
                    label="⬇️ Baixar  Excel",
                    data=excel_bytes,
                    file_name="relatorio_classificado.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            else:
                st.warning("Arquivo não localizado no servidor.")

    with col_info:
        with st.container(border=True):
            total_registros = len(df)
            data_min_str = df["Data Abertura"].min().strftime("%d/%m/%Y")
            data_max_str = df["Data Abertura"].max().strftime("%d/%m/%Y")
            modulos_disp  = ", ".join(sorted(df["Módulo"].dropna().unique().tolist()))
            colunas_total = len(df.columns)

            st.markdown(
                f"""
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.9rem 1.4rem; padding:0.2rem 0;">
                    <div>
                        <div style="font-size:0.68rem; font-weight:700; color:#7a9e88; text-transform:uppercase; letter-spacing:0.07em;">Total de Registros</div>
                        <div style="font-size:1.4rem; font-weight:700; color:#02683d;">{total_registros:,}</div>
                    </div>
                    <div>
                        <div style="font-size:0.68rem; font-weight:700; color:#7a9e88; text-transform:uppercase; letter-spacing:0.07em;">Colunas</div>
                        <div style="font-size:1.4rem; font-weight:700; color:#02683d;">{colunas_total}</div>
                    </div>
                    <div>
                        <div style="font-size:0.68rem; font-weight:700; color:#7a9e88; text-transform:uppercase; letter-spacing:0.07em;">Período Coberto</div>
                        <div style="font-size:0.9rem; font-weight:600; color:#1f2937;">{data_min_str} → {data_max_str}</div>
                    </div>
                    <div>
                        <div style="font-size:0.68rem; font-weight:700; color:#7a9e88; text-transform:uppercase; letter-spacing:0.07em;">Módulos Presentes</div>
                        <div style="font-size:0.9rem; font-weight:600; color:#1f2937;">{modulos_disp}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Seção 2: Regras SLA ─────────────────────────────────────────────────
    st.markdown("##### Regras de SLA Atualmente Aplicadas")

    st.markdown(
        """
        <div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:12px; padding:0.85rem 1.1rem; margin-bottom:1.4rem; font-size:0.82rem; color:#166534; line-height:1.6;">
            <b>Como funciona:</b> cada ticket é classificado por <b>Módulo</b> e <b>Categoria</b>.
            O sistema localiza a regra correspondente e compara o <b>Tempo Gasto</b> com os limites de
            <span style="color:#1d4ed8; font-weight:600;">Piso (mín.)</span> e
            <span style="color:#b91c1c; font-weight:600;">Teto (máx.)</span> para determinar o <b>Status SLA</b>.
            Regras marcadas como <i>Prazo Não Aplicável</i> são excluídas do cálculo de estouro.
        </div>
        """,
        unsafe_allow_html=True
    )

    # Filtro rápido por módulo dentro da aba
    def _normaliza_modulo_regra(valor):
        return str(valor).strip().lower()

    modulos_regras = sorted(
        {str(r.get("modulo", "")).strip() for r in REGRAS_SLA if str(r.get("modulo", "")).strip()}
    )
    filtro_modulo_regra = st.radio(
        "Filtrar regras por módulo:",
        options=["Todos"] + modulos_regras,
        horizontal=True
    )

    if filtro_modulo_regra == "Todos":
        regras_filtradas = list(REGRAS_SLA)
    else:
        filtro_modulo_norm = _normaliza_modulo_regra(filtro_modulo_regra)
        regras_filtradas = [
            r for r in REGRAS_SLA
            if _normaliza_modulo_regra(r.get("modulo")) in {filtro_modulo_norm, "ambos"}
        ]

    # Renderiza os cards
    for inicio in range(0, len(regras_filtradas), 2):
        cols_cards = st.columns(2)
        for col, regra in zip(cols_cards, regras_filtradas[inicio:inicio + 2]):
            with col:
                modulo_lower = _normaliza_modulo_regra(regra.get("modulo")).replace(" ", "")
                css_class = "ambos" if modulo_lower == "ambos" else ("unidp" if "unidp" in modulo_lower else "unifiscal")

                nota_especial = regra.get("nota_especial", None)
                piso = regra.get("piso_horas")
                teto = regra.get("teto_horas")

                if nota_especial:
                    badge_piso = f'<span class="sla-badge na">NA {nota_especial}</span>'
                else:
                    badge_piso = f'<span class="sla-badge piso">Piso: {piso:.1f}h</span>' if piso is not None else '<span class="sla-badge na">Piso: -</span>'
                    badge_teto = f'<span class="sla-badge teto">Teto: {teto:.1f}h</span>' if teto is not None else '<span class="sla-badge na">Teto: -</span>'

                cats = " | ".join(regra.get("categoria", [])) if regra.get("categoria") else "-"
                subs = " | ".join(regra.get("subcategoria", [])) if regra.get("subcategoria") else "<span style='color:#9ca3af;font-style:italic;'>qualquer subcategoria</span>"

                nota_html = f'<div class="sla-nota">Observacao: {nota_especial}</div>' if nota_especial else ""
                badges_html = badge_piso if nota_especial else f"{badge_piso} {badge_teto}"

                st.markdown(
                    f"""
                    <div class="sla-card">
                        <div class="sla-card-modulo {css_class}">{regra.get('modulo', 'N/A')}</div>
                        <div class="sla-card-title">{regra.get('nome_exibicao', 'Regra sem nome')}</div>
                        <div style="font-size:0.75rem; color:#6b7280; margin-bottom:0.55rem;">
                            <b style="color:#374151;">Categoria:</b> {cats}<br>
                            <b style="color:#374151;">Subcategoria:</b> {subs}
                        </div>
                        <div>{badges_html}</div>
                        {nota_html}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Seção 3: Metas SLA Mensais ──────────────────────────────────────────
    st.markdown("##### Tolerâncias Máximas de Estouro por Mês")

    meses_nomes = {
        1:"Janeiro", 2:"Fevereiro", 3:"Março", 4:"Abril",
        5:"Maio", 6:"Junho", 7:"Julho", 8:"Agosto",
        9:"Setembro", 10:"Outubro", 11:"Novembro", 12:"Dezembro"
    }

    cols_metas = st.columns(len(METAS_SLA_MENSAL) + 1)

    cols_metas[0].markdown(
        f"""
        <div style="background:#fefce8; border:1px solid #fde68a; border-radius:12px; padding:0.9rem 1rem; text-align:center;">
            <div style="font-size:0.68rem; font-weight:700; color:#92400e; text-transform:uppercase; letter-spacing:0.07em;">Baseline (antes de Abril)</div>
            <div style="font-size:1.6rem; font-weight:800; color:#b45309; margin-top:0.3rem;">{BASELINE_HISTORICO*100:.0f}%</div>
            <div style="font-size:0.72rem; color:#92400e; margin-top:0.15rem;">Referência histórica</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    for i, (mes_num, meta) in enumerate(sorted(METAS_SLA_MENSAL.items())):
        cor_bg   = "#f0fdf4" if meta <= 0.20 else "#eff6ff" if meta <= 0.30 else "#fef2f2"
        cor_bdr  = "#bbf7d0" if meta <= 0.20 else "#bfdbfe" if meta <= 0.30 else "#fecaca"
        cor_txt  = "#166534" if meta <= 0.20 else "#1e40af" if meta <= 0.30 else "#991b1b"
        cols_metas[i+1].markdown(
            f"""
            <div style="background:{cor_bg}; border:1px solid {cor_bdr}; border-radius:12px; padding:0.9rem 1rem; text-align:center;">
                <div style="font-size:0.68rem; font-weight:700; color:{cor_txt}; text-transform:uppercase; letter-spacing:0.07em;">{meses_nomes.get(mes_num, mes_num)}</div>
                <div style="font-size:1.6rem; font-weight:800; color:{cor_txt}; margin-top:0.3rem;">{'<'} {meta*100:.0f}%</div>
                <div style="font-size:0.72rem; color:{cor_txt}; margin-top:0.15rem;">máx. tolerado</div>
            </div>
            """,
            unsafe_allow_html=True
        )
