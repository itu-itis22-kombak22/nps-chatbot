"""
Offline hazırlık modülü.

Ham NPS tablosundan aşağıdaki üç katmanı üretir:

1. ÖZET TABLOLARI  (özet_tabloları/)
   - Günlük top konular
   - Haftalık / Aylık trend
   - Segment bazlı dağılım
   - Duygu / Kategori kırılımı

2. HAZIR METİN ÖZETLERİ  (hazir_ozetler/ + DB tablosu nps_ozetler)
   - Günlük negatif özet
   - Haftalık issue özeti
   → LLM ile üretilir, metin olarak saklanır.

3. VEKTÖR İNDEKSİ  (vector_index/)
   → Gelecek modül (vector_index.py)

Çalıştır:
    python etl/offline_prep.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from config.constants import SUMMARY_TYPES

# ──────────────────────────────────────────────────────────────────────────────
# Yollar
# ──────────────────────────────────────────────────────────────────────────────
RAW_PARQUET   = Path("data/raw/nps_mock_200k.parquet")
SUMMARY_DIR   = Path("data/processed/ozet_tablolari")
OZETLER_DIR   = Path("data/processed/hazir_ozetler")
OZETLER_DIR.mkdir(parents=True, exist_ok=True)
SUMMARY_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────────────────────
# 1. ÖZET TABLOLARI
# ──────────────────────────────────────────────────────────────────────────────

def compute_summary_tables(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Döndürür:
      gunluk_top_konular      — her gün için en çok geçen top-5 kategori
      haftalik_trend          — haftalık ortalama NPS + yorum sayısı
      aylik_trend             — aylık ortalama NPS + yorum sayısı
      segment_dagilim         — NPS segmenti × yorum tipi × duygu çapraz tablo
      duygu_kategori_kirilim  — ana kategori × duygu matrisi
    """
    df = df.copy()
    df["INPUT_AS_OF_DATE"] = pd.to_datetime(df["INPUT_AS_OF_DATE"])
    df["gun"]  = df["INPUT_AS_OF_DATE"].dt.date
    df["hafta"] = df["INPUT_AS_OF_DATE"].dt.to_period("W")
    df["ay"]    = df["INPUT_AS_OF_DATE"].dt.to_period("M")

    # NPS segment etiketi
    def segment(s):
        if s <= 6: return "Detractor"
        if s <= 8: return "Passive"
        return "Promoter"
    df["SEGMENT"] = df["NPS_SCORE"].apply(segment)

    # 1a. Günlük top konular
    top_konular = (
        df.groupby(["gun", "FIRST_MAIN_CATEGORY"])
          .size()
          .reset_index(name="yorum_sayisi")
          .sort_values(["gun", "yorum_sayisi"], ascending=[True, False])
    )
    top_konular = (
        top_konular.groupby("gun")
                   .head(5)
                   .reset_index(drop=True)
    )

    # 1b. Haftalık trend
    haftalik = (
        df.groupby("hafta")
          .agg(yorum_sayisi=("NPS_SCORE", "count"),
               ort_nps=("NPS_SCORE", "mean"))
          .reset_index()
    )
    haftalik["hafta"] = haftalik["hafta"].astype(str)

    # 1c. Aylık trend
    aylik = (
        df.groupby("ay")
          .agg(yorum_sayisi=("NPS_SCORE", "count"),
               ort_nps=("NPS_SCORE", "mean"))
          .reset_index()
    )
    aylik["ay"] = aylik["ay"].astype(str)

    # 1d. Segment dağılımı
    segment_dagilim = (
        df.groupby(["SEGMENT", "COMMENT_TYPE", "EMOTION"])
          .size()
          .reset_index(name="adet")
    )

    # 1e. Duygu × kategori kırılım
    duygu_kategori = (
        df.pivot_table(
            index="FIRST_MAIN_CATEGORY",
            columns="EMOTION",
            values="NPS_SCORE",
            aggfunc="count",
            fill_value=0,
        ).reset_index()
    )

    return {
        "gunluk_top_konular":     top_konular,
        "haftalik_trend":         haftalik,
        "aylik_trend":            aylik,
        "segment_dagilim":        segment_dagilim,
        "duygu_kategori_kirilim": duygu_kategori,
    }


def save_summary_tables(tables: dict[str, pd.DataFrame]):
    for name, tbl in tables.items():
        path = SUMMARY_DIR / f"{name}.parquet"
        tbl.to_parquet(path, index=False)
        print(f"  [✓] {path}  ({len(tbl):,} satır)")


# ──────────────────────────────────────────────────────────────────────────────
# 2. HAZIR METİN ÖZETLERİ  (nps_ozetler tablosuna yazılacak)
# ──────────────────────────────────────────────────────────────────────────────

