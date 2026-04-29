"""
Veri erişim katmanı.

USE_DB=false → Parquet/CSV dosyalarından okur (geliştirme/test)
USE_DB=true  → Oracle DB'den okur (production)

Oracle parametreleri .env dosyasından okunur:
    ORACLE_HOST, ORACLE_PORT, ORACLE_SERVICE
    ORACLE_USER, ORACLE_PASSWORD
    ORACLE_NPS_TABLE  → ham NPS verisi tablosu
"""

import os
from pathlib import Path
from functools import lru_cache

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

USE_DB      = os.getenv("USE_DB", "false").lower() == "true"
RAW_PARQUET = Path("data/raw/nps_mock_200k.parquet")
SUMMARY_DIR = Path("data/processed/ozet_tablolari")
OZETLER_CSV = Path("offline_hazirlik/nps_ozetler.csv")

# Oracle parametreleri
ORACLE_HOST    = os.getenv("ORACLE_HOST", "")
ORACLE_PORT    = os.getenv("ORACLE_PORT", "1521")
ORACLE_SERVICE = os.getenv("ORACLE_SERVICE", "")
ORACLE_USER    = os.getenv("ORACLE_USER", "")
ORACLE_PASSWORD= os.getenv("ORACLE_PASSWORD", "")
ORACLE_TABLE   = os.getenv("ORACLE_NPS_TABLE", "")


# ──────────────────────────────────────────────────────────────────────────────
# Oracle bağlantısı
# ──────────────────────────────────────────────────────────────────────────────

def _get_oracle_connection():
    """
    python-oracledb ile bağlantı döndürür.
    Kur: pip install oracledb
    """
    try:
        import oracledb
        dsn = f"{ORACLE_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE}"
        return oracledb.connect(user=ORACLE_USER, password=ORACLE_PASSWORD, dsn=dsn)
    except ImportError:
        raise RuntimeError("Oracle bağlantısı için: pip install oracledb")


def _query_oracle(sql: str) -> pd.DataFrame:
    conn = _get_oracle_connection()
    try:
        df = pd.read_sql(sql, conn)
        df.columns = [c.upper() for c in df.columns]
        return df
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# Parquet loader (geliştirme)
# ──────────────────────────────────────────────────────────────────────────────

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
    df = df.rename(columns={"Özet Çeşidi": "OZET_CESIDI", "Tarih": "TARIH", "Özet": "OZET"})
    return df


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def get_raw(
    period: str | None = None,
    category: str | None = None,
    segment: str | None = None,
    emotion: str | None = None,
    comment_type: str | None = None,
    nps_min: int | None = None,
    nps_max: int | None = None,
) -> pd.DataFrame:
    """Ham NPS verisini filtreli döndürür. USE_DB=true ise Oracle'dan okur."""

    if USE_DB:
        df = _load_raw_oracle(period, category, segment, emotion, comment_type, nps_min, nps_max)
    else:
        df = _load_raw_parquet().copy()
        df = _apply_filters(df, period, category, segment, emotion, comment_type, nps_min, nps_max)

    return df


def get_summary_table(name: str) -> pd.DataFrame:
    """
    name: gunluk_top_konular | haftalik_trend | aylik_trend |
          segment_dagilim | duygu_kategori_kirilim
    """
    return _load_summary(name)


def get_ozetler(ozet_cesidi: str | None = None, tarih: str | None = None) -> pd.DataFrame:
    """offline_hazirlik/nps_ozetler.csv'den filtreli özet döndürür."""
    df = _load_ozetler()
    if ozet_cesidi:
        df = df[df["OZET_CESIDI"] == ozet_cesidi]
    if tarih:
        df = df[df["TARIH"] >= tarih]
    return df.sort_values("TARIH", ascending=False)


# ──────────────────────────────────────────────────────────────────────────────
# Oracle okuma (USE_DB=true)
# ──────────────────────────────────────────────────────────────────────────────

def _load_raw_oracle(period, category, segment, emotion, comment_type, nps_min, nps_max) -> pd.DataFrame:
    """Filtreleri WHERE clause'a çevirip Oracle'dan çeker."""
    conditions = ["1=1"]

    if period == "haftalık":
        conditions.append("INPUT_AS_OF_DATE >= SYSDATE - 7")
    elif period == "aylık":
        conditions.append("INPUT_AS_OF_DATE >= SYSDATE - 30")
    elif period == "günlük":
        conditions.append("INPUT_AS_OF_DATE >= SYSDATE - 1")

    if category:
        conditions.append(f"UPPER(FIRST_MAIN_CATEGORY) = UPPER('{category}')")
    if emotion:
        conditions.append(f"UPPER(EMOTION) = UPPER('{emotion}')")
    if comment_type:
        conditions.append(f"UPPER(COMMENT_TYPE) = UPPER('{comment_type}')")
    if nps_min is not None:
        conditions.append(f"NPS_SCORE >= {nps_min}")
    if nps_max is not None:
        conditions.append(f"NPS_SCORE <= {nps_max}")

    # Segment → NPS aralığına çevir
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


# ──────────────────────────────────────────────────────────────────────────────
# Filtre yardımcısı (Parquet modu)
# ──────────────────────────────────────────────────────────────────────────────

def _apply_filters(df, period, category, segment, emotion, comment_type, nps_min, nps_max):
    if period == "haftalık":
        cutoff = df["INPUT_AS_OF_DATE"].max() - pd.Timedelta(weeks=1)
        df = df[df["INPUT_AS_OF_DATE"] >= cutoff]
    elif period == "aylık":
        cutoff = df["INPUT_AS_OF_DATE"].max() - pd.Timedelta(days=30)
        df = df[df["INPUT_AS_OF_DATE"] >= cutoff]
    elif period == "günlük":
        cutoff = df["INPUT_AS_OF_DATE"].max() - pd.Timedelta(days=1)
        df = df[df["INPUT_AS_OF_DATE"] >= cutoff]

    if category:
        df = df[df["FIRST_MAIN_CATEGORY"].str.lower() == category.lower()]
    if segment:
        seg_map = {"Detractor": (0, 6), "Passive": (7, 8), "Promoter": (9, 10)}
        if segment in seg_map:
            lo, hi = seg_map[segment]
            df = df[(df["NPS_SCORE"] >= lo) & (df["NPS_SCORE"] <= hi)]
    if emotion:
        df = df[df["EMOTION"].str.lower() == emotion.lower()]
    if comment_type:
        df = df[df["COMMENT_TYPE"].str.lower() == comment_type.lower()]
    if nps_min is not None:
        df = df[df["NPS_SCORE"] >= nps_min]
    if nps_max is not None:
        df = df[df["NPS_SCORE"] <= nps_max]

    return df
