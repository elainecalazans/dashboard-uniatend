from __future__ import annotations

import base64
import json
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
    ultima = msgs_tecnico[-1]["texto"].strip()
    sem_saudacao = _SAUDACAO_RE.sub("", ultima).strip()
    sem_fechamento = _FECHAMENTO_RE.sub("", sem_saudacao).strip()
    if not sem_fechamento:
        return True
    if _SALVO_RE.search(sem_fechamento):
        return False
    if len(sem_fechamento) > 120:
        return False
    return bool(_GENERICA_RE.search(sem_fechamento))


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

        registros.append({
            "ID": ticket_id,
            "Responsável": ticket.get("Responsável", ""),
            "Módulo": ticket.get("Módulo", ""),
            "Tipo": tipo,
            "Categoria": categoria,
            "Status": status,
            "FRT (horas)": round(frt, 1) if frt is not None else None,
            "FRT OK": "Sim" if (frt is not None and frt <= 2.0) else ("Não" if frt is not None else _label_sem_frt(historico)),
            "Gap Máx (dias)": round(max_gap, 1) if max_gap is not None else None,
            "Risco Zumbi": "Sim" if (max_gap is not None and max_gap > 5) else "Não",
            "Regra 24 Dias": _regra_24_dias(ticket.get("Última Atualização"), categoria, status, tipo),
            "Resolução Genérica": "Sim" if _resolucao_generica(msgs_tecnico) else "Não",
            "Causa Raíz Preenchida": "Sim" if (causa_raiz not in ("", "nan") and len(causa_raiz) > 3) else "Não",
        })

    return (
        pd.DataFrame(registros)
        .sort_values(["Responsável", "ID"])
        .reset_index(drop=True)
    )


# ── Geração do report HTML ────────────────────────────────────────────────────

_LOGO_PATH   = Path(__file__).parent.parent / "relatorio_dashboard" / "ícone uniatend.png"
_CONFIG_PATH = Path(__file__).parent.parent / "config.json"

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
    ".lb img{height:42px;display:block}"
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
    "font-style:italic;word-break:break-word}"
    ".ft{padding:10px 24px;font-size:11px;color:#bbb;border-top:1px solid #f0f0f0;"
    "text-align:center}"
    ".ms{background:#eef8f8;border-bottom:1px solid #b2e5e5;padding:14px 24px}"
    ".ms-t{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;"
    "color:#007070;margin-bottom:10px}"
    ".ms-g{display:flex;gap:10px}"
    ".ms-c{flex:1;background:#fff;border:1px solid #b2e5e5;border-radius:6px;"
    "padding:10px 12px;text-align:center}"
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
    if row.get("Risco Zumbi") == "Sim" and not is_melhoria:
        gap = row.get("Gap Máx (dias)")
        msgs_com_ts = [h for h in (historico or []) if pd.notna(h.get("timestamp"))]
        ja_respondido = bool(msgs_com_ts) and msgs_com_ts[-1]["papel"] == "tecnico"
        if ja_respondido:
            txt = f"Cliente aguardou {int(gap)} dias — técnico já respondeu" if pd.notna(gap) else "Gap > 5 dias — técnico já respondeu"
            flags.append({"cls": "fa", "txt": txt})
        else:
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
    # Causa Raíz desativada temporariamente — regra de aplicação em definição
    return flags


def _tem_flag(row: pd.Series) -> bool:
    is_melhoria = (
        str(row.get("Categoria", "")).strip().lower() == "melhorias"
        or str(row.get("Tipo", "")).strip().lower() == "melhoria"
    )
    return (
        (not is_melhoria and row.get("Risco Zumbi") == "Sim")
        or row.get("Regra 24 Dias") == "Sim"
        or (row.get("FRT OK") == "Não" and pd.notna(row.get("FRT (horas)")))
        or row.get("Resolução Genérica") == "Sim"
        # Causa Raíz desativada temporariamente — regra de aplicação em definição
    )


