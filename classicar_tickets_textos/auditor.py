from __future__ import annotations

import json
import os
import re
from html import escape as _esc
from pathlib import Path

import pandas as pd

from text_cleaner import consolidar_historico

_GENERICA_RE = re.compile(
    r"\b("
    r"tratativa\s+finalizada|"
    r"(o\s+)?erro\s+(foi\s+)?(solucionado|corrigido|resolvido)|"
    r"(o\s+)?problema\s+(foi\s+)?(solucionado|corrigido|resolvido)|"
    r"(foi\s+|est[aá]\s+)?(solucionado|resolvido|finalizado|conclu[íi]do|corrigido)|"
    r"(realizado|atendido|executado|feito)\s+conforme\s+solicitado|"
    r"ok[.!]?|pronto[.!]?"
    r")\b",
    re.IGNORECASE,
)

# Palavras técnicas específicas que indicam conteúdo real — evitam falso positivo
_SALVO_RE = re.compile(
    r"\b("
    r"altera[çc][aã]o|altera[çc][oõ]es|alterado|"
    r"parametriza[çc][aã]o|parametrizado|"
    r"configura[çc][aã]o|configura[çc][oõ]es|configurado|"
    r"ajustes?|"
    r"atualiza[çc][aã]o|atualizado|"
    r"implementa[çc][aã]o|implementado|"
    r"corre[çc][aã]o|"
    r"valida[çc][aã]o|validado|"
    r"verifica[çc][aã]o|verificado|"
    r"arquivos?|upload|"
    r"integra[çc][aã]o|"
    r"CFOP|SPED|ERP|NCM|Unifica|CNPJ|CEI|eSocial|REINF|DCTF"
    r")\b",
    re.IGNORECASE,
)

_COBRANCA_RE = re.compile(
    r"cobran[çc]a|encerramento administrativo|falta de retorno",
    re.IGNORECASE,
)

_DEV_RE = re.compile(
    r"\b(time\s+de\s+desenvolvimento|time\s+de\s+dev|tratativa\s+de\s+dev)\b",
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


def _calcular_max_gap_zumbi(historico: list[dict], status: str) -> float | None:
    msgs = [h for h in historico if pd.notna(h["timestamp"])]
    if not msgs:
        return None

    gaps = []
    ultimo_cliente_ts = None
    aguardando = False

    for h in msgs:
        if h["papel"] == "cliente":
            if not aguardando:
                ultimo_cliente_ts = h["timestamp"]
                aguardando = True
        else:
            if aguardando and ultimo_cliente_ts is not None:
                gaps.append((h["timestamp"] - ultimo_cliente_ts).total_seconds() / 86400)
            aguardando = False
            ultimo_cliente_ts = None

    if aguardando and ultimo_cliente_ts is not None:
        if "conclu" not in str(status).strip().lower():
            hoje = pd.Timestamp.now().normalize()
            gaps.append((hoje - ultimo_cliente_ts).total_seconds() / 86400)

    return max(gaps) if gaps else None


def _resolucao_generica(msgs_tecnico: list[dict]) -> bool:
    if not msgs_tecnico:
        return False

    def _e_generica(texto: str) -> bool:
        texto = texto.strip()
        sem_saudacao = _SAUDACAO_RE.sub("", texto).strip()
        sem_fechamento = _FECHAMENTO_RE.sub("", sem_saudacao).strip()
        if not sem_fechamento:
            return True
        if _SALVO_RE.search(sem_fechamento):
            return False
        if len(sem_fechamento) > 120:
            return False
        return bool(_GENERICA_RE.search(sem_fechamento))

    if not _e_generica(msgs_tecnico[-1]["texto"]):
        return False

    # Última mensagem é genérica — penúltima pode conter o conteúdo real
    if len(msgs_tecnico) >= 2 and not _e_generica(msgs_tecnico[-2]["texto"]):
        return False

    return True


def _regra_24_dias(ultima_atualizacao, categoria: str, status: str, tipo: str = "") -> str:
    is_melhoria = (
        str(categoria).strip().lower() == "melhorias"
        or str(tipo).strip().lower() == "melhoria"
    )
    if not is_melhoria:
        return "-"
    if "conclu" in str(status).strip().lower():
        return "-"
    if pd.isna(ultima_atualizacao) or str(ultima_atualizacao).strip() in ("", "nan"):
        return "Sem dados"
    try:
        ts = pd.Timestamp(ultima_atualizacao)
    except Exception:
        return "Sem dados"
    dias = (pd.Timestamp.now().normalize() - ts.normalize()).days
    return "Sim" if dias > 24 else "Não"


def _protocolo_encerramento(historico: list[dict]) -> bool:
    return any(
        h["papel"] == "tecnico" and bool(_COBRANCA_RE.search(h["texto"]))
        for h in historico
    )


def _link_clickup_ausente(historico: list[dict], link_url: str) -> bool:
    mencionou_dev = any(
        _DEV_RE.search(h["texto"])
        for h in historico if h["papel"] == "tecnico"
    )
    if not mencionou_dev:
        return False
    return str(link_url).strip() in ("", "nan")


def auditar(df_tickets: pd.DataFrame, df_textos_raw: pd.DataFrame) -> pd.DataFrame:
    df_tickets = df_tickets[df_tickets["Status"].str.strip().str.lower() != "cancelado"].copy()

    df_hist = consolidar_historico(df_textos_raw)
    hist_idx = df_hist.set_index("id_ticket")["historico"].to_dict()

    registros = []
    for _, ticket in df_tickets.iterrows():
        ticket_id = str(ticket["ID"])
        historico = hist_idx.get(ticket_id, [])
        msgs_tecnico = [h for h in historico if h["papel"] == "tecnico"]

        frt = _calcular_frt(historico)
        max_gap = _calcular_max_gap_zumbi(historico, ticket.get("Status", ""))
        causa_raiz = str(ticket.get("Causa Raíz", "")).strip()
        categoria = ticket.get("Categoria", "")
        status = ticket.get("Status", "")
        tipo = str(ticket.get("Tipo", "") or "").strip()
        link_url = str(ticket.get("Link ClickUp", "") or "").strip()

        # Zumbi Ativo: ticket está aguardando agora (última msg é do cliente, gap atual > 5 dias).
        # Distinto de Risco Zumbi, que guarda o pior gap histórico para conformidade mensal.
        msgs_com_ts = [h for h in historico if pd.notna(h.get("timestamp"))]
        zumbi_ativo = False
        if msgs_com_ts and "conclu" not in str(status).strip().lower():
            ultimo = msgs_com_ts[-1]
            if ultimo["papel"] == "cliente":
                gap_atual = (pd.Timestamp.now().normalize() - ultimo["timestamp"]).total_seconds() / 86400
                zumbi_ativo = gap_atual > 5

        registros.append({
            "ID": ticket_id,
            "Responsável": ticket.get("Responsável", ""),
            "Módulo": ticket.get("Módulo", ""),
            "Tipo": tipo,
            "Categoria": categoria,
            "Status": status,
            "Data Abertura": ticket.get("Data Abertura", ""),
            "FRT (horas)": round(frt, 1) if frt is not None else None,
            "FRT OK": "Sim" if (frt is not None and frt <= 2.0) else ("Não" if frt is not None else _label_sem_frt(historico)),
            "Gap Máx (dias)": round(max_gap, 1) if max_gap is not None else None,
            "Risco Zumbi": "Sim" if (max_gap is not None and max_gap > 5) else "Não",
            "Zumbi Ativo": zumbi_ativo,
            "Regra 24 Dias": _regra_24_dias(ticket.get("Última Atualização"), categoria, status, tipo),
            "Resolução Genérica": "Sim" if _resolucao_generica(msgs_tecnico) else "Não",
            "Causa Raíz Preenchida": "Sim" if (causa_raiz not in ("", "nan") and len(causa_raiz) > 3) else "Não",
            "Link ClickUp": (
                "Ausente" if _link_clickup_ausente(historico, link_url)
                else ("OK" if link_url and link_url != "nan" else "-")
            ),
        })

    return (
        pd.DataFrame(registros)
        .sort_values(["Responsável", "ID"])
        .reset_index(drop=True)
    )


def calcular_recorrencia(
    df_classificado: pd.DataFrame,
    df_textos_raw: pd.DataFrame,
) -> dict:
    hoje = pd.Timestamp.now()
    limite = hoje - pd.Timedelta(days=30)

    df = df_classificado.copy()
    df["ID"] = df["ID"].astype(str).str.strip()
    df["_data_ab"] = pd.to_datetime(
        df.get("Data Abertura", pd.Series(dtype=str)), dayfirst=True, errors="coerce"
    )
    df_30 = df[df["_data_ab"] >= limite].copy()

    vazio = {
        "n_total_30d": 0,
        "n_recorrente_cliente": 0,
        "pct_recorrente_cliente": None,
        "grupos_cliente": [],
        "n_com_causa": 0,
        "n_recorrente_causa": 0,
        "pct_recorrente_causa": None,
        "grupos_causa": [],
    }
    if df_30.empty:
        return vazio

    n_total_30d = len(df_30)

    # Métrica 1 — mesma Categoria (2+ tickets no período)
    grupos_cliente: list[dict] = []
    recorrentes_c: set[str] = set()
    if "Categoria" in df_30.columns:
        for cat, grp in df_30.groupby("Categoria"):
            if len(grp) < 2:
                continue
            ids = grp["ID"].tolist()
            recorrentes_c.update(ids)
            resps = (
                grp["Responsável"].dropna().tolist()
                if "Responsável" in grp.columns else []
            )
            grupos_cliente.append({
                "categoria": str(cat),
                "n": len(ids),
                "tickets": ids,
                "responsaveis": resps,
            })
        grupos_cliente.sort(key=lambda g: -g["n"])

    pct_c = len(recorrentes_c) / n_total_30d if n_total_30d > 0 else None

    # Métrica 2 — mesma Causa Raíz
    grupos_causa: list[dict] = []
    recorrentes_cr: set[str] = set()
    n_com_causa = 0
    pct_cr = None
    if "Causa Raíz" in df_30.columns:
        df_cr = df_30[
            df_30["Causa Raíz"].notna()
            & (df_30["Causa Raíz"].astype(str).str.strip().isin(["", "nan"]) == False)
        ].copy()
        n_com_causa = len(df_cr)
        for causa, grp in df_cr.groupby("Causa Raíz"):
            if len(grp) < 2:
                continue
            ids = grp["ID"].tolist()
            recorrentes_cr.update(ids)
            resps = (
                grp["Responsável"].dropna().tolist()
                if "Responsável" in grp.columns else []
            )
            grupos_causa.append({
                "causa": str(causa),
                "n": len(ids),
                "tickets": ids,
                "responsaveis": resps,
            })
        grupos_causa.sort(key=lambda g: -g["n"])
        pct_cr = len(recorrentes_cr) / n_com_causa if n_com_causa > 0 else None

    return {
        "n_total_30d": n_total_30d,
        "n_recorrente_cliente": len(recorrentes_c),
        "pct_recorrente_cliente": pct_c,
        "grupos_cliente": grupos_cliente,
        "n_com_causa": n_com_causa,
        "n_recorrente_causa": len(recorrentes_cr),
        "pct_recorrente_causa": pct_cr,
        "grupos_causa": grupos_causa,
    }


def auditar_conformidade_mensal(
    df_audit: pd.DataFrame,
    mes_ref: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, float | None, int, int]:
    """
    Retorna (df_resultado, pct_conformidade, n_total, n_conforme).
    Base: tickets concluídos no mês de referência (padrão: mês atual).
    FRT 'Sem dados' / 'Abertura Administrativa' → critério neutro (Opção A).
    """
    ref = mes_ref or pd.Timestamp.now()

    is_concluido = df_audit["Status"].str.strip().str.lower().str.contains("conclu", na=False)
    _datas = pd.to_datetime(
        df_audit.get("Data Abertura", pd.Series(dtype=str)), dayfirst=True, errors="coerce"
    )
    is_mes = (_datas.dt.month == ref.month) & (_datas.dt.year == ref.year)

    df_mes = df_audit[is_concluido & is_mes].copy()
    if df_mes.empty:
        return df_mes, None, 0, 0

    def _avaliar(row: pd.Series) -> list[str]:
        falhas = []
        if str(row.get("FRT OK", "")).strip() == "Não":
            falhas.append("FRT > 2h")
        if row.get("Risco Zumbi") == "Sim":
            falhas.append("Risco Zumbi")
        if row.get("Resolução Genérica") == "Sim":
            falhas.append("Resolução Genérica")
        if row.get("Link ClickUp") == "Ausente":
            falhas.append("Link ClickUp ausente")
        return falhas

    df_mes["_falhas"] = df_mes.apply(_avaliar, axis=1)
    df_mes["Conforme"] = df_mes["_falhas"].apply(lambda f: "Sim" if not f else "Não")
    df_mes["Critérios Reprovados"] = df_mes["_falhas"].apply(lambda f: ", ".join(f) if f else "—")
    df_mes = df_mes.drop(columns=["_falhas"])

    n_total = len(df_mes)
    n_conforme = int((df_mes["Conforme"] == "Sim").sum())
    pct = n_conforme / n_total if n_total > 0 else None

    return df_mes.sort_values(["Responsável", "ID"]).reset_index(drop=True), pct, n_total, n_conforme


# ── Geração do report HTML ────────────────────────────────────────────────────

_CONFIG_PATH = Path(__file__).parent.parent / "config.json"
_ENV_PATH    = Path(__file__).parent.parent / ".env"


def _carregar_env() -> None:
    if not _ENV_PATH.exists():
        return
    for linha in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        os.environ.setdefault(chave.strip(), valor.strip())

_SLA_ESTOURO  = "Acima do Teto (Nota: Tempo Corrido Bruto)"
_SLA_EXCLUIDOS = {"SLA Não Definido", "Sem Registro de Tempo", "Prazo Não Aplicável"}
_MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março",    4: "Abril",
    5: "Maio",    6: "Junho",     7: "Julho",     8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}

