"""
Pipeline de classificação de tickets UniATEND.
Uso: python app.py
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from auditor import (
    auditar, auditar_conformidade_mensal,
    gerar_html_report, gerar_html_report_conformidade, gerar_html_report_individual,
)
from classifier import classificar, classificar_causa_raiz
from data_utils import carregar_tickets, carregar_textos, preparar_textos
from mailer import enviar_report, enviar_report_conformidade, enviar_reports_individuais
from sla_engine import avaliar_sla, converter_tempo_para_horas

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_BASE = Path(__file__).parent
OUTPUT_PATH = _BASE.parent / "relatorio_dashboard" / "relatorio_classificado.xlsx"
AUDIT_PATH  = _BASE.parent / "relatorio_dashboard" / "relatorio_auditoria.xlsx"

_COLUNAS_FINAIS = [
    "ID", "Data Abertura", "Última Atualização", "Status", "Módulo", "Categoria", "Subcategoria",
    "Responsável",
    "SLA Piso", "SLA Teto", "% Consumo SLA", "Status SLA", "Tempo Gasto",
    "Causa Raíz", "Caminho", "Tipo", "Título", "Prioridade", "Tempo Gasto (Horas)", "Link ClickUp",
]


def _montar_base() -> pd.DataFrame:
    tickets = carregar_tickets()
    textos  = preparar_textos(carregar_textos())

    tickets.columns = tickets.columns.str.strip().str.lower()
    tickets["id_ticket"] = tickets["id_ticket"].astype(str).str.strip()

    if "modulo" not in tickets.columns:
        logger.warning("Coluna 'modulo' ausente. Preenchendo com 'Desconhecido'.")
        tickets["modulo"] = "Desconhecido"
    else:
        tickets["modulo"] = tickets["modulo"].astype(str).str.strip()

    base = tickets.merge(textos, on="id_ticket", how="left")
    base["texto"] = base["texto"].fillna("")
    base.rename(columns={
        "id_ticket":    "ID",
        "data_abertura": "Data Abertura",
        "status":       "Status",
        "modulo":       "Módulo",
        "caminho":      "Caminho",
        "tipo":         "Tipo",
        "prioridade":    "Prioridade",
        "tempo_gasto":   "Tempo Gasto",
        "responsavel":       "Responsável",
        "responsável":       "Responsável",
        "última_atualização": "Última Atualização",
        "ultima_atualizacao": "Última Atualização",
        "link_url":           "Link ClickUp",
    }, inplace=True)
    return base


def _classificar_tudo(df_base: pd.DataFrame) -> pd.DataFrame:
    df = df_base.copy()
    df[["Categoria", "Subcategoria"]] = df.apply(
        lambda r: pd.Series(classificar(r["texto"], r["Módulo"])), axis=1
    )
    df["Causa Raíz"] = ""
    df["Título"] = ""
    return df


def _aplicar_incremental(df_base: pd.DataFrame) -> pd.DataFrame:
    if not OUTPUT_PATH.exists():
        return _classificar_tudo(df_base)

    try:
        df_existente = pd.read_excel(OUTPUT_PATH)
        df_existente["ID"] = df_existente["ID"].astype(str).str.strip()

        colunas_manuais = ["ID"] + [
            c for c in ["Módulo", "Categoria", "Subcategoria", "Causa Raíz", "Título",
                        "SLA Piso", "SLA Teto", "% Consumo SLA", "Status SLA"]
            if c in df_existente.columns
        ]
        df_manuais = df_existente[colunas_manuais]

        df_historico_ausente = df_existente[~df_existente["ID"].isin(df_base["ID"])].copy()

        df = df_base.merge(df_manuais, on="ID", how="left", suffixes=("_orig", "_man"))

        if "Módulo_man" in df.columns:
            df["Módulo"] = df["Módulo_man"].fillna(df["Módulo_orig"])
            df.drop(columns=["Módulo_orig", "Módulo_man"], inplace=True)
        elif "Módulo_orig" in df.columns:
            df.rename(columns={"Módulo_orig": "Módulo"}, inplace=True)

        mask_novos = df["Categoria"].isna()
        if mask_novos.any():
            df.loc[mask_novos, ["Categoria", "Subcategoria"]] = (
                df[mask_novos]
                .apply(lambda r: pd.Series(classificar(r["texto"], r["Módulo"])), axis=1)
                .values
            )
            for col in ("Causa Raíz", "Título"):
                if col in df.columns:
                    df[col] = df[col].astype(object)
                    df.loc[mask_novos, col] = ""

        return pd.concat([df_historico_ausente, df], ignore_index=True)

    except Exception as exc:
        logger.warning("Erro no processamento incremental (%s). Gerando do zero.", exc)
        return _classificar_tudo(df_base)


def _aplicar_causa_raiz(df: pd.DataFrame, df_textos_raw: pd.DataFrame) -> pd.DataFrame:
    from text_cleaner import consolidar_historico
    df_hist = consolidar_historico(df_textos_raw)
    hist_idx = df_hist.set_index("id_ticket")["historico"].to_dict()

    for idx, row in df.iterrows():
        if str(row.get("Causa Raíz", "")).strip() not in ("", "nan"):
            continue
        historico = hist_idx.get(str(row["ID"]), [])
        msgs_tecnico = [h for h in historico if h["papel"] == "tecnico"]
        causa = classificar_causa_raiz(msgs_tecnico)
        if causa:
            df.at[idx, "Causa Raíz"] = causa

    return df


def _aplicar_sla(df: pd.DataFrame) -> pd.DataFrame:
    for col in ("SLA Piso", "SLA Teto", "% Consumo SLA", "Status SLA"):
        if col not in df.columns:
            df[col] = np.nan
    # Garante object dtype para evitar conflito com backend ArrowStringArray (pandas 2.x+)
    df["Status SLA"] = df["Status SLA"].astype(object)

    df["Tempo Gasto (Horas)"] = df["Tempo Gasto"].apply(converter_tempo_para_horas)

    engine = df.apply(
        lambda r: avaliar_sla(r["Módulo"], r["Categoria"], r["Subcategoria"], r["Tempo Gasto (Horas)"]),
        axis=1,
    )
    df[["_Eng_Status", "_Eng_Piso", "_Eng_Teto", "_Eng_Consumo", "_Tem_Regra"]] = engine

    mask_com_regra = df["_Tem_Regra"] == True
    df.loc[mask_com_regra, "Status SLA"]     = df.loc[mask_com_regra, "_Eng_Status"].astype(object)
    df.loc[mask_com_regra, "SLA Piso"]       = df.loc[mask_com_regra, "_Eng_Piso"]
    df.loc[mask_com_regra, "SLA Teto"]       = df.loc[mask_com_regra, "_Eng_Teto"]
    df.loc[mask_com_regra, "% Consumo SLA"]  = df.loc[mask_com_regra, "_Eng_Consumo"]

    mask_sem_hist = (~mask_com_regra) & df["SLA Piso"].isna()
    df.loc[mask_sem_hist, "Status SLA"] = "SLA Não Definido"

    if "Tipo" in df.columns:
        mask_tipo_melhoria = df["Tipo"].str.strip().str.lower() == "melhoria"
        df.loc[mask_tipo_melhoria, "Status SLA"] = "Prazo Não Aplicável"
        df.loc[mask_tipo_melhoria, ["SLA Piso", "SLA Teto", "% Consumo SLA"]] = np.nan

    return df.drop(columns=["_Eng_Status", "_Eng_Piso", "_Eng_Teto", "_Eng_Consumo", "_Tem_Regra"])


ENVIO_EMAIL_ATIVO = True


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pipeline UniATEND")
    p.add_argument(
        "--auditoria-mensal",
        action="store_true",
        help="Gera relatório de conformidade mensal (tickets concluídos no mês)",
    )
    p.add_argument(
        "--mes",
        default=None,
        metavar="AAAA-MM",
        help="Mês de referência para a auditoria mensal (ex: 2026-05). Padrão: mês atual.",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    logger.info("Iniciando pipeline de classificação...")

    df_textos_raw = carregar_textos()

    df_base = _montar_base()
    df = _aplicar_incremental(df_base)
    df = _aplicar_causa_raiz(df, df_textos_raw)
    df = _aplicar_sla(df)

    if "Status" in df.columns:
        df = df[df["Status"].str.strip().str.lower() != "cancelado"]
    if "Categoria" in df.columns:
        df = df[df["Categoria"].str.lower().str.strip() != "teste de funcionalidade"]

    colunas_presentes = [c for c in _COLUNAS_FINAIS if c in df.columns]
    df_final = df[colunas_presentes].drop_duplicates(subset=["ID"], keep="last")
    df_final.to_excel(OUTPUT_PATH, index=False)
    logger.info("Pipeline concluído. %d tickets exportados para %s", len(df_final), OUTPUT_PATH)

    df_audit = auditar(df_final, df_textos_raw)
    df_audit.to_excel(AUDIT_PATH, index=False)
    logger.info("Auditoria concluída. %d tickets auditados para %s", len(df_audit), AUDIT_PATH)

    data_str = pd.Timestamp.now().strftime("%d/%m/%Y")

    if ENVIO_EMAIL_ATIVO:
        try:
            html_body = gerar_html_report(df_audit, df_final, df_textos_raw)
            enviar_report(html_body, data_str)
            logger.info("Report de auditoria enviado por e-mail.")
        except Exception as exc:
            logger.warning("Falha no envio do e-mail: %s", exc)

        try:
            responsaveis = df_audit["Responsável"].dropna().unique().tolist()
            reports_individuais = {
                resp: gerar_html_report_individual(df_audit, df_final, df_textos_raw, resp)
                for resp in responsaveis
            }
            enviar_reports_individuais(reports_individuais, data_str)
            logger.info("Reports individuais enviados para %d responsáveis.", len(reports_individuais))
        except Exception as exc:
            logger.warning("Falha no envio dos reports individuais: %s", exc)
    else:
        logger.info("Envio de e-mail desativado (ENVIO_EMAIL_ATIVO = False).")

    if args.auditoria_mensal:
        mes_ref = None
        if args.mes:
            try:
                mes_ref = pd.Timestamp(args.mes + "-01")
            except Exception:
                logger.error("Formato inválido para --mes: use AAAA-MM (ex: 2026-05)")
                return
        ref_ts = mes_ref or pd.Timestamp.now()
        mes_str = ref_ts.strftime("%Y_%m")
        mes_exib = ref_ts.strftime("%Y/%m")
        conf_path = _BASE.parent / "relatorio_dashboard" / f"relatorio_conformidade_{mes_str}.xlsx"
        df_conf, pct, n_total, n_conforme = auditar_conformidade_mensal(df_audit, mes_ref=mes_ref)
        if pct is not None:
            df_conf.to_excel(conf_path, index=False)
            logger.info(
                "Conformidade %s: %.1f%% (%d/%d conformes). Salvo em %s",
                mes_exib, pct * 100, n_conforme, n_total, conf_path,
            )
            if ENVIO_EMAIL_ATIVO:
                try:
                    html_conf = gerar_html_report_conformidade(df_conf, pct, n_total, n_conforme, df_final, df_textos_raw, df_audit, mes_ref=mes_ref)
                    enviar_report_conformidade(html_conf, mes_exib)
                    logger.info("Report de conformidade mensal enviado por e-mail.")
                except Exception as exc:
                    logger.warning("Falha no envio do report de conformidade: %s", exc)
            else:
                logger.info("Envio de e-mail desativado (ENVIO_EMAIL_ATIVO = False).")
        else:
            logger.info("Auditoria mensal: sem tickets concluídos em %s.", mes_exib)


if __name__ == "__main__":
    main()