def _calcular_metricas_mes(df_tickets: pd.DataFrame) -> dict:
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

    return {
        "pct_fora_prazo": pct_fora,
        "meta_mes": meta_mes,
        "baseline": baseline,
        "pct_causa_raiz": pct_causa,
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

    titulo = f"M&eacute;tricas do M&ecirc;s &mdash; {_esc(m['mes_nome'])}"
    return (
        f"<div class='ms'><div class='ms-t'>{titulo}</div><div class='ms-g'>"
        f"{_card('Fora do Prazo', v1, m1, s1)}"
        f"{_card('Margem Dispon&iacute;vel', v2, m2, s2)}"
        f"{_card('Causa Ra&iacute;z', v3, m3, s3)}"
        f"</div></div>"
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


def gerar_html_report(
    df_audit: pd.DataFrame,
    df_tickets: pd.DataFrame,
    df_textos_raw: pd.DataFrame,
) -> str:
    hoje = pd.Timestamp.now().normalize()
    data_str = hoje.strftime("%d/%m/%Y")

    logo_html = ""
    if _LOGO_PATH.exists():
        b64 = base64.b64encode(_LOGO_PATH.read_bytes()).decode()
        logo_html = f"<div class='lb'><img src='data:image/png;base64,{b64}' alt='UniATEND'></div>"

    m = _calcular_metricas_mes(df_tickets)
    html_met = _html_metricas(m)
    html_dev = _html_desvios(_calcular_desvios_sla(df_tickets), m["mes_nome"])

    df_hist = consolidar_historico(df_textos_raw)
    hist_idx = df_hist.set_index("id_ticket")["historico"].to_dict()

    df_tk = df_tickets.copy()
    df_tk["ID"] = df_tk["ID"].astype(str).str.strip()
    tk_idx = df_tk.set_index("ID").to_dict("index")

    # Apenas tickets em aberto — concluídos são histórico, não requerem ação do líder
    df_flag = df_audit[
        df_audit.apply(_tem_flag, axis=1)
        & ~df_audit["Status"].str.strip().str.lower().str.contains("conclu", na=False)
    ].copy()

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
        tickets_html = []
        for _, row in grupo.sort_values("ID").iterrows():
            tid = str(row["ID"])
            tk = tk_idx.get(tid, {})

            titulo_raw = str(tk.get("Título", "") or "").strip()
            header = (
                f"#{tid} &mdash; {_esc(titulo_raw)}"
                if titulo_raw and titulo_raw != "nan"
                else f"#{tid}"
            )

            tipo = str(tk.get("Tipo", "") or "").strip()
            tipo_str = _esc(tipo) if tipo and tipo != "nan" else ""

            cat = str(row.get("Categoria", "")).strip()
            sub = str(tk.get("Subcategoria", "") or "").strip()
            cat_str = (
                f"{_esc(cat)} &rsaquo; {_esc(sub)}"
                if sub and sub != "nan"
                else _esc(cat)
            )
            status = _esc(str(row.get("Status", "")).strip())
            data_ab = tk.get("Data Abertura")
            dias_ab = _dias_desde(data_ab)
            try:
                data_fmt = pd.to_datetime(data_ab, dayfirst=True, errors="coerce").strftime("%d/%m/%Y")
                ab_str = f"Aberto em {data_fmt} ({dias_ab} dias)" if dias_ab is not None else f"Aberto em {data_fmt}"
            except Exception:
                ab_str = f"Aberto h&aacute; {dias_ab} dias" if dias_ab is not None else ""
            meta = "&nbsp;&nbsp;|&nbsp;&nbsp;".join(
                p for p in [tipo_str, cat_str, status, ab_str] if p
            )

            flags = _flags_do_ticket(row, tk, hist_idx.get(tid, []))
            flags_html = "".join(
                f'<span class="f {f["cls"]}">{_esc(f["txt"])}</span>' for f in flags
            )

            ultima = _ultima_msg_tecnico(hist_idx.get(tid, []))
            msg_html = (
                f'<div class="um">&ldquo;{_esc(ultima)}&rdquo;</div>'
                if ultima else ""
            )

            tickets_html.append(
                f'<div class="tk">'
                f'<div class="ti">{header}</div>'
                f'<div class="tm">{meta}</div>'
                f'<div>{flags_html}</div>'
                f'{msg_html}'
                f'</div>'
            )

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