_CSS = (
    "body{font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#333;"
    "background:#f0f7f7;margin:0;padding:20px}"
    ".w{max-width:700px;margin:0 auto;background:#fff;border-radius:8px;"
    "box-shadow:0 2px 10px rgba(0,0,0,.1);overflow:hidden}"
    ".lb{background:#fff;padding:14px 24px;border-bottom:3px solid #008080}"
    ".lb-txt{font-size:18px;font-weight:800;color:#005f5f;letter-spacing:.5px}"
    ".hd{background:#005f5f;padding:16px 24px}"
    ".hd h1{margin:0;font-size:17px;font-weight:700;color:#fff;letter-spacing:.3px}"
    ".hd p{margin:5px 0 0;font-size:12px;color:#b2e5e5}"
    ".bd{padding:12px 24px 28px}"
    ".rt{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;"
    "color:#005f5f;margin:22px 0 6px;padding-bottom:5px;border-bottom:2px solid #008080}"
    ".rc{font-weight:normal;text-transform:none;letter-spacing:0;color:#999;font-size:12px}"
    ".tk{border:1px solid #b2e5e5;border-radius:6px;padding:11px 14px;margin:7px 0;"
    "background:#f5fdfd}"
    ".ti{font-weight:700;color:#003d3d;font-size:13px}"
    ".tm{color:#888;font-size:11px;margin:3px 0 8px}"
    ".f{display:inline-block;padding:2px 9px;border-radius:10px;font-size:11px;"
    "font-weight:600;margin:2px 3px 2px 0}"
    ".fc{background:#fde8e8;color:#c0392b;border:1px solid #e74c3c}"
    ".fa{background:#fff4e5;color:#c07800;border:1px solid #e07b00}"
    ".fl{background:#fffde7;color:#7a6200;border:1px solid #d4ac0d}"
    ".um{background:#eef8f8;border-left:3px solid #008080;padding:6px 10px;"
    "font-size:11px;color:#555;margin-top:8px;border-radius:0 4px 4px 0;"
    "font-style:italic}"
    ".ft{padding:10px 24px;font-size:11px;color:#bbb;border-top:1px solid #f0f0f0;"
    "text-align:center}"
    ".ms{background:#eef8f8;border-bottom:1px solid #b2e5e5;padding:14px 24px}"
    ".ms-t{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;"
    "color:#007070;margin-bottom:10px}"
    ".ms-c{background:#fff;border:1px solid #b2e5e5;border-radius:6px;"
    "padding:10px 12px;text-align:center;vertical-align:top}"
    ".ms-l{font-size:10px;font-weight:700;text-transform:uppercase;color:#888;letter-spacing:.3px}"
    ".ms-v{font-size:20px;font-weight:800;margin:4px 0 2px}"
    ".ms-m{font-size:10px;font-weight:600;color:#555;margin-bottom:2px}"
    ".ms-s{font-size:10px;color:#999}"
    ".ok{color:#1a8a3a;font-weight:800}"
    ".nk{color:#c0392b;font-weight:800}"
    ".dv{padding:12px 24px 20px;border-bottom:1px solid #e8e8e8}"
    ".sh{background:#005f5f;padding:11px 24px}"
    ".sh-lbl{font-size:13px;font-weight:700;color:#fff;letter-spacing:.3px}"
)


