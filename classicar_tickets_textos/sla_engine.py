from __future__ import annotations

import re
import unicodedata
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_SLA_RULES_PATH = Path(__file__).parent.parent / "sla_rules.json"
_REGRAS_SLA: list[dict] | None = None


def _get_regras() -> list[dict]:
    global _REGRAS_SLA
    if _REGRAS_SLA is None:
        with open(_SLA_RULES_PATH, encoding="utf-8") as f:
            _REGRAS_SLA = json.load(f)
    return _REGRAS_SLA


def _norm(texto) -> str:
    if pd.isna(texto):
        return ""
    t = str(texto).strip().lower()
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("utf-8")


def converter_tempo_para_horas(tempo_str) -> float:
    if pd.isna(tempo_str) or not isinstance(tempo_str, str) or not tempo_str.strip():
        return 0.0
    s = tempo_str.lower()
    m_dias = re.search(r"(\d+)\s*dia", s)
    m_horas = re.search(r"(\d+)\s*hora", s)
    m_min = re.search(r"(\d+)\s*minuto", s)
    dias = int(m_dias.group(1)) * 24 if m_dias else 0
    horas = float(m_horas.group(1)) if m_horas else 0.0
    minutos = float(m_min.group(1)) / 60 if m_min else 0.0
    return round(dias + horas + minutos, 2)


def avaliar_sla(modulo, categoria, subcategoria, tempo_horas: float) -> pd.Series:
    regras = _get_regras()
    mod_n = _norm(modulo)
    cat_n = _norm(categoria)
    sub_n = _norm(subcategoria)

    piso_h = np.nan
    teto_h = np.nan
    tem_regra = False
    prazo_na = False

    for regra in regras:
        if _norm(regra["modulo"]) not in {mod_n, "ambos"}:
            continue
        if not any(_norm(c) == cat_n for c in regra.get("categoria", [])):
            continue
        subs = regra.get("subcategoria", [])
        if subs and not any(_norm(s) == sub_n for s in subs):
            continue
        tem_regra = True
        if regra.get("piso_horas") is None:
            prazo_na = True
        else:
            piso_h = regra["piso_horas"]
            teto_h = regra["teto_horas"]
        break

    if tempo_horas == 0.0:
        status = "Sem Registro de Tempo"
    elif prazo_na:
        status = "Prazo Não Aplicável"
    elif not tem_regra:
        status = "SLA Não Definido"
    elif tempo_horas > teto_h:
        status = "Acima do Teto (Nota: Tempo Corrido Bruto)"
    elif tempo_horas <= piso_h:
        status = "Abaixo do Piso (Alta Velocidade)"
    else:
        status = "Dentro do Prazo Nominal"

    consumo = (
        round(tempo_horas / teto_h, 4)
        if (not pd.isna(teto_h) and teto_h > 0 and tempo_horas > 0)
        else np.nan
    )
    return pd.Series([status, piso_h, teto_h, consumo, tem_regra])
