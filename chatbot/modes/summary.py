"""
Summary mode: produce an NPS summary from prepared summaries or raw rows.
"""

from __future__ import annotations

import pandas as pd

from chatbot.data_loader import get_ozetler, get_raw
from config.llm_config import chat

_SYSTEM = """\
Sen bir banka NPS analisti chatbot'usun. Asagidaki istatistikleri kullanarak
kullaniciya Turkce, sade ve profesyonel bir ozet sun.
Maddeler halinde yaz. Maksimum 200 kelime.
"""


def respond(params: dict) -> str:
    period = params.get("period") or "haftalik"
    date_label = params.get("date_label") or period

    if not _has_query_filters(params):
        prepared = _prepared_summary(period)
        if prepared:
            return prepared

    df = get_raw(
        period=period,
        category=params.get("category"),
        segment=params.get("segment"),
        emotion=params.get("emotion"),
        comment_type=params.get("comment_type"),
        nps_min=params.get("nps_min"),
        nps_max=params.get("nps_max"),
        date_start=params.get("date_start"),
        date_end=params.get("date_end"),
    )
    if df.empty:
        return f"Secilen filtreler ({date_label}) icin veri bulunamadi."

    stats = _stats_text(df, date_label)
    try:
        return chat(
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": stats},
            ],
            max_tokens=512,
        )
    except Exception:
        return f"**{date_label} NPS Ozeti**\n\n```\n{stats}\n```"


def _has_query_filters(params: dict) -> bool:
    filter_keys = {
        "date_start", "date_end", "category", "segment", "emotion",
        "comment_type", "nps_min", "nps_max",
    }
    return any(params.get(key) is not None for key in filter_keys)


def _prepared_summary(period: str) -> str | None:
    summary_map = {
        "haftalik": "Haftalik Konu Ozeti",
        "haftalık": "Haftalık Konu Özeti",
        "aylik": "Aylik Konu Ozeti",
        "aylık": "Aylık Konu Özeti",
        "gunluk": "Gunluk Negatif Ozet",
        "günlük": "Günlük Negatif Özet",
    }
    summary_type = summary_map.get(period)
    if not summary_type:
        return None

    summaries = get_ozetler(ozet_cesidi=summary_type)
    if summaries.empty:
        return None

    latest = summaries.iloc[0]
    return f"**{summary_type}** ({latest['TARIH']})\n\n{latest['OZET']}"


def _stats_text(df: pd.DataFrame, label: str) -> str:
    total = len(df)
    avg_nps = df["NPS_SCORE"].mean()
    det = len(df[df["NPS_SCORE"] <= 6])
    pas = len(df[(df["NPS_SCORE"] >= 7) & (df["NPS_SCORE"] <= 8)])
    pro = len(df[df["NPS_SCORE"] >= 9])
    top3 = df["FIRST_MAIN_CATEGORY"].value_counts().head(3).to_dict()
    top3_neg = df[df["NPS_SCORE"] <= 4]["FIRST_MAIN_CATEGORY"].value_counts().head(3).to_dict()
    top_emotion = df["EMOTION"].value_counts().head(3).to_dict()

    return (
        f"Donem: {label}\n"
        f"Toplam yorum: {total:,}\n"
        f"Ortalama NPS: {avg_nps:.2f}\n"
        f"Detractor: {det:,} (%{det / total * 100:.1f}), "
        f"Passive: {pas:,} (%{pas / total * 100:.1f}), "
        f"Promoter: {pro:,} (%{pro / total * 100:.1f})\n"
        f"En cok yorum alan konular: {top3}\n"
        f"En cok negatif yorum alan konular: {top3_neg}\n"
        f"Baskin duygular: {top_emotion}"
    )
