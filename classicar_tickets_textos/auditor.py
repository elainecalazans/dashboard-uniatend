from __future__ import annotations

import re

import pandas as pd

from text_cleaner import consolidar_historico

_GENERICA_RE = re.compile(
    r"^("
    r"tratativa finalizada[.!]?|"
    r"erro solucionado[.!]?|"
    r"realizado conforme solicitado[.!]?|"
    r"ok[.!]?|"
    r"resolvido[.!]?|"
    r"conclu[íi]do[.!]?|"
    r"pronto[.!]?"
    r")$",
    re.IGNORECASE,
)

_COBRANCA_RE = re.compile(
    r"cobran[çc]a|encerramento administrativo|falta de retorno",
    re.IGNORECASE,
)

_SAUDACAO_RE = re.compile(
    r"^(boa tarde|bom dia|ol[aá]|oi)[,.]?\s*",
    re.IGNORECASE,
)

_FECHAMENTO_RE = re.compile(
    r"em caso de d[uú]vidas.{0,40}disposi[çc][aã]o\.?",
    re.IGNORECASE,
)


def _label_sem_frt(historico: list[dict]) -> str:
    msgs_cliente = [h for h in historico if h["papel"] == "cliente"]
    msgs_tecnico = [h for h in historico if h["papel"] == "tecnico"]
    if not historico:
        return "Sem dados"
    if msgs_tecnico and not msgs_cliente:
        return "Abertura Administrativa"
    if not msgs_tecnico and len(historico) > 1:
        usuarios = {h["usuario"] for h in historico}
        if len(usuarios) == 1:
            return "Abertura Administrativa"
    return "Sem dados"


def _calcular_frt(historico: list[dict]) -> float | None:
    msgs_cliente = [h for h in historico if h["papel"] == "cliente" and pd.notna(h["timestamp"])]
    msgs_tecnico = [h for h in historico if h["papel"] == "tecnico" and pd.notna(h["timestamp"])]
    if not msgs_cliente or not msgs_tecnico:
        return None
    t_abertura = msgs_cliente[0]["timestamp"]
    respostas = [h for h in msgs_tecnico if h["timestamp"] > t_abertura]
    if not respostas:
        return None
    return (respostas[0]["timestamp"] - t_abertura).total_seconds() / 3600


def _calcular_max_gap(historico: list[dict]) -> float | None:
    ts = sorted(h["timestamp"] for h in historico if pd.notna(h["timestamp"]))
    if len(ts) < 2:
        return None
    gaps = [(ts[i + 1] - ts[i]).total_seconds() / 86400 for i in range(len(ts) - 1)]
    return max(gaps)


def _resolucao_generica(msgs_tecnico: list[dict]) -> bool:
    if not msgs_tecnico:
        return False
    ultima = msgs_tecnico[-1]["texto"].strip()
    sem_saudacao = _SAUDACAO_RE.sub("", ultima).strip()
    sem_fechamento = _FECHAMENTO_RE.sub("", sem_saudacao).strip()
    return not sem_fechamento or bool(_GENERICA_RE.match(sem_fechamento))


def _protocolo_encerramento(historico: list[dict]) -> bool:
    return any(
        h["papel"] == "tecnico" and bool(_COBRANCA_RE.search(h["texto"]))
        for h in historico
    )


def auditar(df_tickets: pd.DataFrame, df_textos_raw: pd.DataFrame) -> pd.DataFrame:
    df_hist = consolidar_historico(df_textos_raw)
    hist_idx = df_hist.set_index("id_ticket")["historico"].to_dict()

    registros = []
    for _, ticket in df_tickets.iterrows():
        ticket_id = str(ticket["ID"])
        historico = hist_idx.get(ticket_id, [])
        msgs_tecnico = [h for h in historico if h["papel"] == "tecnico"]

        frt = _calcular_frt(historico)
        max_gap = _calcular_max_gap(historico)
        causa_raiz = str(ticket.get("Causa Raíz", "")).strip()

        registros.append({
            "ID": ticket_id,
            "Responsável": ticket.get("Responsável", ""),
            "Módulo": ticket.get("Módulo", ""),
            "Categoria": ticket.get("Categoria", ""),
            "Status": ticket.get("Status", ""),
            "FRT (horas)": round(frt, 1) if frt is not None else None,
            "FRT OK": "Sim" if (frt is not None and frt <= 2.0) else ("Não" if frt is not None else _label_sem_frt(historico)),
            "Gap Máx (dias)": round(max_gap, 1) if max_gap is not None else None,
            "Risco Zumbi": "Sim" if (max_gap is not None and max_gap > 5) else "Não",
            "Resolução Genérica": "Sim" if _resolucao_generica(msgs_tecnico) else "Não",
            "Causa Raíz Preenchida": "Sim" if (causa_raiz not in ("", "nan") and len(causa_raiz) > 3) else "Não",
        })

    return (
        pd.DataFrame(registros)
        .sort_values(["Responsável", "ID"])
        .reset_index(drop=True)
    )
