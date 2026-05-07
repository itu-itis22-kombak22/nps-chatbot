"""
Data access layer.

USE_DB=false reads local parquet/CSV files for development.
USE_DB=true reads the raw NPS table from Oracle.
"""

from __future__ import annotations

import os
import unicodedata
from functools import lru_cache
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

USE_DB = os.getenv("USE_DB", "false").lower() == "true"
RAW_PARQUET = Path("data/raw/nps_mock_200k.parquet")
SUMMARY_DIR = Path("data/processed/ozet_tablolari")
OZETLER_CSV = Path("offline_hazirlik/nps_ozetler.csv")

ORACLE_HOST = os.getenv("ORACLE_HOST", "")
ORACLE_PORT = os.getenv("ORACLE_PORT", "1521")
ORACLE_SERVICE = os.getenv("ORACLE_SERVICE", "")
ORACLE_USER = os.getenv("ORACLE_USER", "")
ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "")
ORACLE_TABLE = os.getenv("ORACLE_NPS_TABLE", "")


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).casefold().replace("ı", "i")
    text = "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )
    return text


def _period_key(period: str | None) -> str | None:
    norm = _normalize_text(period)
    if "hafta" in norm:
        return "weekly"
    if "ay" in norm:
        return "monthly"
    if "gun" in norm:
        return "daily"
    return None


def _get_oracle_connection():
    try:
        import oracledb
    except ImportError as exc:
        raise RuntimeError("Oracle baglantisi icin: pip install oracledb") from exc

    dsn = oracledb.makedsn(ORACLE_HOST, ORACLE_PORT, service_name=ORACLE_SERVICE)
    return oracledb.connect(user=ORACLE_USER, password=ORACLE_PASSWORD, dsn=dsn)


def _query_oracle(sql: str) -> pd.DataFrame:
    conn = _get_oracle_connection()
    try:
        df = pd.read_sql(sql, conn)
        df.columns = [c.upper() for c in df.columns]
        return df
    finally:
        conn.close()


@lru_cache(maxsize=1)
def _load_raw_parquet() -> pd.DataFrame:
    df = pd.read_parquet(RAW_PARQUET)
    df["INPUT_AS_OF_DATE"] = pd.to_datetime(df["INPUT_AS_OF_DATE"])
    return df


@lru_cache(maxsize=8)
def _load_summary(name: str) -> pd.DataFrame:
    return pd.read_parquet(SUMMARY_DIR / f"{name}.parquet")


@lru_cache(maxsize=1)
def _load_ozetler() -> pd.DataFrame:
    df = pd.read_csv(OZETLER_CSV, encoding="utf-8-sig")
    rename_map = {
        "Ozet Cesidi": "OZET_CESIDI",
        "Ozet": "OZET",
        "Tarih": "TARIH",
        "Özet Çeşidi": "OZET_CESIDI",
        "Özet": "OZET",
        "Ã–zet Ã‡eÅŸidi": "OZET_CESIDI",
        "Ã–zet": "OZET",
    }
    return df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})


def get_raw(
    period: str | None = None,
    category: str | None = None,
    segment: str | None = None,
    emotion: str | None = None,
    comment_type: str | None = None,
    nps_min: int | None = None,
    nps_max: int | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
) -> pd.DataFrame:
    """Return raw NPS rows with optional filters."""

    if USE_DB:
        return _load_raw_oracle(
            period, category, segment, emotion, comment_type,
            nps_min, nps_max, date_start, date_end,
        )

    df = _load_raw_parquet().copy()
    return _apply_filters(
        df, period, category, segment, emotion, comment_type,
        nps_min, nps_max, date_start, date_end,
    )


def get_summary_table(name: str) -> pd.DataFrame:
    """
    name: gunluk_top_konular | haftalik_trend | aylik_trend |
          segment_dagilim | duygu_kategori_kirilim
    """
    return _load_summary(name)


def get_ozetler(ozet_cesidi: str | None = None, tarih: str | None = None) -> pd.DataFrame:
    """Return prepared text summaries from offline_hazirlik/nps_ozetler.csv."""
    df = _load_ozetler()
    if ozet_cesidi and "OZET_CESIDI" in df.columns:
        df = df[df["OZET_CESIDI"] == ozet_cesidi]
    if tarih and "TARIH" in df.columns:
        df = df[df["TARIH"] >= tarih]
    if "TARIH" in df.columns:
        return df.sort_values("TARIH", ascending=False)
    return df