def _primeiro_nome(nome: str) -> str:
    partes = str(nome or "").strip().split()
    return partes[0].title() if partes else "—"


def _ultima_msg_tecnico(historico: list[dict]) -> str:
    for h in reversed(historico):
        if h["papel"] == "tecnico" and h["texto"].strip():
            t = h["texto"].strip()
            return (t[:250] + "…") if len(t) > 250 else t
    return ""


def _fmt_tempo(h: float) -> str:
    if h < 1:
        return f"{int(round(h * 60))}min"
    if h < 24:
        hh = int(h)
        mm = int(round((h - hh) * 60))
        if mm == 60:
            hh += 1
            mm = 0
        return f"{hh}h" if mm == 0 else f"{hh}h {mm}min"
    return f"{h / 24:.1f} dias"


def _dias_desde(ts) -> int | None:
    try:
        parsed = pd.to_datetime(ts, dayfirst=True, errors="coerce")
        if pd.isna(parsed):
            return None
        return (pd.Timestamp.now().normalize() - parsed.normalize()).days
    except Exception:
        return None


def _flags_do_ticket(row: pd.Series, tk: dict, historico: list[dict] | None = None) -> list[dict]:
    flags = []
    is_melhoria = (
        str(row.get("Categoria", "")).strip().lower() == "melhorias"
        or str(row.get("Tipo", "")).strip().lower() == "melhoria"
    )
    if row.get("Zumbi Ativo") == True and not is_melhoria:
        msgs_com_ts = [h for h in (historico or []) if pd.notna(h.get("timestamp"))]
        ultimo_cliente = next((h for h in reversed(msgs_com_ts) if h["papel"] == "cliente"), None)
        if ultimo_cliente and pd.notna(ultimo_cliente.get("timestamp")):
            gap_atual = int((pd.Timestamp.now().normalize() - ultimo_cliente["timestamp"]).total_seconds() / 86400)
            txt = f"Cliente aguardando há {gap_atual} dias"
        else:
            gap = row.get("Gap Máx (dias)")
            txt = f"Cliente aguardando há {int(gap)} dias" if pd.notna(gap) else "Gap > 5 dias"
        flags.append({"cls": "fc", "txt": txt})
    if row.get("Regra 24 Dias") == "Sim":
        dias = _dias_desde(tk.get("Última Atualização"))
        txt = (
            f"Melhoria sem atualização há {dias} dias"
            if dias else "Melhoria sem atualização há +24 dias"
        )
        flags.append({"cls": "fc", "txt": txt})
    frt_ok = row.get("FRT OK")
    frt_h = row.get("FRT (horas)")
    if frt_ok == "Não" and pd.notna(frt_h):
        flags.append({"cls": "fa", "txt": f"1ª resposta em {frt_h:.1f}h (limite: 2h)"})
    if row.get("Resolução Genérica") == "Sim":
        flags.append({"cls": "fa", "txt": "Encerramento genérico"})
    if row.get("Link ClickUp") == "Ausente":
        flags.append({"cls": "fc", "txt": "Escalado p/ Dev sem link ClickUp"})
    # Causa Raíz desativada temporariamente — regra de aplicação em definição
    return flags


def _tem_flag(row: pd.Series) -> bool:
    is_melhoria = (
        str(row.get("Categoria", "")).strip().lower() == "melhorias"
        or str(row.get("Tipo", "")).strip().lower() == "melhoria"
    )
    return (
        (not is_melhoria and row.get("Zumbi Ativo") == True)
        or row.get("Regra 24 Dias") == "Sim"
        or (row.get("FRT OK") == "Não" and pd.notna(row.get("FRT (horas)")))
        or row.get("Resolução Genérica") == "Sim"
        or row.get("Link ClickUp") == "Ausente"
        # Causa Raíz desativada temporariamente — regra de aplicação em definição
    )


def _calcular_metricas_mes(
    df_tickets: pd.DataFrame,
    df_audit: pd.DataFrame | None = None,
) -> dict:
    hoje = pd.Timestamp.now()
    df = df_tickets.copy()
    if "Data Abertura" in df.columns:
        df["_data_ab"] = pd.to_datetime(df["Data Abertura"], dayfirst=True, errors="coerce")
    else:
        df["_data_ab"] = pd.NaT
    df_mes = df[(df["_data_ab"].dt.month == hoje.month) & (df["_data_ab"].dt.year == hoje.year)]

    concluidos = (
        df_mes[df_mes["Status"].str.strip().str.lower().str.contains("conclu", na=False)]
        if "Status" in df_mes.columns else df_mes.iloc[:0]
    )
    pct_fora = None
    if "Status SLA" in concluidos.columns:
        com_sla = concluidos[~concluidos["Status SLA"].isin(_SLA_EXCLUIDOS)]
        if len(com_sla) > 0:
            pct_fora = float((com_sla["Status SLA"] == _SLA_ESTOURO).sum()) / len(com_sla)

    meta_mes, baseline = None, 0.48
    try:
        cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        metas = {int(k): v for k, v in cfg.get("metas_sla_mensal", {}).items()}
        meta_mes = metas.get(hoje.month)
        baseline = cfg.get("baseline_historico", 0.48)
    except Exception:
        pass

    pct_causa = None
    if "Causa Raíz" in concluidos.columns and len(concluidos) > 0:
        pct_causa = float(
            (concluidos["Causa Raíz"].notna() & (concluidos["Causa Raíz"].astype(str).str.strip() != "")).mean()
        )

    pct_conf, n_conf, n_tot_conf = None, 0, 0
    if df_audit is not None:
        _, pct_conf, n_tot_conf, n_conf = auditar_conformidade_mensal(df_audit)

    pct_melhoria = None
    if "Tipo" in df_mes.columns and len(df_mes) > 0:
        pct_melhoria = float(
            (df_mes["Tipo"].str.strip().str.lower() == "melhoria").sum()
        ) / len(df_mes)

    return {
        "pct_fora_prazo": pct_fora,
        "meta_mes": meta_mes,
        "baseline": baseline,
        "pct_causa_raiz": pct_causa,
        "pct_conformidade": pct_conf,
        "n_conformes": n_conf,
        "n_total_conf": n_tot_conf,
        "pct_melhoria": pct_melhoria,
        "mes_nome": f"{_MESES_PT.get(hoje.month, '')}/{hoje.year}",
        "n_concluidos_mes": len(concluidos),
        "n_tickets_mes": len(df_mes),
    }


