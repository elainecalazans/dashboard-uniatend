from __future__ import annotations

import streamlit as st
import pandas as pd

from config import (
    BASELINE_HISTORICO, METAS_SLA_MENSAL, MESES_NOMES,
    SLA_STATUS_INTERNO, SLA_STATUS_EXCLUIDOS,
)


def calcular_kpis(
    dados: pd.DataFrame,
    status_concluido: list[str],
) -> tuple[int, float, float]:
    if dados.empty:
        return 0, 0.0, 0.0

    vol = len(dados)
    concluidos = dados[dados["Status"].isin(status_concluido)]
    com_sla = concluidos[~concluidos["Status SLA"].isin(SLA_STATUS_EXCLUIDOS)]
    pct_estouro = (
        (com_sla["Status SLA"] == SLA_STATUS_INTERNO).sum() / len(com_sla)
        if len(com_sla) > 0 else 0.0
    )
    tx_causa = (
        dados["Causa_Raiz_Preenchida"].mean()
        if "Causa_Raiz_Preenchida" in dados.columns else 0.0
    )
    return vol, pct_estouro, tx_causa


def render_kpis(
    df_atual: pd.DataFrame,
    df_prev: pd.DataFrame,
    status_concluido: list[str],
    mes_fim: int,
    texto_comparativo: str,
) -> None:
    vol_at, pct_at, causa_at = calcular_kpis(df_atual, status_concluido)
    vol_pr, pct_pr, causa_pr = calcular_kpis(df_prev, status_concluido)
    meta_num = METAS_SLA_MENSAL.get(mes_fim)

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Volume de Tickets",
        str(vol_at),
        delta=f"{vol_at - vol_pr} {texto_comparativo}",
        delta_color="inverse",
        help="Total de tickets abertos no período filtrado.",
    )

    delta_esp = (pct_at - pct_pr) * 100
    col2.metric(
        "% Fora do Prazo (Concluídos)",
        f"{pct_at*100:.1f}%",
        delta=f"{delta_esp:.1f}% {texto_comparativo}",
        delta_color="inverse",
        help="Proporção de tickets concluídos cujo tempo de resolução ultrapassou o teto de SLA.",
    )

    if meta_num is not None:
        folga = meta_num - pct_at
        col3.metric(
            f"Tolerância Máxima — Mês {mes_fim}",
            f"< {meta_num*100:.0f}%",
            delta=f"{folga*100:.1f}% de margem" if folga >= 0 else f"{abs(folga)*100:.1f}% acima da meta",
            delta_color="normal" if folga >= 0 else "inverse",
            help="Meta gerencial: volume máximo permitido de tickets fora do SLA no mês.",
        )
    else:
        col3.metric(
            f"Tolerância Máxima — Mês {mes_fim}",
            f"< {BASELINE_HISTORICO*100:.0f}% (baseline)",
            help="Mês fora do plano de metas. Referência: baseline histórico de 48%.",
        )

    delta_causa = (causa_at - causa_pr) * 100
    col4.metric(
        "% Causa Raiz Documentada",
        f"{causa_at*100:.1f}%",
        delta=f"{delta_causa:.1f}% {texto_comparativo}",
        delta_color="off" if causa_at == 0 else "normal",
        help="Proporção de tickets com campo 'Causa Raíz' preenchido.",
    )

    if causa_at == 0:
        st.markdown("""
        <style>
        div[data-testid="stHorizontalBlock"] > div:nth-child(4) [data-testid="stMetricDelta"] > div,
        div[data-testid="stHorizontalBlock"] > div:nth-child(4) [data-testid="stMetricDelta"] svg {
            color: #4b5563 !important;
            fill: #4b5563 !important;
        }
        </style>
        """, unsafe_allow_html=True)