def _load_raw_oracle(
    period, category, segment, emotion, comment_type,
    nps_min, nps_max, date_start, date_end,
) -> pd.DataFrame:
    conditions = ["1=1"]

    if date_start:
        conditions.append(f"INPUT_AS_OF_DATE >= DATE '{date_start}'")
    if date_end:
        conditions.append(f"INPUT_AS_OF_DATE < DATE '{date_end}' + 1")

    period_key = _period_key(period)
    if not date_start and not date_end and period_key == "weekly":
        conditions.append("INPUT_AS_OF_DATE >= SYSDATE - 7")
    elif not date_start and not date_end and period_key == "monthly":
        conditions.append("INPUT_AS_OF_DATE >= SYSDATE - 30")
    elif not date_start and not date_end and period_key == "daily":
        conditions.append("INPUT_AS_OF_DATE >= SYSDATE - 1")

    if category:
        conditions.append(f"UPPER(FIRST_MAIN_CATEGORY) = UPPER('{category}')")
    if emotion:
        conditions.append(f"UPPER(EMOTION) = UPPER('{emotion}')")
    if comment_type:
        conditions.append(f"UPPER(COMMENT_TYPE) = UPPER('{comment_type}')")
    if nps_min is not None:
        conditions.append(f"NPS_SCORE >= {int(nps_min)}")
    if nps_max is not None:
        conditions.append(f"NPS_SCORE <= {int(nps_max)}")

    if segment == "Detractor":
        conditions.append("NPS_SCORE <= 6")
    elif segment == "Passive":
        conditions.append("NPS_SCORE BETWEEN 7 AND 8")
    elif segment == "Promoter":
        conditions.append("NPS_SCORE >= 9")

    where = " AND ".join(conditions)
    sql = f"SELECT * FROM {ORACLE_TABLE} WHERE {where}"

    df = _query_oracle(sql)
    df["INPUT_AS_OF_DATE"] = pd.to_datetime(df["INPUT_AS_OF_DATE"])
    return df


def _apply_filters(
    df, period, category, segment, emotion, comment_type,
    nps_min, nps_max, date_start, date_end,
):
    if date_start:
        df = df[df["INPUT_AS_OF_DATE"] >= pd.to_datetime(date_start)]
    if date_end:
        end = pd.to_datetime(date_end) + pd.Timedelta(days=1)
        df = df[df["INPUT_AS_OF_DATE"] < end]

    period_key = _period_key(period)
    if not date_start and not date_end and period_key == "weekly":
        cutoff = df["INPUT_AS_OF_DATE"].max() - pd.Timedelta(weeks=1)
        df = df[df["INPUT_AS_OF_DATE"] >= cutoff]
    elif not date_start and not date_end and period_key == "monthly":
        cutoff = df["INPUT_AS_OF_DATE"].max() - pd.Timedelta(days=30)
        df = df[df["INPUT_AS_OF_DATE"] >= cutoff]
    elif not date_start and not date_end and period_key == "daily":
        cutoff = df["INPUT_AS_OF_DATE"].max() - pd.Timedelta(days=1)
        df = df[df["INPUT_AS_OF_DATE"] >= cutoff]

    if category:
        df = df[df["FIRST_MAIN_CATEGORY"].str.casefold() == str(category).casefold()]
    if segment:
        seg_map = {"Detractor": (0, 6), "Passive": (7, 8), "Promoter": (9, 10)}
        if segment in seg_map:
            lo, hi = seg_map[segment]
            df = df[(df["NPS_SCORE"] >= lo) & (df["NPS_SCORE"] <= hi)]
    if emotion:
        df = df[df["EMOTION"].str.casefold() == str(emotion).casefold()]
    if comment_type:
        df = df[df["COMMENT_TYPE"].str.casefold() == str(comment_type).casefold()]
    if nps_min is not None:
        df = df[df["NPS_SCORE"] >= int(nps_min)]
    if nps_max is not None:
        df = df[df["NPS_SCORE"] <= int(nps_max)]

    return df
