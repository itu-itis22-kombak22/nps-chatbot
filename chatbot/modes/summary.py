"""
Summary Mode — haftalık/aylık/günlük NPS özeti üretir.

Önce nps_ozetler tablosunda hazır özet var mı bakar.
Yoksa istatistiksel özet üretir ve LLM ile metne çevirir.
"""

from __future__ import annotations
import pandas as pd
from chatbot.data_loader import get_raw, get_ozetler
from config.llm_config import chat

_SYSTEM = """\
Sen bir banka NPS analisti chatbot'usun. Aşağıdaki istatistikleri kullanarak
kullanıcıya Türkçe, sade ve profesyonel bir özet sun.
Maddeler halinde yaz. Maksimum 200 kelime.
"""


def _stats_text(df: pd.DataFrame, period: str) -> str:
    total   = len(df)
    avg_nps = df["NPS_SCORE"].mean()
    det     = len(df[df["NPS_SCORE"] <= 6])
    pas     = len(df[(df["NPS_SCORE"] >= 7) & (df["NPS_SCORE"] <= 8)])
    pro     = len(df[df["NPS_SCORE"] >= 9])
    top3    = df["FIRST_MAIN_CATEGORY"].value_counts().head(3).to_dict()
    top3_neg = (
        df[df["NPS_SCORE"] <= 4]["FIRST_MAIN_CATEGORY"]
        .value_counts().head(3).to_dict()
    )
    top_emotion = df["EMOTION"].value_counts().head(3).to_dict()

    return (
        f"Periyot: {period}\n"
        f"Toplam yorum: {total:,}\n"
        f"Ortalama NPS: {avg_nps:.2f}\n"
        f"Detractor: {det:,} (%{det/total*100:.1f}), "
        f"Passive: {pas:,} (%{pas/total*100:.1f}), "
        f"Promoter: {pro:,} (%{pro/total*100:.1f})\n"
        f"En çok yorum alan konular: {top3}\n"
        f"En çok şikayet alan konular: {top3_neg}\n"
        f"Baskın duygular: {top_emotion}"
    )


def respond(params: dict) -> str:
    period = params.get("period") or "haftalık"

    # 1. Hazır özet var mı?
    ozet_map = {
        "haftalık": "Haftalık Konu Özeti",
        "aylık":    "Aylık Konu Özeti",
        "günlük":   "Günlük Negatif Özet",
    }
    ozet_cesidi = ozet_map.get(period)
    if ozet_cesidi:
        ozetler = get_ozetler(ozet_cesidi=ozet_cesidi)
        if not ozetler.empty:
            latest = ozetler.iloc[0]
            return (
                f"**{ozet_cesidi}** ({latest['TARIH']})\n\n"
                f"{latest['OZET']}"
            )

    # 2. Hazır yoksa istatistikten üret
    df = get_raw(period=period)
    if df.empty:
        return f"Seçilen dönem ({period}) için veri bulunamadı."

    stats = _stats_text(df, period)
    try:
        return chat(
            messages=[
                {"role": "system",  "content": _SYSTEM},
                {"role": "user",    "content": stats},
            ],
            max_tokens=512,
        )
    except Exception:
        # LLM ulaşılamıyorsa ham istatistik dön
        return f"📊 **{period.capitalize()} Özet**\n\n```\n{stats}\n```"
