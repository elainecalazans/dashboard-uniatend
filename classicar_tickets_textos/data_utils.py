from __future__ import annotations

import csv
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_BASE = Path(__file__).parent


def _contar_linhas(path: Path) -> int:
    with open(path, encoding="utf-8-sig") as f:
        return sum(1 for _ in f) - 1


def carregar_tickets() -> pd.DataFrame:
    path = _BASE / "tickets.csv"
    try:
        df = pd.read_csv(path, sep=";", encoding="utf-8-sig")
        df.columns = df.columns.str.strip().str.lower()
        if "id_ticket" not in df.columns:
            raise ValueError("Coluna id_ticket ausente")
    except Exception as exc:
        logger.warning("tickets.csv com estrutura inválida (%s). Aplicando fallback.", exc)
        df = pd.read_csv(
            path, sep=",", encoding="utf-8-sig", engine="python",
            quotechar='"', quoting=csv.QUOTE_ALL, on_bad_lines="skip", header=None,
        )
        df = df.iloc[:, :10]
        df.columns = [
            "id_ticket", "data_abertura", "status", "modulo", "caminho",
            "tipo", "responsavel", "prioridade", "ultima_atualizacao", "tempo_gasto",
        ]
        primeira = df.iloc[0].astype(str).str.lower()
        if any("id_ticket" in v for v in primeira):
            df = df.iloc[1:]

    try:
        descartadas = _contar_linhas(path) - len(df)
        if descartadas > 0:
            logger.warning("tickets.csv: %d linha(s) ignorada(s).", descartadas)
    except Exception:
        pass

    return df


def carregar_textos() -> pd.DataFrame:
    path = _BASE / "textos.csv"
    df = pd.read_csv(
        path, sep=",", encoding="utf-8-sig", engine="python",
        quoting=csv.QUOTE_MINIMAL, on_bad_lines="skip",
    )
    df.columns = df.columns.str.strip()

    if "id_ticket" not in df.columns:
        logger.warning("textos.csv com estrutura inválida. Aplicando fallback.")
        df = pd.read_csv(
            path, sep=",", encoding="utf-8-sig", engine="python",
            header=None, quotechar='"', quoting=csv.QUOTE_ALL, on_bad_lines="skip",
        )
        df = df.iloc[:, :4]
        df.columns = ["id_ticket", "nome", "texto", "criado_em"]

    try:
        descartadas = _contar_linhas(path) - len(df)
        if descartadas > 0:
            logger.warning("textos.csv: %d linha(s) ignorada(s).", descartadas)
    except Exception:
        pass

    return df


def preparar_textos(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower()
    df["id_ticket"] = df["id_ticket"].astype(str).str.strip()

    if "texto" not in df.columns:
        return df[["id_ticket"]]

    df["texto"] = df["texto"].replace(r"\n", " ", regex=True)

    coluna_data = "criado_em"
    if coluna_data in df.columns:
        df[coluna_data] = pd.to_datetime(df[coluna_data], format="%m/%d/%y %H:%M", errors="coerce")
        df["texto"] = df["texto"].astype(str).str.strip()

        _excluir = ["alteração de status", "alteracao de status", "ticket atribuído", "ticket atribuido"]

        def _valido(t: str) -> bool:
            tl = t.lower()
            return t not in ("", "nan") and not any(p in tl for p in _excluir)

        df = df[df["texto"].apply(_valido)]
        df = df.sort_values(coluna_data).drop_duplicates(subset=["id_ticket"], keep="first")

    return df[["id_ticket", "texto"]]