def _html_metricas(m: dict) -> str:
    def _card(label: str, valor: str, meta_txt: str, sub: str) -> str:
        return (
            f"<div class='ms-c'><div class='ms-l'>{label}</div>"
            f"<div class='ms-v'>{valor}</div>"
            f"<div class='ms-m'>{meta_txt}</div>"
            f"<div class='ms-s'>{sub}</div></div>"
        )

    pct = m["pct_fora_prazo"]
    meta = m["meta_mes"] or m["baseline"]

    # Card 1 — Fora do Prazo
    if pct is not None:
        cor1 = "ok" if pct <= meta else "nk"
        v1 = f'<span class="{cor1}">{pct * 100:.1f}%</span>'
        s1 = f'{m["n_concluidos_mes"]} conclu&iacute;dos no m&ecirc;s'
    else:
        v1, s1 = '<span style="color:#bbb">&mdash;</span>', "sem conclu&iacute;dos no m&ecirc;s"
    m1 = f'Meta: &lt;&nbsp;{meta * 100:.0f}%'

    # Card 2 — Tolerância Máxima
    if m["meta_mes"] is not None:
        folga = (m["meta_mes"] - (pct or 0.0)) * 100
        cor2 = "ok" if folga >= 0 else "nk"
        v2 = f'<span class="{cor2}">{abs(folga):.1f}pp</span>'
        s2 = "de margem" if folga >= 0 else "acima da meta"
        m2 = f'Limite do m&ecirc;s: &lt;&nbsp;{m["meta_mes"] * 100:.0f}%'
    else:
        v2 = f'<span style="color:#888">&mdash;</span>'
        s2 = "m&ecirc;s sem meta definida"
        m2 = f'Base hist&oacute;rica: &lt;&nbsp;{m["baseline"] * 100:.0f}%'

    # Card 3 — Causa Raíz
    pct_cr = m["pct_causa_raiz"]
    if pct_cr is not None:
        cor3 = "ok" if pct_cr >= 0.8 else ("nk" if pct_cr < 0.5 else "")
        v3 = f'<span{"" if not cor3 else f" class=\'{cor3}\'"}">{pct_cr * 100:.1f}%</span>'
        s3 = f'{m["n_concluidos_mes"]} conclu&iacute;dos no m&ecirc;s'
    else:
        v3, s3 = '<span style="color:#bbb">&mdash;</span>', "sem dados"
    m3 = "Meta: 100%"

    # Card 4 — Conformidade
    pct_conf = m.get("pct_conformidade")
    if pct_conf is not None:
        cor4 = "ok" if pct_conf >= 0.90 else ("nk" if pct_conf < 0.70 else "")
        v4 = f'<span{"" if not cor4 else f" class=\'{cor4}\'"}">{pct_conf * 100:.1f}%</span>'
        n_conf = m.get("n_conformes", 0)
        n_tot  = m.get("n_total_conf", 0)
        s4 = f'{n_conf}/{n_tot} conclu&iacute;dos'
    else:
        v4, s4 = '<span style="color:#bbb">&mdash;</span>', "sem dados"
    m4 = "Meta: &ge;&nbsp;90%"

    # Card 5 — % Melhorias
    pct_mel = m.get("pct_melhoria")
    if pct_mel is not None:
        v5 = f'{pct_mel * 100:.1f}%'
        s5 = f'{m["n_tickets_mes"]} tickets no m&ecirc;s'
    else:
        v5, s5 = '<span style="color:#bbb">&mdash;</span>', "sem dados"
    m5 = "Acompanhamento"

    titulo = f"M&eacute;tricas do M&ecirc;s &mdash; {_esc(m['mes_nome'])}"
    return (
        f"<div class='ms'><div class='ms-t'>{titulo}</div>"
        f"<table width='100%' cellspacing='0' cellpadding='0'>"
        f"<tr>"
        f"<td style='width:32%;padding-right:5px;vertical-align:top;padding-bottom:6px'>"
        f"{_card('Fora do Prazo', v1, m1, s1)}</td>"
        f"<td style='width:32%;padding:0 5px;vertical-align:top;padding-bottom:6px'>"
        f"{_card('Margem Dispon&iacute;vel', v2, m2, s2)}</td>"
        f"<td style='width:32%;padding-left:5px;vertical-align:top;padding-bottom:6px'>"
        f"{_card('Conformidade', v4, m4, s4)}</td>"
        f"</tr>"
        f"<tr>"
        f"<td style='width:32%;padding-right:5px;vertical-align:top'>"
        f"{_card('Causa Ra&iacute;z', v3, m3, s3)}</td>"
        f"<td style='width:32%;padding:0 5px;vertical-align:top'>"
        f"{_card('Melhorias', v5, m5, s5)}</td>"
        f"<td style='width:32%;vertical-align:top'></td>"
        f"</tr>"
        f"</table></div>"
    )


def _calcular_desvios_sla(df_tickets: pd.DataFrame) -> list[dict]:
    hoje = pd.Timestamp.now()
    df = df_tickets.copy()

    if "Status SLA" not in df.columns or "Status" not in df.columns:
        return []

    df["_data_ab"] = pd.to_datetime(
        df.get("Data Abertura", pd.Series(dtype=str)), dayfirst=True, errors="coerce"
    )

    is_mes = (df["_data_ab"].dt.month == hoje.month) & (df["_data_ab"].dt.year == hoje.year)
    is_concluido = df["Status"].str.strip().str.lower().str.contains("conclu", na=False)
    is_aberto = ~is_concluido
    is_estouro = df["Status SLA"] == _SLA_ESTOURO
    is_sla_definido = ~df["Status SLA"].isin(_SLA_EXCLUIDOS) & df["Status SLA"].notna()

    mask_dev = is_estouro & ((is_concluido & is_mes) | is_aberto)
    mask_base = is_sla_definido & ((is_concluido & is_mes) | is_aberto)

    df_dev = df[mask_dev]
    df_base = df[mask_base]

    if df_dev.empty:
        return []

    grupos = []
    for (modulo, categoria), grp in df_dev.groupby(["Módulo", "Categoria"]):
        if pd.isna(modulo) or pd.isna(categoria):
            continue
        total = len(
            df_base[(df_base["Módulo"] == modulo) & (df_base["Categoria"] == categoria)]
        )
        n = len(grp)
        pct = n / total * 100 if total > 0 else 0.0
        tickets = [
            {
                "id": str(row["ID"]),
                "titulo": str(row.get("Título", "") or "").strip(),
                "tipo": str(row.get("Tipo", "") or "").strip(),
                "subcategoria": str(row.get("Subcategoria", "") or "").strip(),
                "status": str(row.get("Status", "") or "").strip(),
                "data_abertura": row.get("Data Abertura"),
                "resp": str(row.get("Responsável", "") or "").strip(),
                "piso": row.get("SLA Piso"),
                "teto": row.get("SLA Teto"),
                "gasto": row.get("Tempo Gasto (Horas)"),
                "status_sla": str(row.get("Status SLA", "") or ""),
            }
            for _, row in grp.sort_values("ID").iterrows()
        ]
        grupos.append({
            "modulo": str(modulo),
            "categoria": str(categoria),
            "n": n,
            "total": total,
            "pct": pct,
            "tickets": tickets,
        })

    return sorted(grupos, key=lambda g: -g["pct"])


def _fmt_horas(val) -> str:
    try:
        h = float(val)
        return f"{int(h)}h" if h == int(h) else f"{h:.1f}h"
    except Exception:
        return "—"


def _html_desvios(grupos: list[dict], mes_nome: str) -> str:
    if not grupos:
        return ""

    blocos = []
    for g in grupos:
        grupo_str = f"{_esc(g['modulo'])} &rsaquo; {_esc(g['categoria'])}"
        n, total, pct = g["n"], g["total"], g["pct"]
        s = "desvio" if n == 1 else "desvios"
        subtit = f"{n} {s} de {total} &middot; {pct:.0f}%"

        tks_html = []
        for t in g["tickets"]:
            tid = t["id"]
            titulo_raw = t.get("titulo", "").strip()
            header = (
                f"#{_esc(tid)} &mdash; {_esc(titulo_raw)}"
                if titulo_raw and titulo_raw != "nan"
                else f"#{_esc(tid)}"
            )

            tipo = t.get("tipo", "").strip()
            tipo_str = _esc(tipo) if tipo and tipo != "nan" else ""

            cat = _esc(g["categoria"])
            sub = t.get("subcategoria", "").strip()
            cat_str = f"{cat} &rsaquo; {_esc(sub)}" if sub and sub != "nan" else cat

            status = _esc(t.get("status", "").strip())
            resp   = _esc(t.get("resp", "").strip())

            data_ab = t.get("data_abertura")
            dias_ab = _dias_desde(data_ab)
            try:
                data_fmt = pd.to_datetime(data_ab, dayfirst=True, errors="coerce").strftime("%d/%m/%Y")
                ab_str = f"Aberto em {data_fmt} ({dias_ab} dias)" if dias_ab is not None else f"Aberto em {data_fmt}"
            except Exception:
                ab_str = f"Aberto h&aacute; {dias_ab} dias" if dias_ab is not None else ""

            meta = "&nbsp;&nbsp;|&nbsp;&nbsp;".join(
                p for p in [tipo_str, cat_str, status, resp, ab_str] if p
            )

            piso  = f"Piso {_fmt_horas(t['piso'])}"  if pd.notna(t.get("piso"))  else None
            teto  = f"Teto {_fmt_horas(t['teto'])}"  if pd.notna(t.get("teto"))  else None
            gv    = t.get("gasto")
            gasto = f"Gasto {_fmt_horas(gv)}"        if (pd.notna(gv) and float(gv) > 0) else None
            sts   = re.sub(r"\s*\(.*?\)", "", t["status_sla"]).strip()

            flags_html = "".join(
                f'<span class="f {cls}">{_esc(txt)}</span>'
                for txt, cls in [(piso, "fl"), (teto, "fl"), (gasto, "fa"), (sts, "fc")]
                if txt
            )

            tks_html.append(
                f'<div class="tk">'
                f'<div class="ti">{header}</div>'
                f'<div class="tm">{meta}</div>'
                f'<div>{flags_html}</div>'
                f'</div>'
            )

        blocos.append(
            f'<div class="rt">{grupo_str}'
            f' <span class="rc">— {subtit}</span></div>'
            + "".join(tks_html)
        )

    titulo = f"Desvios de SLA &mdash; {_esc(mes_nome)}"
    return (
        f"<div class='sh'><div class='sh-lbl'>{titulo}</div></div>"
        f"<div class='dv'>" + "".join(blocos) + "</div>"
    )


