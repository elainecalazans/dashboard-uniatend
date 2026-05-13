from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from config import BRAND_COLORS, BASELINE_HISTORICO, METAS_SLA_MENSAL, SLA_STATUS_INTERNO


def plotly_base_layout(title_text: str, y_title: str) -> dict:
    return dict(
        paper_bgcolor="#ffffff",
        plot_bgcolor="#fafcfb",
        font=dict(family="Inter, sans-serif", color="#3a4f40", size=12),
        title=dict(
            text=title_text,
            font=dict(size=15, color="#02683d", family="Inter, sans-serif", weight="bold"),
            x=0, xanchor="left", pad=dict(l=4),
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
            tickangle=-30,
        ),
        legend=dict(
            orientation="h",
            yanchor="top", y=-0.15,
            xanchor="center", x=0.5,
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#dce8e1",
            borderwidth=1,
            font=dict(size=11, color="#3a4f40"),
        ),
        margin=dict(t=70, l=56, r=24, b=80),
        height=480,
    )


def create_sla_trend_chart(df_sla_validos: pd.DataFrame) -> go.Figure | None:
    if df_sla_validos.empty:
        return None

    df_trend = (
        df_sla_validos
        .groupby(["Mês/Ano", "Mês_Nome", "Mes_Int"])["Status SLA"]
        .agg(lambda s: (s == SLA_STATUS_INTERNO).mean() * 100)
        .reset_index(name="% Estouro")
        .sort_values("Mês/Ano")
    )
    df_trend["Tolerancia"] = df_trend["Mes_Int"].map(METAS_SLA_MENSAL) * 100

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_trend["Mês_Nome"],
        y=df_trend["% Estouro"],
        name="% Realizado",
        marker=dict(color="#02683d", line=dict(width=0), opacity=0.9),
        text=df_trend["% Estouro"].apply(lambda v: f"{v:.1f}%"),
        textposition="auto",
        textfont=dict(color="white", size=12, family="Inter"),
    ))

    if df_trend["Tolerancia"].notna().any():
        fig.add_trace(go.Scatter(
            x=df_trend["Mês_Nome"],
            y=df_trend["Tolerancia"],
            mode="lines+markers+text",
            name="% Máximo Tolerado (Meta)",
            line=dict(color="#e05c2a", dash="solid", width=2.5),
            marker=dict(size=10, color="#e05c2a", line=dict(width=2, color="#ffffff")),
            text=df_trend["Tolerancia"].apply(lambda v: f"Máx: {v:.0f}%" if pd.notna(v) else ""),
            textposition="top center",
            textfont=dict(color="#e05c2a", size=12, family="Inter"),
            connectgaps=False,
        ))

    fig.add_hline(
        y=BASELINE_HISTORICO * 100,
        line_dash="dot",
        line_color="#c49a00",
        line_width=2,
        annotation_text=f"Baseline Gerencial ({BASELINE_HISTORICO*100:.0f}%)",
        annotation_position="top left",
        annotation_font_color="#c49a00",
        annotation_font_size=11,
    )

    fig.update_layout(**plotly_base_layout("Desempenho de SLA vs Tolerância Redutiva", "% Fora do Prazo"))
    fig.update_yaxes(range=[0, max(100, df_trend["% Estouro"].max() + 20)])
    return fig


def create_causa_raiz_chart(df_tendencia: pd.DataFrame) -> go.Figure:
    df_cr = (
        df_tendencia
        .groupby(["Mês_Nome", "Mês/Ano", "Módulo"])
        .agg(Vol=("ID", "count"), Preench=("Causa_Raiz_Preenchida", "sum"))
        .reset_index()
    )
    df_cr["% Causa Raiz"] = (df_cr["Preench"] / df_cr["Vol"]) * 100
    df_cr = df_cr.sort_values("Mês/Ano")

    fig = px.line(
        df_cr,
        x="Mês_Nome", y="% Causa Raiz",
        color="Módulo",
        markers=True, text="% Causa Raiz",
        color_discrete_sequence=BRAND_COLORS,
    )
    fig.update_traces(
        texttemplate="%{text:.1f}%",
        textposition="top center",
        textfont=dict(size=11, family="Inter"),
        line=dict(width=2.2),
        marker=dict(size=9, line=dict(width=2, color="#ffffff")),
    )
    fig.update_layout(**plotly_base_layout("Evolução da Qualidade Documental (Causa Raiz)", "% Preenchido"))
    fig.update_yaxes(range=[0, 115])
    return fig
