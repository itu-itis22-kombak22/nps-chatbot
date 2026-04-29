"""
Veri erişim katmanı.

Hem Parquet dosyalarından (geliştirme) hem Oracle DB'den (prod) okur.
Geçiş env değişkeni ile yönetilir: USE_DB=true

Oracle bağlantısı aktif değilse otomatik olarak Parquet'e düşer.
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
OZETLER_CSV = Path("offline_hazirlik/nps_ozetler.csv")   # offline katman


# ──────────────────────────────────────────────────────────────────────────────
# Parquet loader (geliştirme)
# ──────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_raw() -> pd.DataFrame:
    df = pd.read_parquet(RAW_PARQUET)
    df["INPUT_AS_OF_DATE"] = pd.to_datetime(df["INPUT_AS_OF_DATE"])
    return df


@lru_cache(maxsize=8)
def _load_summary(name: str) -> pd.DataFrame:
    return pd.read_parquet(SUMMARY_DIR / f"{name}.parquet")


@lru_cache(maxsize=1)
def _load_ozetler() -> pd.DataFrame:
    df = pd.read_csv(OZETLER_CSV, encoding="utf-8-sig")
    # Sütun adları: "Özet Çeşidi", "Tarih", "Özet"
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
    """Ham NPS verisini filtreli döndürür."""
    df = _load_raw().copy()

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


def get_summary_table(name: str) -> pd.DataFrame:
    """
    name: gunluk_top_konular | haftalik_trend | aylik_trend |
          segment_dagilim | duygu_kategori_kirilim
    """
    return _load_summary(name)


def get_ozetler(ozet_cesidi: str | None = None, tarih: str | None = None) -> pd.DataFrame:
    """
    nps_ozetler tablosundan filtreli özet döndürür.
    ozet_cesidi: 'Haftalık Konu Özeti' | 'Aylık Konu Özeti' | 'Günlük Negatif Özet' | ...
    """
    df = _load_ozetler()
    if ozet_cesidi:
        df = df[df["OZET_CESIDI"] == ozet_cesidi]
    if tarih:
        df = df[df["TARIH"] >= tarih]
    return df.sort_values("TARIH", ascending=False)