def _montar_df_flag(df_audit: pd.DataFrame, hoje: pd.Timestamp) -> pd.DataFrame:
    is_concluido = df_audit["Status"].str.strip().str.lower().str.contains("conclu", na=False)
    mask_abertos = df_audit.apply(_tem_flag, axis=1) & ~is_concluido
    if "Data Abertura" in df_audit.columns and "Link ClickUp" in df_audit.columns:
        _datas = pd.to_datetime(df_audit["Data Abertura"], dayfirst=True, errors="coerce")
        mask_cc = (
            is_concluido
            & (_datas.dt.month == hoje.month)
            & (_datas.dt.year == hoje.year)
            & (df_audit["Link ClickUp"] == "Ausente")
        )
    else:
        mask_cc = pd.Series(False, index=df_audit.index)
    return df_audit[mask_abertos | mask_cc].copy()


def _montar_ticket_html(row: pd.Series, tk: dict, historico: list[dict]) -> str:
    tid = str(row["ID"])
    titulo_raw = str(tk.get("Título", "") or "").strip()
    header = (
        f"#{tid} &mdash; {_esc(titulo_raw)}"
        if titulo_raw and titulo_raw != "nan" else f"#{tid}"
    )
    tipo = str(tk.get("Tipo", "") or "").strip()
    tipo_str = _esc(tipo) if tipo and tipo != "nan" else ""
    cat = str(row.get("Categoria", "")).strip()
    sub = str(tk.get("Subcategoria", "") or "").strip()
    cat_str = f"{_esc(cat)} &rsaquo; {_esc(sub)}" if sub and sub != "nan" else _esc(cat)
    status = _esc(str(row.get("Status", "")).strip())
    data_ab = tk.get("Data Abertura")
    dias_ab = _dias_desde(data_ab)
    try:
        data_fmt = pd.to_datetime(data_ab, dayfirst=True, errors="coerce").strftime("%d/%m/%Y")
        ab_str = f"Aberto em {data_fmt} ({dias_ab} dias)" if dias_ab is not None else f"Aberto em {data_fmt}"
    except Exception:
        ab_str = f"Aberto h&aacute; {dias_ab} dias" if dias_ab is not None else ""
    meta = "&nbsp;&nbsp;|&nbsp;&nbsp;".join(p for p in [tipo_str, cat_str, status, ab_str] if p)
    flags = _flags_do_ticket(row, tk, historico)
    flags_html = "".join(f'<span class="f {f["cls"]}">{_esc(f["txt"])}</span>' for f in flags)
    ultima = _ultima_msg_tecnico(historico)
    msg_html = f'<div class="um">&ldquo;{_esc(ultima)}&rdquo;</div>' if ultima else ""
    return (
        f'<div class="tk">'
        f'<div class="ti">{header}</div>'
        f'<div class="tm">{meta}</div>'
        f'<div>{flags_html}</div>'
        f'{msg_html}'
        f'</div>'
    )


def gerar_html_report(
    df_audit: pd.DataFrame,
    df_tickets: pd.DataFrame,
    df_textos_raw: pd.DataFrame,
) -> str:
    hoje = pd.Timestamp.now().normalize()
    data_str = hoje.strftime("%d/%m/%Y")

    _carregar_env()
    dashboard_url = os.environ.get("DASHBOARD_URL", "").strip()

    logo_html = "<div class='lb'><span class='lb-txt'>UniATEND</span></div>"

    m = _calcular_metricas_mes(df_tickets, df_audit)
    html_met = _html_metricas(m)
    html_dev = _html_desvios(_calcular_desvios_sla(df_tickets), m["mes_nome"])

    df_hist = consolidar_historico(df_textos_raw)
    hist_idx = df_hist.set_index("id_ticket")["historico"].to_dict()

    df_tk = df_tickets.copy()
    df_tk["ID"] = df_tk["ID"].astype(str).str.strip()
    tk_idx = df_tk.set_index("ID").to_dict("index")

    df_flag = _montar_df_flag(df_audit, hoje)

    cta_dashboard = (
        f"<div style='background:#eef8f8;border-top:1px solid #b2e5e5;"
        f"padding:20px 24px;text-align:center;'>"
        f"<div style='font-size:12px;color:#555;margin-bottom:12px;'>"
        f"Acesse o dashboard para filtrar por per&iacute;odo, m&oacute;dulo e ver o hist&oacute;rico completo.</div>"
        f"<a href='{dashboard_url}' style='display:inline-block;background:#005f5f;color:#ffffff;"
        f"font-weight:700;font-size:13px;text-decoration:none;padding:11px 28px;"
        f"border-radius:6px;letter-spacing:.3px;'>"
        f"Acessar o Dashboard &rarr;</a>"
        f"</div>"
        if dashboard_url else ""
    )

    def _tpl(corpo: str, subtit: str) -> str:
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<style>{_CSS}</style></head><body>"
            "<div class='w'>"
            f"{logo_html}"
            "<div class='hd'><h1>Auditoria UniATEND</h1>"
            f"<p>{data_str} &nbsp;&middot;&nbsp; {subtit}</p></div>"
            f"{html_met}"
            f"{html_dev}"
            "<div class='sh'><div class='sh-lbl'>Mandamentos do Playbook</div></div>"
            f"<div class='bd'>{corpo}</div>"
            f"{cta_dashboard}"
            "<div class='ft'>Gerado automaticamente pelo pipeline UniATEND</div>"
            "</div></body></html>"
        )

    if df_flag.empty:
        return _tpl(
            "<p style='color:#27ae60;padding:12px;font-style:italic'>"
            "Nenhum ponto de aten&ccedil;&atilde;o encontrado. Tudo OK!</p>",
            "Tudo OK",
        )

    blocos = []
    for resp, grupo in df_flag.groupby("Responsável"):
        tickets_html = [
            _montar_ticket_html(row, tk_idx.get(str(row["ID"]), {}), hist_idx.get(str(row["ID"]), []))
            for _, row in grupo.sort_values("ID").iterrows()
        ]
        n = len(grupo)
        s = "ponto" if n == 1 else "pontos"
        blocos.append(
            f'<div class="rt">{_esc(str(resp))}'
            f' <span class="rc">— {n} {s} de aten&ccedil;&atilde;o</span></div>'
            + "".join(tickets_html)
        )

    n_resp = df_flag["Responsável"].nunique()
    n_tick = len(df_flag)
    subtit = (
        f"{n_resp} respons&aacute;ve{'l' if n_resp == 1 else 'is'} &middot; "
        f"{n_tick} ticket{'s' if n_tick != 1 else ''} com pontos de aten&ccedil;&atilde;o"
    )
    return _tpl("".join(blocos), subtit)


def gerar_html_report_individual(
    df_audit: pd.DataFrame,
    df_tickets: pd.DataFrame,
    df_textos_raw: pd.DataFrame,
    responsavel: str,
) -> str:
    hoje = pd.Timestamp.now().normalize()
    data_str = hoje.strftime("%d/%m/%Y")

    _carregar_env()
    dashboard_url = os.environ.get("DASHBOARD_URL", "").strip()
    primeiro = _primeiro_nome(responsavel)
    mes_nome = f"{_MESES_PT.get(hoje.month, '')}/{hoje.year}"

    logo_html = "<div class='lb'><span class='lb-txt'>UniATEND</span></div>"

    df_audit_r   = df_audit[df_audit["Responsável"] == responsavel].copy()
    df_tickets_r = df_tickets[df_tickets["Responsável"] == responsavel].copy()

    html_dev = _html_desvios(_calcular_desvios_sla(df_tickets_r), mes_nome)

    df_hist   = consolidar_historico(df_textos_raw)
    hist_idx  = df_hist.set_index("id_ticket")["historico"].to_dict()
    df_tk     = df_tickets.copy()
    df_tk["ID"] = df_tk["ID"].astype(str).str.strip()
    tk_idx    = df_tk.set_index("ID").to_dict("index")

    df_flag = _montar_df_flag(df_audit_r, hoje)

    cta_dashboard = (
        f"<div style='background:#eef8f8;border-top:1px solid #b2e5e5;"
        f"padding:20px 24px;text-align:center;'>"
        f"<div style='font-size:12px;color:#555;margin-bottom:12px;'>"
        f"Acesse o dashboard para filtrar por per&iacute;odo, m&oacute;dulo e ver o hist&oacute;rico completo.</div>"
        f"<a href='{dashboard_url}' style='display:inline-block;background:#005f5f;color:#ffffff;"
        f"font-weight:700;font-size:13px;text-decoration:none;padding:11px 28px;"
        f"border-radius:6px;letter-spacing:.3px;'>"
        f"Acessar o Dashboard &rarr;</a>"
        f"</div>"
        if dashboard_url else ""
    )

    def _tpl(corpo: str, subtit: str) -> str:
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<style>{_CSS}</style></head><body>"
            "<div class='w'>"
            f"{logo_html}"
            "<div class='hd'><h1>Auditoria UniATEND</h1>"
            f"<p>{data_str} &nbsp;&middot;&nbsp; {subtit}</p></div>"
            f"{html_dev}"
            "<div class='sh'><div class='sh-lbl'>Mandamentos do Playbook</div></div>"
            f"<div class='bd'>{corpo}</div>"
            f"{cta_dashboard}"
            "<div class='ft'>Gerado automaticamente pelo pipeline UniATEND</div>"
            "</div></body></html>"
        )

    if df_flag.empty:
        return _tpl(
            f"<p style='color:#27ae60;padding:12px;font-size:14px'>"
            f"Ol&aacute;, {_esc(primeiro)}! Nenhum desvio de atendimento para tratar hoje. "
            f"Parab&eacute;ns pelo trabalho!</p>",
            f"Ol&aacute;, {_esc(primeiro)}! &nbsp;&middot;&nbsp; Tudo em dia",
        )

    tickets_html = [
        _montar_ticket_html(row, tk_idx.get(str(row["ID"]), {}), hist_idx.get(str(row["ID"]), []))
        for _, row in df_flag.sort_values("ID").iterrows()
    ]
    n = len(df_flag)
    s = "ponto" if n == 1 else "pontos"
    corpo = (
        f'<div class="rt">Seus tickets com pontos de aten&ccedil;&atilde;o'
        f' <span class="rc">— {data_str}</span></div>'
        + "".join(tickets_html)
    )
    subtit = f"Ol&aacute;, {_esc(primeiro)}! &nbsp;&middot;&nbsp; {n} {s} de aten&ccedil;&atilde;o"
    return _tpl(corpo, subtit)


