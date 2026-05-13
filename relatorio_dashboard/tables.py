from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.io.formats.style import Styler

from config import SLA_STATUS_INTERNO

HEADER_STYLES = [
    {"selector": "th", "props": [
        ("background-color", "#e2e8f0 !important"),
        ("color", "#1f2937 !important"),
        ("font-weight", "700 !important"),
        ("border-bottom", "2px solid #cbd5e1 !important"),
    ]},
    {"selector": "td", "props": [
        ("border-bottom", "1px solid #f1f5f9 !important"),
    ]},
]


def _zebra(row: pd.Series) -> list[str]:
    bg = "#f8fafc" if row.name % 2 == 0 else "#ffffff"
    return [f"background-color: {bg}; color: #1f2937"] * len(row)


def _style_no_prazo(val) -> str:
    try:
        if pd.isna(val) or val == "":
            return ""
        if val >= 80:
            return "background-color: #16a34a; color: white; font-weight: bold;"
        if val >= 50:
            return "background-color: #f59e0b; color: white; font-weight: bold;"
        return "background-color: #dc2626; color: white; font-weight: bold;"
    except Exception:
        return ""


def _style_fora_prazo(val) -> str:
    try:
        if pd.isna(val) or val == "":
            return ""
        if val >= 50:
            return "background-color: #dc2626; color: white; font-weight: bold;"
        if val >= 20:
            return "background-color: #f59e0b; color: white; font-weight: bold;"
        return "background-color: #16a34a; color: white; font-weight: bold;"
    except Exception:
        return ""


def _style_causa_raiz(val) -> str:
    try:
        if pd.isna(val) or val == "":
            return ""
        if val == 0:
            return "color: #9ca3af; font-style: italic;"
        if val >= 80:
            return "background-color: #16a34a; color: white; font-weight: bold;"
        if val > 0:
            return "background-color: #2563eb; color: white; font-weight: bold;"
        return "color: #1f2937;"
    except Exception:
        return ""


def _style_status_label(val) -> str:
    mapping = {
        "Fora do Prazo":    "color: white; background-color: #dc2626; font-weight: bold;",
        "Alta Velocidade":  "color: white; background-color: #2563eb; font-weight: bold;",
        "Dentro do Prazo":  "color: white; background-color: #16a34a; font-weight: bold;",
        "Sem Regra Definida": "color: white; background-color: #f59e0b; font-weight: bold;",
    }
    return mapping.get(str(val), "")


def build_consolidated_table(df_atual: pd.DataFrame, visao: str) -> Styler:
    df_grp = (
        df_atual.fillna({visao: "Não Definido"})
        .groupby(visao)
        .agg(
            Total=("ID", "count"),
            Tempo_Medio=("Tempo Gasto (Horas)", "mean"),
            Estourados=("Status SLA", lambda x: (x == SLA_STATUS_INTERNO).sum()),
            No_Prazo=("Status SLA", lambda x: x.isin(["Dentro do Prazo Nominal", "Abaixo do Piso (Alta Velocidade)"]).sum()),
            Causa_Preenchida=("Causa_Raiz_Preenchida", "sum"),
        )
        .reset_index()
    )

    denom = df_grp["Total"].replace(0, np.nan)
    df_grp["% No Prazo"]       = (df_grp["No_Prazo"]         / denom * 100).fillna(0)
    df_grp["% Fora do Prazo"]  = (df_grp["Estourados"]       / denom * 100).fillna(0)
    df_grp["% Causa Raiz"]     = (df_grp["Causa_Preenchida"] / denom * 100).fillna(0)

    df_grp = df_grp.rename(columns={
        "Tempo_Medio": "Tempo Médio (h)",
        "Estourados":  "Fora do Prazo (nº)",
    })
    df_grp = df_grp[[visao, "Total", "% No Prazo", "Tempo Médio (h)", "Fora do Prazo (nº)", "% Fora do Prazo", "% Causa Raiz"]]
    df_grp = df_grp.reset_index(drop=True)

    return (
        df_grp.style
        .apply(_zebra, axis=1)
        .set_table_styles(HEADER_STYLES)
        .format({
            "Tempo Médio (h)":  "{:.1f}h",
            "% No Prazo":       "{:.1f}%",
            "% Fora do Prazo":  "{:.1f}%",
            "% Causa Raiz":     "{:.1f}%",
        })
        .map(_style_no_prazo,   subset=["% No Prazo"])
        .map(_style_fora_prazo, subset=["% Fora do Prazo"])
        .map(_style_causa_raiz, subset=["% Causa Raiz"])
    )


def build_audit_table(df_atual: pd.DataFrame, id_busca: str, filtro_status: str) -> Styler:
    cols = [
        "ID", "Data Abertura", "Módulo", "Categoria",
        "SLA Piso", "SLA Teto", "Tempo Gasto (Horas)", "% Consumo SLA",
        "Status_SLA_Label", "Causa Raíz",
    ]
    df_view = df_atual[[c for c in cols if c in df_atual.columns]].copy()

    if "% Consumo SLA" in df_view.columns:
        df_view["% Consumo SLA"] = df_view["% Consumo SLA"] * 100

    if id_busca:
        df_view = df_view[df_view["ID"].astype(str).str.contains(id_busca, case=False, na=False)]

    if filtro_status and filtro_status != "Todos" and "Status_SLA_Label" in df_view.columns:
        df_view = df_view[df_view["Status_SLA_Label"] == filtro_status]

    df_view = df_view.reset_index(drop=True)

    fmt = {
        "Data Abertura":        "{:%d/%m/%Y}",
        "SLA Piso":             "{:.1f}h",
        "SLA Teto":             "{:.1f}h",
        "Tempo Gasto (Horas)":  "{:.1f}h",
        "% Consumo SLA":        "{:.1f}%",
    }

    styler = (
        df_view.style
        .apply(_zebra, axis=1)
        .set_table_styles(HEADER_STYLES)
        .format(fmt, na_rep="—")
    )

    if "Status_SLA_Label" in df_view.columns:
        styler = styler.map(_style_status_label, subset=["Status_SLA_Label"])

    return styler