def render_sla_rules(regras_sla: list[dict]) -> None:
    def _norm(v) -> str:
        return str(v).strip().lower()

    modulos = sorted({str(r.get("modulo", "")).strip() for r in regras_sla if str(r.get("modulo", "")).strip()})
    filtro = st.radio(
        "Filtrar regras por módulo:",
        options=["Todos"] + modulos,
        horizontal=True,
        key="filtro_regra_modulo",
    )

    regras = (
        list(regras_sla) if filtro == "Todos"
        else [r for r in regras_sla if _norm(r.get("modulo")) in {_norm(filtro), "ambos"}]
    )

    for i in range(0, len(regras), 2):
        cols = st.columns(2)
        for col, regra in zip(cols, regras[i:i + 2]):
            with col:
                mod_lower = _norm(regra.get("modulo", "")).replace(" ", "")
                css_cls = "ambos" if mod_lower == "ambos" else ("unidp" if "unidp" in mod_lower else "unifiscal")
                nota = regra.get("nota_especial")
                piso = regra.get("piso_horas")
                teto = regra.get("teto_horas")

                if nota:
                    badges = f'<span class="sla-badge na">NA — {nota}</span>'
                else:
                    b_p = f'<span class="sla-badge piso">Piso: {piso:.1f}h</span>' if piso is not None else '<span class="sla-badge na">Piso: —</span>'
                    b_t = f'<span class="sla-badge teto">Teto: {teto:.1f}h</span>' if teto is not None else '<span class="sla-badge na">Teto: —</span>'
                    badges = f"{b_p} {b_t}"

                cats = " | ".join(regra.get("categoria", [])) or "—"
                subs = (
                    " | ".join(regra.get("subcategoria", []))
                    if regra.get("subcategoria")
                    else "<span style='color:#9ca3af;font-style:italic;'>qualquer</span>"
                )
                nota_html = f'<div class="sla-nota">Obs: {nota}</div>' if nota else ""

                st.markdown(f"""
                <div class="sla-card">
                    <div class="sla-card-modulo {css_cls}">{regra.get("modulo", "N/A")}</div>
                    <div class="sla-card-title">{regra.get("nome_exibicao", "—")}</div>
                    <div style="font-size:0.75rem;color:#6b7280;margin-bottom:0.55rem;">
                        <b style="color:#374151;">Categoria:</b> {cats}<br>
                        <b style="color:#374151;">Subcategoria:</b> {subs}
                    </div>
                    <div>{badges}</div>
                    {nota_html}
                </div>
                """, unsafe_allow_html=True)


def render_meta_cards() -> None:
    cols = st.columns(len(METAS_SLA_MENSAL) + 1)

    cols[0].markdown(f"""
    <div style="background:#fefce8;border:1px solid #fde68a;border-radius:12px;padding:0.9rem 1rem;text-align:center;">
        <div style="font-size:0.68rem;font-weight:700;color:#92400e;text-transform:uppercase;letter-spacing:0.07em;">Baseline (antes de Abril)</div>
        <div style="font-size:1.6rem;font-weight:800;color:#b45309;margin-top:0.3rem;">{BASELINE_HISTORICO*100:.0f}%</div>
        <div style="font-size:0.72rem;color:#92400e;margin-top:0.15rem;">Referência histórica</div>
    </div>
    """, unsafe_allow_html=True)

    for i, (mes_num, meta) in enumerate(sorted(METAS_SLA_MENSAL.items())):
        bg  = "#f0fdf4" if meta <= 0.20 else "#eff6ff" if meta <= 0.30 else "#fef2f2"
        bdr = "#bbf7d0" if meta <= 0.20 else "#bfdbfe" if meta <= 0.30 else "#fecaca"
        txt = "#166534" if meta <= 0.20 else "#1e40af" if meta <= 0.30 else "#991b1b"
        cols[i + 1].markdown(f"""
        <div style="background:{bg};border:1px solid {bdr};border-radius:12px;padding:0.9rem 1rem;text-align:center;">
            <div style="font-size:0.68rem;font-weight:700;color:{txt};text-transform:uppercase;letter-spacing:0.07em;">{MESES_NOMES.get(mes_num, mes_num)}</div>
            <div style="font-size:1.6rem;font-weight:800;color:{txt};margin-top:0.3rem;">{'<'} {meta*100:.0f}%</div>
            <div style="font-size:0.72rem;color:{txt};margin-top:0.15rem;">máx. tolerado</div>
        </div>
        """, unsafe_allow_html=True)