def build_text_summary_row(ozet_cesidi: str, tarih: str, ozet_text: str) -> dict:
    """nps_ozetler tablosuna gidecek tek satır."""
    return {
        "OZET_CESIDI": ozet_cesidi,
        "TARIH":       tarih,        # özetin kapsadığı verilerin başlangıç tarihi
        "OZET":        ozet_text,
        "LOAD_DATE":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def generate_rule_based_summaries(df: pd.DataFrame) -> pd.DataFrame:
    """
    LLM çağrısı olmadan, istatistiksel özetler üretir.
    (LLM entegrasyonu llm_summarizer.py modülünde ayrıca yapılacak.)
    """
    df = df.copy()
    df["INPUT_AS_OF_DATE"] = pd.to_datetime(df["INPUT_AS_OF_DATE"])
    df["hafta"] = df["INPUT_AS_OF_DATE"].dt.to_period("W")
    df["ay"]    = df["INPUT_AS_OF_DATE"].dt.to_period("M")

    rows = []

    # — Haftalık konu özeti
    for hafta, grp in df.groupby("hafta"):
        top3 = (
            grp["FIRST_MAIN_CATEGORY"].value_counts().head(3)
        )
        sikayetler = grp[grp["COMMENT_TYPE"] == "Şikayet"]
        top3_sikayet = sikayetler["FIRST_MAIN_CATEGORY"].value_counts().head(3)

        ozet = (
            f"Bu hafta toplam {len(grp):,} yorum alındı. "
            f"En çok konuşulan konular: {', '.join(top3.index.tolist())}. "
            f"En fazla şikayet alan konular: {', '.join(top3_sikayet.index.tolist()) if len(top3_sikayet) else 'yok'}. "
            f"Haftalık ortalama NPS: {grp['NPS_SCORE'].mean():.2f}."
        )
        rows.append(build_text_summary_row(
            ozet_cesidi="Haftalık Konu Özeti",
            tarih=str(hafta.start_time.date()),
            ozet_text=ozet,
        ))

    # — Aylık konu özeti
    for ay, grp in df.groupby("ay"):
        top5 = grp["FIRST_MAIN_CATEGORY"].value_counts().head(5)
        detractors = grp[grp["NPS_SCORE"] <= 6]
        ozet = (
            f"{str(ay)} ayında toplam {len(grp):,} yorum alındı. "
            f"NPS ortalaması: {grp['NPS_SCORE'].mean():.2f}. "
            f"Detractor oranı: %{len(detractors)/len(grp)*100:.1f}. "
            f"Öne çıkan konular: {', '.join(top5.index.tolist())}."
        )
        rows.append(build_text_summary_row(
            ozet_cesidi="Aylık Konu Özeti",
            tarih=str(ay.start_time.date()),
            ozet_text=ozet,
        ))

    # — Günlük negatif özet (son 30 gün, sadece NPS <= 4)
    recent = df[df["INPUT_AS_OF_DATE"] >= df["INPUT_AS_OF_DATE"].max() - pd.Timedelta(days=30)]
    for gun, grp in recent.groupby(df["INPUT_AS_OF_DATE"].dt.date):
        neg = grp[grp["NPS_SCORE"] <= 4]
        if len(neg) == 0:
            continue
        top_neg = neg["FIRST_MAIN_CATEGORY"].value_counts().head(3)
        ozet = (
            f"{gun} tarihinde {len(neg):,} negatif yorum (NPS 0-4). "
            f"Yoğunlaşan konular: {', '.join(top_neg.index.tolist())}. "
            f"Hakim duygular: {', '.join(neg['EMOTION'].value_counts().head(2).index.tolist())}."
        )
        rows.append(build_text_summary_row(
            ozet_cesidi="Günlük Negatif Özet",
            tarih=str(gun),
            ozet_text=ozet,
        ))

    # — Haftalık segment dağılımı
    for hafta, grp in df.groupby("hafta"):
        det = len(grp[grp["NPS_SCORE"] <= 6])
        pas = len(grp[(grp["NPS_SCORE"] >= 7) & (grp["NPS_SCORE"] <= 8)])
        pro = len(grp[grp["NPS_SCORE"] >= 9])
        total = len(grp)
        ozet = (
            f"Hafta {hafta}: Detractor %{det/total*100:.1f} ({det:,}), "
            f"Passive %{pas/total*100:.1f} ({pas:,}), "
            f"Promoter %{pro/total*100:.1f} ({pro:,})."
        )
        rows.append(build_text_summary_row(
            ozet_cesidi="Haftalık Segment Dağılımı",
            tarih=str(hafta.start_time.date()),
            ozet_text=ozet,
        ))

    return pd.DataFrame(rows)


def save_ozetler(df_ozetler: pd.DataFrame):
    path_parquet = OZETLER_DIR / "nps_ozetler.parquet"
    path_csv     = OZETLER_DIR / "nps_ozetler.csv"
    df_ozetler.to_parquet(path_parquet, index=False)
    df_ozetler.to_csv(path_csv, index=False, encoding="utf-8-sig")
    print(f"  [✓] {path_parquet}  ({len(df_ozetler):,} satır)")
    print(f"  [✓] {path_csv}")


# ──────────────────────────────────────────────────────────────────────────────
# Ana akış
# ──────────────────────────────────────────────────────────────────────────────
def run():
    print("[*] Ham veri okunuyor…")
    df = pd.read_parquet(RAW_PARQUET)
    print(f"    {len(df):,} satır yüklendi.")

    print("\n[1] Özet tabloları hesaplanıyor…")
    tables = compute_summary_tables(df)
    save_summary_tables(tables)

    print("\n[2] Hazır metin özetleri üretiliyor…")
    df_ozetler = generate_rule_based_summaries(df)
    save_ozetler(df_ozetler)

    print(f"\n[✓] Offline hazırlık tamamlandı.")
    print(f"    Özet tablosu satır sayıları:")
    for name, tbl in tables.items():
        print(f"      {name}: {len(tbl):,}")
    print(f"    nps_ozetler: {len(df_ozetler):,} satır")


if __name__ == "__main__":
    run()
