"""
Example Mode — filtreye uyan gerçek yorum örneklerini döndürür.
"""

from __future__ import annotations
import pandas as pd
from chatbot.data_loader import get_raw

DEFAULT_LIMIT = 5
MAX_LIMIT     = 20


def respond(params: dict) -> str:
    category     = params.get("category")
    segment      = params.get("segment")
    emotion      = params.get("emotion")
    comment_type = params.get("comment_type")
    period       = params.get("period") or "aylık"
    limit        = min(int(params.get("limit") or DEFAULT_LIMIT), MAX_LIMIT)

    df = get_raw(
        period=period,
        category=category,
        segment=segment,
        emotion=emotion,
        comment_type=comment_type,
    )

    if df.empty:
        return "Seçilen filtrelere uyan yorum bulunamadı."

    # Şikayet/Memnuniyet önce gelsin, Veri Yetersiz sona
    priority = {"Şikayet": 0, "Talep/Öneri": 1, "Memnuniyet": 2, "Veri Yetersiz": 3}
    df = df.copy()
    df["_sort"] = df["COMMENT_TYPE"].map(priority).fillna(9)
    df = df.sort_values("_sort").drop(columns="_sort")

    sample = df.head(limit * 3).sample(min(limit, len(df)), random_state=42)

    lines = []
    for i, (_, row) in enumerate(sample.iterrows(), 1):
        seg = _segment_label(row["NPS_SCORE"])
        sub = f" / {row['FIRST_SUBCATEGORY']}" if pd.notna(row.get("FIRST_SUBCATEGORY")) else ""
        lines.append(
            f"**{i}.** [{seg} | NPS: {row['NPS_SCORE']} | "
            f"{row['FIRST_MAIN_CATEGORY']}{sub} | {row['EMOTION']} | {row['COMMENT_TYPE']}]\n"
            f"> {row['TEXT']}"
        )

    header_parts = []
    if segment:      header_parts.append(segment)
    if comment_type: header_parts.append(comment_type)
    if category:     header_parts.append(category)
    if emotion:      header_parts.append(emotion)
    header = " / ".join(header_parts) if header_parts else "Genel"

    return (
        f"📝 **Örnek Yorumlar** — {header} ({period}, {len(sample)} yorum)\n\n"
        + "\n\n".join(lines)
    )


def _segment_label(score: int) -> str:
    if score <= 6: return "Detractor"
    if score <= 8: return "Passive"
    return "Promoter"
