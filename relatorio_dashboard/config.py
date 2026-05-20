from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
ROOT_DIR = BASE_DIR.parent

EXCEL_PATH = BASE_DIR / "relatorio_classificado.xlsx"
AUDIT_PATH = BASE_DIR / "relatorio_auditoria.xlsx"
LOGO_PATH = BASE_DIR / "1775153144791_image.png"
SLA_RULES_PATH = ROOT_DIR / "sla_rules.json"
CONFIG_PATH = ROOT_DIR / "config.json"
CSS_PATH = BASE_DIR / "style.css"


def _carregar_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["metas_sla_mensal"] = {int(k): v for k, v in cfg["metas_sla_mensal"].items()}
    return cfg


_cfg = _carregar_config()

BASELINE_HISTORICO: float = _cfg["baseline_historico"]
METAS_SLA_MENSAL: dict[int, float] = _cfg["metas_sla_mensal"]
BRAND_COLORS: list[str] = _cfg["brand_colors"]

MESES_NOMES: dict[int, str] = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março",    4: "Abril",
    5: "Maio",    6: "Junho",     7: "Julho",     8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}

SLA_STATUS_INTERNO = "Acima do Teto (Nota: Tempo Corrido Bruto)"

SLA_STATUS_EXCLUIDOS: set[str] = {
    "SLA Não Definido",
    "Sem Registro de Tempo",
    "Prazo Não Aplicável",
}

SLA_STATUS_LABELS: dict[str, str] = {
    SLA_STATUS_INTERNO:                  "Fora do Prazo",
    "Abaixo do Piso (Alta Velocidade)":  "Alta Velocidade",
    "Dentro do Prazo Nominal":           "Dentro do Prazo",
    "SLA Não Definido":                  "Sem Regra Definida",
    "Sem Registro de Tempo":             "Sem Registro",
    "Prazo Não Aplicável":               "Não Aplicável",
}