def _calcular_metricas_conformidade(
    df_classificado: pd.DataFrame,
    df_audit_full: pd.DataFrame | None,
    n_total: int,
    n_conforme: int,
    pct: float,
    mes_ref: pd.Timestamp | None = None,
) -> dict:
    ref = mes_ref or pd.Timestamp.now()
    df = df_classificado.copy()
    df["ID"] = df["ID"].astype(str).str.strip()
    df["_data_ab"] = pd.to_datetime(
        df.get("Data Abertura", pd.Series(dtype=str)), dayfirst=True, errors="coerce"
    )
    is_mes = (df["_data_ab"].dt.month == ref.month) & (df["_data_ab"].dt.year == ref.year)
    df_mes = df[is_mes].copy()
    n_mes = len(df_mes)

    is_conc = df_mes["Status"].str.strip().str.lower().str.contains("conclu", na=False)
    df_conc = df_mes[is_conc]

    # Tempo mediano e médio — concluídos no mês
    tempo_mediano = tempo_medio = None
    if "Tempo Gasto (Horas)" in df_conc.columns and len(df_conc) > 0:
        vals = df_conc["Tempo Gasto (Horas)"].dropna()
        if len(vals) > 0:
            tempo_mediano = float(vals.median())
            tempo_medio = float(vals.mean())

    # % melhoria — todos os tickets do mês
    n_melhoria = 0
    pct_melhoria = None
    if "Tipo" in df_mes.columns and n_mes > 0:
        n_melhoria = int((df_mes["Tipo"].str.strip().str.lower() == "melhoria").sum())
        pct_melhoria = n_melhoria / n_mes

    # % erro → dev — Tipo=Erro com Link ClickUp ≠ "-" no mês
    n_erro_dev = 0
    pct_erro_dev = None
    if df_audit_full is not None and n_mes > 0:
        df_aud = df_audit_full.copy()
        df_aud["ID"] = df_aud["ID"].astype(str).str.strip()
        df_aud_mes = df_aud[df_aud["ID"].isin(df_mes["ID"])]
        if "Tipo" in df_aud_mes.columns and "Link ClickUp" in df_aud_mes.columns:
            mask = (
                df_aud_mes["Tipo"].str.strip().str.lower() == "erro"
            ) & ~df_aud_mes["Link ClickUp"].isin(["-", "", "nan"])
            n_erro_dev = int(mask.sum())
            pct_erro_dev = n_erro_dev / n_mes

    # Causa raíz breakdown — tickets do mês com causa preenchida
    causa_breakdown: list[dict] = []
    if "Causa Raíz" in df_mes.columns:
        cr = df_mes["Causa Raíz"].dropna()
        cr = cr[~cr.astype(str).str.strip().isin(["", "nan"])]
        for causa, cnt in cr.value_counts().items():
            causa_breakdown.append({"causa": str(causa), "n": int(cnt)})

    return {
        "pct_conformidade": pct,
        "n_conforme": n_conforme,
        "n_total": n_total,
        "n_nao_conforme": n_total - n_conforme,
        "tempo_mediano": tempo_mediano,
        "tempo_medio": tempo_medio,
        "n_concluidos": len(df_conc),
        "pct_melhoria": pct_melhoria,
        "n_melhoria": n_melhoria,
        "pct_erro_dev": pct_erro_dev,
        "n_erro_dev": n_erro_dev,
        "n_mes": n_mes,
        "causa_breakdown": causa_breakdown,
    }


def _html_cards_mensais(m: dict, mes_nome: str) -> str:
    def _card(titulo: str, valor: str, meta: str, sub: str, cor: str = "#888") -> str:
        return (
            f"<div class='ms-c' style='border-top:3px solid {cor}'>"
            f"<div class='ms-l'>{titulo}</div>"
            f"<div class='ms-v'>{valor}</div>"
            f"<div class='ms-m'>{meta}</div>"
            f"<div class='ms-s'>{sub}</div>"
            f"</div>"
        )

    # Conformidade
    pct_c = m["pct_conformidade"]
    cor1 = "#02683d" if pct_c >= 0.90 else ("#c0392b" if pct_c < 0.70 else "#e07b00")
    cls1 = "ok" if pct_c >= 0.90 else ("nk" if pct_c < 0.70 else "")
    v1 = f'<span{"" if not cls1 else f" class=\"{cls1}\""}">{pct_c * 100:.1f}%</span>'
    c1 = _card("Conformidade", v1, "Meta: &ge;&nbsp;90%", f'{m["n_conforme"]}/{m["n_total"]} conformes', cor1)

    # Não Conformes
    n_nao = m["n_nao_conforme"]
    cor2 = "#c0392b" if n_nao > 0 else "#02683d"
    v2 = f'<span class="{"nk" if n_nao > 0 else "ok"}">{n_nao}</span>'
    c2 = _card("N&atilde;o Conformes", v2, "&nbsp;", f'{m["n_total"]} conclu&iacute;dos no m&ecirc;s', cor2)

    # Tempo Mediano
    tm = m.get("tempo_mediano")
    tmed = m.get("tempo_medio")
    if tm is not None:
        v3 = f"<span>{_fmt_tempo(tm)}</span>"
        m3 = f"M&eacute;dia: {_fmt_tempo(tmed)}" if tmed is not None else "&nbsp;"
        s3 = f'{m["n_concluidos"]} conclu&iacute;dos no m&ecirc;s'
        cor3 = "#1a8c55"
    else:
        v3, m3, s3, cor3 = '<span style="color:#bbb">&mdash;</span>', "&nbsp;", "sem dados", "#ccc"
    c3 = _card("Tempo Mediano", v3, m3, s3, cor3)

    # % Melhoria
    pm = m.get("pct_melhoria")
    if pm is not None:
        v4 = f"{pm * 100:.1f}%"
        s4 = f'{m["n_melhoria"]}/{m["n_mes"]} tickets no m&ecirc;s'
        cor4 = "#888"
    else:
        v4, s4, cor4 = '<span style="color:#bbb">&mdash;</span>', "sem dados", "#ccc"
    c4 = _card("Melhorias", v4, "Acompanhamento", s4, cor4)

    # % Erro → Dev
    pe = m.get("pct_erro_dev")
    if pe is not None:
        v5 = f"{pe * 100:.1f}%"
        s5 = f'{m["n_erro_dev"]}/{m["n_mes"]} tickets no m&ecirc;s'
        cor5 = "#e07b00" if pe > 0.10 else "#888"
    else:
        v5, s5, cor5 = '<span style="color:#bbb">&mdash;</span>', "sem dados", "#ccc"
    c5 = _card("Erro &rarr; Dev", v5, "Acompanhamento", s5, cor5)

    # Causa Raíz
    n_cr = len(m.get("causa_breakdown", []))
    if n_cr > 0:
        total_cr = sum(g["n"] for g in m["causa_breakdown"])
        v6 = f'{n_cr} causa{"s" if n_cr != 1 else ""}'
        s6 = f"{total_cr} tickets identificados"
        cor6 = "#02683d"
    else:
        v6, s6, cor6 = '<span style="color:#bbb">&mdash;</span>', "em preenchimento", "#ccc"
    c6 = _card("Causa Ra&iacute;z", v6, "Acompanhamento", s6, cor6)

    td1 = "style='width:32%;padding-right:5px;vertical-align:top;padding-bottom:6px'"
    td2 = "style='width:32%;padding:0 5px;vertical-align:top;padding-bottom:6px'"
    td3 = "style='width:32%;padding-left:5px;vertical-align:top;padding-bottom:6px'"
    return (
        f"<div class='ms'><div class='ms-t'>Indicadores do M&ecirc;s &mdash; {_esc(mes_nome)}</div>"
        f"<table width='100%' cellspacing='0' cellpadding='0'>"
        f"<tr><td {td1}>{c1}</td><td {td2}>{c2}</td><td {td3}>{c3}</td></tr>"
        f"<tr><td {td1}>{c4}</td><td {td2}>{c5}</td><td {td3}>{c6}</td></tr>"
        f"</table></div>"
    )


