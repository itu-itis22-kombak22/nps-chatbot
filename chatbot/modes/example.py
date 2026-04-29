"""
Example Mode — filtreye uyan gerçek yorum örneklerini döndürür.
"""

from __future__ import annotations
import pandas as pd
from chatbot.data_loader import get_raw

MAX_EXAMPLES = 5


def respond(params: dict) -> str:
    category     = params.get("category")
    segment      = params.get("segment")
    emotion      = params.get("emotion")
    comment_type = params.get("comment_type")
    period       = params.get("period") or "haftalık"

    df = get_raw(
        period=period,
        category=category,
        segment=segment,
        emotion=emotion,
        comment_type=comment_type,
    )

    if df.empty:
        return "Seçilen filtrelere uyan yorum bulunamadı."

    sample = df.sample(min(MAX_EXAMPLES, len(df)), random_state=42)

    lines = []
    for i, (_, row) in enumerate(sample.iterrows(), 1):
        seg = _segment_label(row["NPS_SCORE"])
        lines.append(
            f"**{i}.** [{seg} | NPS: {row['NPS_SCORE']} | "
            f"{row['FIRST_MAIN_CATEGORY']} | {row['EMOTION']}]\n"
            f"> {row['TEXT']}"
        )

    header_parts = []
    if segment:      header_parts.append(segment)
    if category:     header_parts.append(category)
    if emotion:      header_parts.append(emotion)
    if comment_type: header_parts.append(comment_type)
    header = " / ".join(header_parts) if header_parts else "Rastgele"

    return (
        f"📝 **Örnek Yorumlar** — {header} ({period})\n\n"
        + "\n\n".join(lines)
    )


def _segment_label(score: int) -> str:
    if score <= 6: return "Detractor"
    if score <= 8: return "Passive"
    return "Promoter"
