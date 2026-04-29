"""
200.000 satırlık mock NPS verisi üretici.

Çalıştır:
    python etl/generate_mock_data.py

Çıktı:
    data/raw/nps_mock_200k.parquet   (hızlı okuma için)
    data/raw/nps_mock_200k.csv       (DBeaver import için)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import random
import hashlib
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
from tqdm import tqdm

from config.constants import SUBMAP, ALLOWED, COMMENT_TYPES, MAIN_CATEGORIES
from etl.templates import TEMPLATES

# ──────────────────────────────────────────────────────────────────────────────
# Parametreler
# ──────────────────────────────────────────────────────────────────────────────
N_ROWS        = 200_000
START_DATE    = datetime(2024, 1, 1)
END_DATE      = datetime(2025, 12, 31)
RANDOM_SEED   = 42

# NPS dağılımı: gerçek banka dağılımına yakın
# Detractor (0-6) ~%40, Passive (7-8) ~%30, Promoter (9-10) ~%30
NPS_WEIGHTS = [3, 3, 4, 5, 5, 10, 10, 15, 15, 17, 13]  # 0-10 için ağırlıklar

# Yorum tipi dağılımı
COMMENT_TYPE_WEIGHTS = {
    "Şikayet":       0.35,
    "Memnuniyet":    0.40,
    "Talep/Öneri":   0.18,
    "Veri Yetersiz": 0.07,
}

# NPS skoruna göre yorum tipi yönlendirme
# Düşük NPS → daha fazla şikayet, yüksek NPS → daha fazla memnuniyet
NPS_COMMENT_TYPE_BIAS = {
    # (nps_range): {type: multiplier}
    "low":    {"Şikayet": 2.5, "Memnuniyet": 0.2, "Talep/Öneri": 1.2, "Veri Yetersiz": 0.8},   # 0-4
    "mid":    {"Şikayet": 1.0, "Memnuniyet": 0.6, "Talep/Öneri": 1.5, "Veri Yetersiz": 1.0},   # 5-7
    "high":   {"Şikayet": 0.1, "Memnuniyet": 2.8, "Talep/Öneri": 0.9, "Veri Yetersiz": 0.8},   # 8-10
}

# ──────────────────────────────────────────────────────────────────────────────
# Yardımcı fonksiyonlar
# ──────────────────────────────────────────────────────────────────────────────
rng = random.Random(RANDOM_SEED)
np_rng = np.random.default_rng(RANDOM_SEED)


def random_date(start: datetime, end: datetime) -> datetime:
    delta = int((end - start).total_seconds())
    return start + timedelta(seconds=rng.randint(0, delta))


def nps_to_band(score: int) -> str:
    if score <= 4:
        return "low"
    if score <= 7:
        return "mid"
    return "high"


def pick_comment_type(nps_score: int) -> str:
    band = nps_to_band(nps_score)
    bias = NPS_COMMENT_TYPE_BIAS[band]
    types  = list(COMMENT_TYPE_WEIGHTS.keys())
    weights = [COMMENT_TYPE_WEIGHTS[t] * bias[t] for t in types]
    total = sum(weights)
    weights = [w / total for w in weights]
    return rng.choices(types, weights=weights, k=1)[0]


def pick_emotion(comment_type: str) -> str:
    return rng.choice(ALLOWED[comment_type])


def pick_categories():
    """Ana kategori ve birinci alt kategori (zorunlu), ikinci kategori (opsiyonel)."""
    main1 = rng.choice(MAIN_CATEGORIES)
    subs1 = SUBMAP[main1]
    sub1  = rng.choice(subs1) if subs1 else None

    # %25 ihtimalle ikinci kategori de dolu
    if rng.random() < 0.25:
        main2 = rng.choice([c for c in MAIN_CATEGORIES if c != main1])
        subs2 = SUBMAP[main2]
        sub2  = rng.choice(subs2) if subs2 else None
    else:
        main2, sub2 = None, None

    return main1, sub1, main2, sub2


def build_text(comment_type: str, emotion: str, main_cat: str, sub_cat: str) -> str:
    key = (comment_type, emotion)
    pool = TEMPLATES.get(key)
    if not pool:
        # Fallback: generic
        pool = TEMPLATES.get((comment_type, "Veri Yetersiz"), ["Yorum yok."])
    template = rng.choice(pool)
    sub_cat_str = sub_cat if sub_cat else main_cat
    text = template.replace("{kategori}", main_cat).replace("{alt_kategori}", sub_cat_str)
    return text


def make_session_id(idx: int) -> int:
    """Gerçekçi görünen 8 haneli session ID."""
    return 10_000_000 + idx * 7 + rng.randint(0, 6)


# ──────────────────────────────────────────────────────────────────────────────
# Ana üretim döngüsü
# ──────────────────────────────────────────────────────────────────────────────
def generate(n: int = N_ROWS) -> pd.DataFrame:
    print(f"[*] {n:,} satır mock NPS verisi üretiliyor…")
    rows = []

    nps_scores = rng.choices(range(11), weights=NPS_WEIGHTS, k=n)

    for i in tqdm(range(n), unit="row", ncols=80):
        nps = nps_scores[i]
        comment_type    = pick_comment_type(nps)
        emotion         = pick_emotion(comment_type)
        main1, sub1, main2, sub2 = pick_categories()
        text            = build_text(comment_type, emotion, main1, sub1)
        input_date      = random_date(START_DATE, END_DATE)
        result_date     = input_date + timedelta(hours=rng.randint(0, 48))
        load_date       = result_date

        rows.append({
            "SESSION_ID":            make_session_id(i),
            "NPS_SCORE":             nps,
            "TEXT":                  text,
            "INPUT_AS_OF_DATE":      input_date,
            "RESULT_AS_OF_DATE":     result_date,
            "FIRST_MAIN_CATEGORY":   main1,
            "FIRST_SUBCATEGORY":     sub1,
            "SECOND_MAIN_CATEGORY":  main2,
            "SECOND_SUBCATEGORY":    sub2,
            "COMMENT_TYPE":          comment_type,
            "EMOTION":               emotion,
            "LOAD_DATE":             load_date,
        })

    df = pd.DataFrame(rows)
    print(f"[✓] Üretim tamamlandı: {len(df):,} satır")
    return df


def save(df: pd.DataFrame):
    os.makedirs("data/raw", exist_ok=True)
    parquet_path = "data/raw/nps_mock_200k.parquet"
    csv_path     = "data/raw/nps_mock_200k.csv"

    df.to_parquet(parquet_path, index=False)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")  # utf-8-sig → Excel/DBeaver uyumu

    print(f"[✓] Parquet → {parquet_path}  ({os.path.getsize(parquet_path)/1e6:.1f} MB)")
    print(f"[✓] CSV     → {csv_path}  ({os.path.getsize(csv_path)/1e6:.1f} MB)")


def print_stats(df: pd.DataFrame):
    print("\n── NPS Dağılımı ──────────────────────────────────")
    print(df["NPS_SCORE"].value_counts().sort_index())
    print("\n── Yorum Tipi ────────────────────────────────────")
    print(df["COMMENT_TYPE"].value_counts())
    print("\n── Duygu Durumu ──────────────────────────────────")
    print(df["EMOTION"].value_counts())
    print("\n── Top-5 Ana Kategori ────────────────────────────")
    print(df["FIRST_MAIN_CATEGORY"].value_counts().head())


if __name__ == "__main__":
    df = generate()
    save(df)
    print_stats(df)