def _html_causa_raiz_breakdown(causa_breakdown: list[dict]) -> str:
    if not causa_breakdown:
        return ""
    max_n = max(g["n"] for g in causa_breakdown)
    linhas: list[str] = []
    for g in causa_breakdown:
        pct_b = g["n"] / max_n * 100
        s = "ticket" if g["n"] == 1 else "tickets"
        linhas.append(
            f"<table width='100%' cellspacing='0' cellpadding='0' style='margin-bottom:7px'><tr>"
            f"<td style='width:40%;font-size:12px;color:#1f2937;padding-right:10px;"
            f"vertical-align:middle;word-break:break-word'>{_esc(g['causa'])}</td>"
            f"<td style='width:52%;vertical-align:middle'>"
            f"<div style='background:#d4edda;border-radius:3px;height:14px;overflow:hidden'>"
            f"<div style='background:#02683d;height:14px;width:{pct_b:.1f}%'></div>"
            f"</div></td>"
            f"<td style='width:8%;font-size:12px;font-weight:700;color:#02683d;"
            f"text-align:right;padding-left:8px;vertical-align:middle;white-space:nowrap'>"
            f"{g['n']} {s}</td>"
            f"</tr></table>"
        )
    return (
        f"<div class='sh'><div class='sh-lbl'>Chamados por Causa Ra&iacute;z</div></div>"
        f"<div class='dv'>"
        f"<div style='background:#f8fffe;border:1px solid #b2e5e5;border-radius:6px;padding:14px 16px'>"
        + "".join(linhas)
        + "</div></div>"
    )


def _html_recorrencia(dados: dict, mes_nome: str) -> str:
    if not dados or dados["n_total_30d"] == 0:
        return ""

    def _card_rec(label: str, valor: str, sub: str) -> str:
        return (
            f"<div class='ms-c'><div class='ms-l'>{label}</div>"
            f"<div class='ms-v'>{valor}</div>"
            f"<div class='ms-s'>{sub}</div></div>"
        )

    pct_c  = dados["pct_recorrente_cliente"]
    pct_cr = dados["pct_recorrente_causa"]
    n30    = dados["n_total_30d"]

    v_c   = f"{pct_c * 100:.1f}%"  if pct_c  is not None else '<span style="color:#bbb">&mdash;</span>'
    v_cr  = f"{pct_cr * 100:.1f}%" if pct_cr is not None else '<span style="color:#bbb">&mdash;</span>'
    sub_c  = f'{dados["n_recorrente_cliente"]} de {n30} tickets &mdash; &uacute;lt. 30 dias'
    sub_cr = f'{dados["n_recorrente_causa"]} de {dados["n_com_causa"]} com causa ra&iacute;z preenchida'

    cards = (
        f"<div class='ms'>"
        f"<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        f"<td style='width:48%;padding-right:6px;vertical-align:top'>"
        f"{_card_rec('Recorr&ecirc;ncia por Categoria', v_c, sub_c)}</td>"
        f"<td style='width:48%;padding-left:6px;vertical-align:top'>"
        f"{_card_rec('Recorr&ecirc;ncia por Causa Ra&iacute;z', v_cr, sub_cr)}</td>"
        f"<td style='width:4%;vertical-align:top'></td>"
        f"</tr></table></div>"
    )

    blocos = [cards]

    def _barras(grupos: list[dict], chave_nome: str, chave_n: str) -> str:
        if not grupos:
            return ""
        max_n = max(g[chave_n] for g in grupos)
        linhas_b: list[str] = []
        for g in grupos:
            pct_b = g[chave_n] / max_n * 100
            s = "ticket" if g[chave_n] == 1 else "tickets"
            linhas_b.append(
                f"<table width='100%' cellspacing='0' cellpadding='0' style='margin-bottom:7px'><tr>"
                f"<td style='width:38%;font-size:12px;color:#1f2937;padding-right:10px;"
                f"vertical-align:middle;word-break:break-word'>{_esc(str(g[chave_nome]))}</td>"
                f"<td style='width:54%;vertical-align:middle'>"
                f"<div style='background:#d4edda;border-radius:3px;height:14px;overflow:hidden'>"
                f"<div style='background:#02683d;height:14px;width:{pct_b:.1f}%'></div>"
                f"</div></td>"
                f"<td style='width:8%;font-size:12px;font-weight:700;color:#02683d;"
                f"text-align:right;padding-left:8px;vertical-align:middle;white-space:nowrap'>"
                f"{g[chave_n]} {s}</td>"
                f"</tr></table>"
            )
        return (
            f"<div style='background:#f8fffe;border:1px solid #b2e5e5;border-radius:6px;"
            f"padding:14px 16px;margin:10px 0 4px'>"
            + "".join(linhas_b)
            + "</div>"
        )

    # Seção — por categoria
    titulo_cat = (
        f"<div class='sh'><div class='sh-lbl'>"
        f"Recorr&ecirc;ncia por Categoria &mdash; &uacute;ltimos 30 dias"
        f"</div></div>"
    )
    if dados["grupos_cliente"]:
        grafico_cat = _barras(dados["grupos_cliente"], "categoria", "n")
        linhas: list[str] = []
        for g in dados["grupos_cliente"]:
            ids_str = ", ".join(f"#{t}" for t in g["tickets"])
            resps = list(dict.fromkeys(
                str(r) for r in g["responsaveis"] if r and str(r) not in ("", "nan")
            ))
            resp_str = " &middot; ".join(_esc(r) for r in resps)
            linhas.append(
                f'<div class="tk">'
                f'<div class="ti">{_esc(g["categoria"])}</div>'
                f'<div class="tm">{ids_str}</div>'
                f'{"<div class=\"tm\">" + resp_str + "</div>" if resp_str else ""}'
                f'<div><span class="f fc">{g["n"]} tickets na mesma categoria</span></div>'
                f'</div>'
            )
        blocos.append(
            titulo_cat
            + f"<div class='dv'>{grafico_cat}"
            f"<div class='rt' style='margin-top:18px'>Detalhe por categoria</div>"
            f"{''.join(linhas)}</div>"
        )
    elif pct_c is not None:
        blocos.append(
            titulo_cat
            + f"<div class='dv'><p style='color:#27ae60;font-style:italic;font-size:13px;margin:8px 0'>"
            f"Nenhuma categoria recorrente no per&iacute;odo.</p></div>"
        )

    # Seção — por causa raíz
    titulo_cr = (
        f"<div class='sh'><div class='sh-lbl'>"
        f"Recorr&ecirc;ncia por Causa Ra&iacute;z &mdash; &uacute;ltimos 30 dias"
        f"</div></div>"
    )
    if dados["grupos_causa"]:
        grafico_cr = _barras(dados["grupos_causa"], "causa", "n")
        linhas_cr: list[str] = []
        for g in dados["grupos_causa"]:
            ids_str = ", ".join(f"#{t}" for t in g["tickets"])
            resps = list(dict.fromkeys(
                str(r) for r in g["responsaveis"] if r and str(r) not in ("", "nan")
            ))
            resp_str = " &middot; ".join(_esc(r) for r in resps)
            linhas_cr.append(
                f'<div class="tk">'
                f'<div class="ti">{_esc(g["causa"])}</div>'
                f'<div class="tm">{ids_str}</div>'
                f'{"<div class=\"tm\">" + resp_str + "</div>" if resp_str else ""}'
                f'<div><span class="f fc">{g["n"]} tickets com a mesma causa ra&iacute;z</span></div>'
                f'</div>'
            )
        blocos.append(
            titulo_cr
            + f"<div class='dv'>{grafico_cr}"
            f"<div class='rt' style='margin-top:18px'>Detalhe por causa ra&iacute;z</div>"
            f"{''.join(linhas_cr)}</div>"
        )
    elif pct_cr is not None:
        blocos.append(
            titulo_cr
            + f"<div class='dv'><p style='color:#27ae60;font-style:italic;font-size:13px;margin:8px 0'>"
            f"Nenhuma causa ra&iacute;z recorrente no per&iacute;odo.</p></div>"
        )

    return "".join(blocos)


