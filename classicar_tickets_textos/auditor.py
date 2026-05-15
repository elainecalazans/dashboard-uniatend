from __future__ import annotations

import re
from html import escape as _esc

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
    return not sem_fechamento or bool(_GENERICA_RE.match(sem_fechamento))


def _regra_24_dias(ultima_atualizacao, categoria: str, status: str) -> str:
    if str(categoria).strip().lower() != "melhorias":
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

        registros.append({
            "ID": ticket_id,
            "Responsável": ticket.get("Responsável", ""),
            "Módulo": ticket.get("Módulo", ""),
            "Categoria": categoria,
            "Status": status,
            "FRT (horas)": round(frt, 1) if frt is not None else None,
            "FRT OK": "Sim" if (frt is not None and frt <= 2.0) else ("Não" if frt is not None else _label_sem_frt(historico)),
            "Gap Máx (dias)": round(max_gap, 1) if max_gap is not None else None,
            "Risco Zumbi": "Sim" if (max_gap is not None and max_gap > 5) else "Não",
            "Regra 24 Dias": _regra_24_dias(ticket.get("Última Atualização"), categoria, status),
            "Resolução Genérica": "Sim" if _resolucao_generica(msgs_tecnico) else "Não",
            "Causa Raíz Preenchida": "Sim" if (causa_raiz not in ("", "nan") and len(causa_raiz) > 3) else "Não",
        })

    return (
        pd.DataFrame(registros)
        .sort_values(["Responsável", "ID"])
        .reset_index(drop=True)
    )


# ── Geração do report HTML ────────────────────────────────────────────────────

_CSS = (
    "body{font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#333;"
    "background:#eef1f6;margin:0;padding:20px}"
    ".w{max-width:700px;margin:0 auto;background:#fff;border-radius:8px;"
    "box-shadow:0 2px 10px rgba(0,0,0,.12);overflow:hidden}"
    ".hd{background:#1e2d5a;color:#fff;padding:18px 24px}"
    ".hd h1{margin:0;font-size:17px;font-weight:700;letter-spacing:.4px}"
    ".hd p{margin:5px 0 0;font-size:12px;color:#94b0e8}"
    ".bd{padding:12px 24px 28px}"
    ".rt{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;"
    "color:#1e2d5a;margin:22px 0 6px;padding-bottom:5px;border-bottom:2px solid #e6eaf0}"
    ".rc{font-weight:normal;text-transform:none;letter-spacing:0;color:#999;font-size:12px}"
    ".tk{border:1px solid #e6eaf0;border-radius:6px;padding:11px 14px;margin:7px 0;"
    "background:#fafbfd}"
    ".ti{font-weight:700;color:#1e2d5a;font-size:13px}"
    ".tm{color:#999;font-size:11px;margin:3px 0 8px}"
    ".f{display:inline-block;padding:2px 9px;border-radius:10px;font-size:11px;"
    "font-weight:600;margin:2px 3px 2px 0}"
    ".fc{background:#fde8e8;color:#c0392b;border:1px solid #e74c3c}"
    ".fa{background:#fff4e5;color:#c07800;border:1px solid #e07b00}"
    ".fl{background:#fffde7;color:#7a6200;border:1px solid #d4ac0d}"
    ".um{background:#f4f6f8;border-left:3px solid #bdc7d3;padding:6px 10px;"
    "font-size:11px;color:#555;margin-top:8px;border-radius:0 4px 4px 0;"
    "font-style:italic;word-break:break-word}"
    ".ft{padding:10px 24px;font-size:11px;color:#bbb;border-top:1px solid #f0f0f0;"
    "text-align:center}"
)


def _ultima_msg_tecnico(historico: list[dict]) -> str:
    for h in reversed(historico):
        if h["papel"] == "tecnico" and h["texto"].strip():
            t = h["texto"].strip()
            return (t[:250] + "…") if len(t) > 250 else t
    return ""


def _dias_desde(ts) -> int | None:
    try:
        return (pd.Timestamp.now().normalize() - pd.Timestamp(ts).normalize()).days
    except Exception:
        return None


def _flags_do_ticket(row: pd.Series, tk: dict) -> list[dict]:
    flags = []
    if row.get("Risco Zumbi") == "Sim":
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
    if row.get("Causa Raíz Preenchida") == "Não":
        flags.append({"cls": "fl", "txt": "Causa raíz não preenchida"})
    return flags


def _tem_flag(row: pd.Series) -> bool:
    return (
        row.get("Risco Zumbi") == "Sim"
        or row.get("Regra 24 Dias") == "Sim"
        or (row.get("FRT OK") == "Não" and pd.notna(row.get("FRT (horas)")))
        or row.get("Resolução Genérica") == "Sim"
        or row.get("Causa Raíz Preenchida") == "Não"
    )


def gerar_html_report(
    df_audit: pd.DataFrame,
    df_tickets: pd.DataFrame,
    df_textos_raw: pd.DataFrame,
) -> str:
    hoje = pd.Timestamp.now().normalize()
    data_str = hoje.strftime("%d/%m/%Y")

    df_hist = consolidar_historico(df_textos_raw)
    hist_idx = df_hist.set_index("id_ticket")["historico"].to_dict()

    df_tk = df_tickets.copy()
    df_tk["ID"] = df_tk["ID"].astype(str).str.strip()
    tk_idx = df_tk.set_index("ID").to_dict("index")

    df_flag = df_audit[df_audit.apply(_tem_flag, axis=1)].copy()

    def _tpl(corpo: str, subtit: str) -> str:
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<style>{_CSS}</style></head><body>"
            "<div class='w'>"
            "<div class='hd'><h1>Auditoria UniATEND</h1>"
            f"<p>{data_str} &nbsp;&middot;&nbsp; {subtit}</p></div>"
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

            cat = str(row.get("Categoria", "")).strip()
            sub = str(tk.get("Subcategoria", "") or "").strip()
            cat_str = (
                f"{_esc(cat)} &rsaquo; {_esc(sub)}"
                if sub and sub != "nan"
                else _esc(cat)
            )
            status = _esc(str(row.get("Status", "")).strip())
            dias_ab = _dias_desde(tk.get("Data Abertura"))
            ab_str = f"Aberto h&aacute; {dias_ab} dias" if dias_ab is not None else ""
            meta = "&nbsp;&nbsp;|&nbsp;&nbsp;".join(
                p for p in [cat_str, status, ab_str] if p
            )

            flags = _flags_do_ticket(row, tk)
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
