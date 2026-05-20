from __future__ import annotations

import base64
import json
import logging

import numpy as np
import pandas as pd
import streamlit as st

from config import AUDIT_PATH, EXCEL_PATH, LOGO_PATH, SLA_RULES_PATH, CSS_PATH, SLA_STATUS_LABELS

logger = logging.getLogger(__name__)


@st.cache_resource
def load_sla_rules() -> list[dict]:
    try:
        with open(SLA_RULES_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        st.error(f"Arquivo de regras SLA não encontrado: {SLA_RULES_PATH}")
        return []
    except json.JSONDecodeError as exc:
        st.error(f"Erro de sintaxe no sla_rules.json: {exc}")
        return []


@st.cache_resource
def get_logo_base64() -> str | None:
    if LOGO_PATH.exists():
        return base64.b64encode(LOGO_PATH.read_bytes()).decode()
    return None


@st.cache_resource
def load_css() -> str:
    if CSS_PATH.exists():
        return CSS_PATH.read_text(encoding="utf-8")
    return ""


@st.cache_data
def load_data(file_mtime: float) -> pd.DataFrame:
    try:
        df = pd.read_excel(EXCEL_PATH)

        if "Data Abertura" in df.columns:
            df["Data Abertura"] = pd.to_datetime(df["Data Abertura"], dayfirst=True, errors="coerce")

        for col in ["SLA Piso", "SLA Teto", "% Consumo SLA", "Tempo Gasto (Horas)", "Prioridade"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if "Causa Raíz" in df.columns:
            df["Causa_Raiz_Preenchida"] = df["Causa Raíz"].replace(r"^\s*$", np.nan, regex=True).notna()
        else:
            df["Causa_Raiz_Preenchida"] = False

        df["Mês/Ano"]  = df["Data Abertura"].dt.to_period("M").dt.to_timestamp()
        df["Mês_Nome"] = df["Data Abertura"].dt.strftime("%b/%Y")
        df["Mes_Int"]  = df["Data Abertura"].dt.month

        if "Status SLA" in df.columns:
            df["Status_SLA_Label"] = df["Status SLA"].map(SLA_STATUS_LABELS).fillna(df["Status SLA"])

        return df.dropna(subset=["Data Abertura"])

    except Exception as exc:
        st.error(f"Erro ao carregar relatorio_classificado.xlsx: {exc}")
        logger.exception("Falha no carregamento do Excel.")
        return pd.DataFrame()


def get_excel_mtime() -> float:
    return EXCEL_PATH.stat().st_mtime if EXCEL_PATH.exists() else 0.0


@st.cache_data
def load_audit_data(file_mtime: float) -> pd.DataFrame:
    if not AUDIT_PATH.exists():
        return pd.DataFrame()
    try:
        df = pd.read_excel(AUDIT_PATH)
        if "Data Abertura" in df.columns:
            df["Data Abertura"] = pd.to_datetime(df["Data Abertura"], dayfirst=True, errors="coerce")
        return df
    except Exception as exc:
        logger.warning("Erro ao carregar relatorio_auditoria.xlsx: %s", exc)
        return pd.DataFrame()


def get_audit_mtime() -> float:
    return AUDIT_PATH.stat().st_mtime if AUDIT_PATH.exists() else 0.0