def gerar_html_report_conformidade(
    df_conf: pd.DataFrame,
    pct: float,
    n_total: int,
    n_conforme: int,
    df_classificado: pd.DataFrame | None = None,
    df_textos_raw: pd.DataFrame | None = None,
    df_audit_full: pd.DataFrame | None = None,
    mes_ref: pd.Timestamp | None = None,
) -> str:
    _carregar_env()
    ref = mes_ref or pd.Timestamp.now()
    data_str = pd.Timestamp.now().strftime("%d/%m/%Y")
    mes_nome = f"{_MESES_PT.get(ref.month, '')}/{ref.year}"
    dashboard_url = os.environ.get("DASHBOARD_URL", "").strip()

    if df_classificado is not None:
        m = _calcular_metricas_conformidade(df_classificado, df_audit_full, n_total, n_conforme, pct, mes_ref=ref)
        cards_html = _html_cards_mensais(m, mes_nome)
        secao_causa = _html_causa_raiz_breakdown(m["causa_breakdown"])
    else:
        cor_geral = "ok" if pct >= 0.90 else ("nk" if pct < 0.70 else "")
        pct_str = f'<span{"" if not cor_geral else f" class=\'{cor_geral}\'"}">{pct * 100:.1f}%</span>'
        cards_html = (
            f"<div class='ms'><table width='100%' cellspacing='0' cellpadding='0'><tr>"
            f"<td style='width:32%;padding-right:5px;vertical-align:top'>"
            f"<div class='ms-c'><div class='ms-l'>Conformidade Geral</div>"
            f"<div class='ms-v'>{pct_str}</div>"
            f"<div class='ms-m'>Meta: &ge;&nbsp;90%</div>"
            f"<div class='ms-s'>{n_conforme}/{n_total} tickets conformes</div></div></td>"
            f"<td style='width:32%;padding:0 5px;vertical-align:top'>"
            f"<div class='ms-c'><div class='ms-l'>N&atilde;o Conformes</div>"
            f"<div class='ms-v'><span class='{'nk' if (n_total - n_conforme) > 0 else 'ok'}'>"
            f"{n_total - n_conforme}</span></div>"
            f"<div class='ms-m'>&nbsp;</div>"
            f"<div class='ms-s'>{n_total} conclu&iacute;dos no m&ecirc;s</div></div></td>"
            f"<td style='width:32%;padding-left:5px;vertical-align:top'></td>"
            f"</tr></table></div>"
        )
        secao_causa = ""

    # Breakdown por responsável
    resumo = []
    for resp, grp in df_conf.groupby("Responsável"):
        total_r = len(grp)
        conf_r = int((grp["Conforme"] == "Sim").sum())
        pct_r = conf_r / total_r if total_r > 0 else 0.0
        resumo.append({"resp": str(resp), "conf": conf_r, "total": total_r, "pct": pct_r})
    resumo.sort(key=lambda r: r["pct"])

    linhas_resumo = []
    for r in resumo:
        cor_r = "ok" if r["pct"] >= 0.90 else ("nk" if r["pct"] < 0.70 else "")
        pct_r_str = f'<span{"" if not cor_r else f" class=\'{cor_r}\'"}">{r["pct"] * 100:.1f}%</span>'
        linhas_resumo.append(
            f"<tr style='border-bottom:1px solid #f0f0f0'>"
            f"<td style='padding:7px 10px;font-size:13px;color:#1f2937'>{_esc(r['resp'])}</td>"
            f"<td style='padding:7px 10px;text-align:center;font-size:13px'>{r['conf']}/{r['total']}</td>"
            f"<td style='padding:7px 10px;text-align:center;font-weight:700'>{pct_r_str}</td>"
            f"</tr>"
        )

    tabela_resumo = (
        f"<div class='sh'><div class='sh-lbl'>Resultado por Respons&aacute;vel</div></div>"
        f"<div class='dv'>"
        f"<table width='100%' cellspacing='0' cellpadding='0' "
        f"style='border-collapse:collapse;border:1px solid #e8e8e8;border-radius:6px;overflow:hidden'>"
        f"<tr style='background:#f8fffe'>"
        f"<th style='padding:7px 10px;text-align:left;font-size:11px;font-weight:700;"
        f"text-transform:uppercase;color:#005f5f;letter-spacing:.4px'>Respons&aacute;vel</th>"
        f"<th style='padding:7px 10px;text-align:center;font-size:11px;font-weight:700;"
        f"text-transform:uppercase;color:#005f5f;letter-spacing:.4px'>Conformes / Total</th>"
        f"<th style='padding:7px 10px;text-align:center;font-size:11px;font-weight:700;"
        f"text-transform:uppercase;color:#005f5f;letter-spacing:.4px'>%</th>"
        f"</tr>"
        + "".join(linhas_resumo)
        + f"</table></div>"
    )

    # Tickets não-conformes por responsável
    df_nao = df_conf[df_conf["Conforme"] == "Não"].copy()
    blocos_nao = []
    for resp, grp in df_nao.groupby("Responsável"):
        tickets_html = []
        for _, row in grp.sort_values("ID").iterrows():
            tid = _esc(str(row["ID"]))
            criterios = str(row.get("Critérios Reprovados", "")).strip()
            cat = _esc(str(row.get("Categoria", "")).strip())
            status = _esc(str(row.get("Status", "")).strip())
            data_ab = row.get("Data Abertura")
            try:
                data_fmt = pd.to_datetime(data_ab, dayfirst=True, errors="coerce").strftime("%d/%m/%Y")
            except Exception:
                data_fmt = ""
            meta = "&nbsp;&nbsp;|&nbsp;&nbsp;".join(p for p in [cat, status, data_fmt] if p)
            flags_html = "".join(
                f'<span class="f fc">{_esc(c.strip())}</span>'
                for c in criterios.split(",") if c.strip() and c.strip() != "—"
            )
            tickets_html.append(
                f'<div class="tk">'
                f'<div class="ti">#{tid}</div>'
                f'<div class="tm">{meta}</div>'
                f'<div>{flags_html}</div>'
                f'</div>'
            )
        n_r = len(grp)
        s_r = "ticket" if n_r == 1 else "tickets"
        blocos_nao.append(
            f'<div class="rt">{_esc(str(resp))}'
            f' <span class="rc">— {n_r} {s_r} n&atilde;o conforme{"s" if n_r != 1 else ""}</span></div>'
            + "".join(tickets_html)
        )

    secao_nao = (
        f"<div class='sh'><div class='sh-lbl'>Tickets N&atilde;o Conformes</div></div>"
        f"<div class='bd'>{''.join(blocos_nao)}</div>"
        if blocos_nao else ""
    )

    secao_rec = ""
    if df_classificado is not None and df_textos_raw is not None:
        rec = calcular_recorrencia(df_classificado, df_textos_raw)
        secao_rec = _html_recorrencia(rec, mes_nome)

    cta = (
        f"<div style='background:#eef8f8;border-top:1px solid #b2e5e5;"
        f"padding:20px 24px;text-align:center;'>"
        f"<div style='font-size:12px;color:#555;margin-bottom:12px;'>"
        f"Acesse o dashboard para o hist&oacute;rico completo de conformidade.</div>"
        f"<a href='{dashboard_url}' style='display:inline-block;background:#005f5f;color:#ffffff;"
        f"font-weight:700;font-size:13px;text-decoration:none;padding:11px 28px;"
        f"border-radius:6px;letter-spacing:.3px;'>Acessar o Dashboard &rarr;</a></div>"
        if dashboard_url else ""
    )

    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<style>{_CSS}</style></head><body>"
        "<div class='w'>"
        "<div class='lb'><span class='lb-txt'>UniATEND</span></div>"
        "<div class='hd'><h1>Auditoria Mensal de Conformidade</h1>"
        f"<p>{data_str} &nbsp;&middot;&nbsp; {_esc(mes_nome)}</p></div>"
        f"{cards_html}"
        f"{secao_causa}"
        f"{tabela_resumo}"
        f"{secao_nao}"
        f"{secao_rec}"
        f"{cta}"
        "<div class='ft'>Gerado automaticamente pelo pipeline UniATEND</div>"
        "</div></body></html>"
    )
