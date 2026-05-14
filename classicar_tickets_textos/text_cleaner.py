from __future__ import annotations

import html
import re

import pandas as pd

TECNICOS: set[str] = {
    "GUILHERME LOPES PIRES DA SILVA",
    "GUILHERME HENRIQUE PORTO DOS SANTOS",
    "JEISY GONCALVES DE SOUSA",
    "RAFAEL RODRIGUES VIANNA",
    "ANDRESSA TELES RODRIGUES",
}

_RUIDO_RE = re.compile(
    r"^("
    r"alteraç[aã]o de status por\b|"
    r"ticket atribu[íi]do a\b|"
    r"solicitante alterado para\b|"
    r"(ticket )?(criado|cancelado) via teste automatizado"
    r")",
    re.IGNORECASE,
)

_ANEXO_RE = re.compile(
    r"x\{[0-9A-Fa-f\-]{36}\}\.\w+|\bx\w+\.(pdf|png|jpg|jpeg|xlsx?|docx?)\b",
    re.IGNORECASE,
)


def _fix_mojibake(texto: str) -> str:
    try:
        return texto.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return texto


def _limpar(texto: str) -> str:
    s = html.unescape(str(texto)).strip()
    if not s or s.lower() == "nan":
        return ""
    s = _fix_mojibake(s)
    s = _ANEXO_RE.sub("", s).strip()
    return s


def _eh_ruido(texto: str) -> bool:
    return not texto or bool(_RUIDO_RE.match(texto))


def consolidar_historico(df: pd.DataFrame) -> pd.DataFrame:
    """
    Recebe o DataFrame bruto de textos.csv e retorna um DataFrame com
    uma linha por ticket: id_ticket, historico, texto_cliente, texto_tecnico.
    """
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower()
    df["id_ticket"] = df["id_ticket"].astype(str).str.strip()
    df["usuario"] = df["usuario"].astype(str).str.strip().str.upper()
    df["criado_em"] = pd.to_datetime(
        df["criado_em"], format="%d/%m/%Y %H:%M:%S", errors="coerce"
    )
    df = df.sort_values(["id_ticket", "criado_em"], na_position="last")

    registros = []
    for ticket_id, grupo in df.groupby("id_ticket", sort=False):
        historico: list[dict] = []
        for _, row in grupo.iterrows():
            texto_limpo = _limpar(row.get("texto", ""))
            if _eh_ruido(texto_limpo):
                continue
            papel = "tecnico" if row["usuario"] in TECNICOS else "cliente"
            historico.append({
                "timestamp": row["criado_em"],
                "papel": papel,
                "usuario": row["usuario"],
                "texto": texto_limpo,
            })

        msgs_cliente = [h for h in historico if h["papel"] == "cliente"]
        msgs_tecnico = [h for h in historico if h["papel"] == "tecnico"]

        registros.append({
            "id_ticket": ticket_id,
            "historico": historico,
            "texto_cliente": msgs_cliente[0]["texto"] if msgs_cliente else "",
            "texto_tecnico": " | ".join(h["texto"] for h in msgs_tecnico),
        })

    return pd.DataFrame(
        registros,
        columns=["id_ticket", "historico", "texto_cliente", "texto_tecnico"],
    )


def preparar_para_classificacao(df: pd.DataFrame) -> pd.DataFrame:
    """
    Retorna [id_ticket, texto] para o classificador.
    Usa a primeira mensagem limpa do cliente; fallback para a primeira mensagem do histórico.
    """
    df_hist = consolidar_historico(df)

    def _texto(row: pd.Series) -> str:
        if row["texto_cliente"]:
            return row["texto_cliente"]
        if row["historico"]:
            return row["historico"][0]["texto"]
        return ""

    df_hist["texto"] = df_hist.apply(_texto, axis=1)
    return df_hist[["id_ticket", "texto"]]
