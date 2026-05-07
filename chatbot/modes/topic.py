"""
Topic mode: category, segment, emotion, and issue analysis.
"""

from __future__ import annotations

import pandas as pd

from chatbot.data_loader import get_raw
from config.llm_config import chat

_SYSTEM = """\
Sen bir banka NPS analisti chatbot'usun.
Kullanicinin sordugu kategori veya segment hakkinda asagidaki istatistiklere
dayanarak Turkce, sade ve analitik bir cevap uret. Maksimum 250 kelime.
"""


def respond(params: dict) -> str:
    category = params.get("category")
    segment = params.get("segment")
    emotion = params.get("emotion")
    comment_type = params.get("comment_type")
    period = params.get("period") or "aylik"
    date_label = params.get("date_label") or period

    df = get_raw(
        period=period,
        category=category,
        segment=segment,
        emotion=emotion,
        comment_type=comment_type,
        nps_min=params.get("nps_min"),
        nps_max=params.get("nps_max"),
        date_start=params.get("date_start"),
        date_end=params.get("date_end"),
    )

    label_parts = []
    if category:
        label_parts.append(category)
    if segment:
        label_parts.append(segment)
    if emotion:
        label_parts.append(emotion)
    if comment_type:
        label_parts.append(comment_type)
    label = " / ".join(label_parts) if label_parts else "Genel"

    stats = _build_stats(df, label, date_label)

    try:
        return chat(
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": stats},
            ],
            max_tokens=512,
        )
    except Exception:
        return f"**{label} Analizi** ({date_label})\n\n```\n{stats}\n```"


def _build_stats(df: pd.DataFrame, label: str, date_label: str) -> str:
    if df.empty:
        return f"{label} / {date_label} icin yeterli veri yok."

    total = len(df)
    avg_nps = df["NPS_SCORE"].mean()
    det_rate = len(df[df["NPS_SCORE"] <= 6]) / total * 100
    pro_rate = len(df[df["NPS_SCORE"] >= 9]) / total * 100

    top_sub = df["FIRST_SUBCATEGORY"].value_counts().head(3).to_dict()
    top_emot = df["EMOTION"].value_counts().head(3).to_dict()
    top_type = df["COMMENT_TYPE"].value_counts().to_dict()

    return (
        f"Konu: {label}\n"
        f"Donem: {date_label}\n"
        f"Toplam yorum: {total:,}\n"
        f"Ortalama NPS: {avg_nps:.2f}\n"
        f"Detractor orani: %{det_rate:.1f} | Promoter orani: %{pro_rate:.1f}\n"
        f"One cikan alt konular: {top_sub}\n"
        f"Baskin duygular: {top_emot}\n"
        f"Yorum tipleri: {top_type}"
    )
