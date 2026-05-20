from __future__ import annotations

import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import premailer

_CONFIG_PATH = Path(__file__).parent.parent / "config.json"


def _carregar_env() -> None:
    env = Path(__file__).parent.parent / ".env"
    if not env.exists():
        return
    for linha in env.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        os.environ.setdefault(chave.strip(), valor.strip())


def enviar_report(html_body: str, data_str: str) -> None:
    _carregar_env()

    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    report_to_raw = os.environ.get("REPORT_TO", "andressa.rodrigues@bhub.ai")
    report_to = [addr.strip() for addr in report_to_raw.replace(";", ",").split(",") if addr.strip()]

    if not smtp_user or not smtp_pass:
        raise ValueError("SMTP_USER e SMTP_PASS precisam estar configurados no .env")
    if not report_to:
        raise ValueError("REPORT_TO não contém nenhum endereço válido")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Auditoria UniATEND — {data_str}"
    msg["From"] = smtp_user
    msg["To"] = ", ".join(report_to)
    html_inline = premailer.transform(html_body)
    msg.attach(MIMEText(html_inline, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(smtp_user, smtp_pass)
        smtp.sendmail(smtp_user, report_to, msg.as_string())


def enviar_reports_individuais(reports: dict[str, str], data_str: str) -> None:
    _carregar_env()

    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")

    if not smtp_user or not smtp_pass:
        raise ValueError("SMTP_USER e SMTP_PASS precisam estar configurados no .env")

    try:
        cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        emails_map = cfg.get("emails_responsaveis", {})
    except Exception:
        emails_map = {}

    if not emails_map:
        return

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(smtp_user, smtp_pass)

        for responsavel, html_body in reports.items():
            email = emails_map.get(responsavel, "").strip()
            if not email:
                continue
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"Seu Relatório UniATEND — {data_str}"
            msg["From"]    = smtp_user
            msg["To"]      = email
            msg.attach(MIMEText(premailer.transform(html_body), "html", "utf-8"))
            smtp.sendmail(smtp_user, [email], msg.as_string())
