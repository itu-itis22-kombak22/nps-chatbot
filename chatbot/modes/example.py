"""
Example mode: return real customer comment examples matching filters.
"""

from __future__ import annotations

import pandas as pd
import unicodedata

from chatbot.data_loader import get_raw

DEFAULT_LIMIT = 5
MAX_LIMIT = 20


def respond(params: dict) -> str:
    category = params.get("category")
    segment = params.get("segment")
    emotion = params.get("emotion")
    comment_type = params.get("comment_type")
    period = params.get("period") or "aylik"
    date_start = params.get("date_start")
    date_end = params.get("date_end")
    date_label = params.get("date_label") or period
    limit = min(int(params.get("limit") or DEFAULT_LIMIT), MAX_LIMIT)

    df = get_raw(
        period=period,
        category=category,
        segment=segment,
        emotion=emotion,
        comment_type=comment_type,
        nps_min=params.get("nps_min"),
        nps_max=params.get("nps_max"),
        date_start=date_start,
        date_end=date_end,
    )

    if df.empty:
        return "Secilen filtrelere uyan yorum bulunamadi."

    df = df.copy()
    df["_sort"] = df["COMMENT_TYPE"].map(_comment_priority).fillna(9)
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
    if segment:
        header_parts.append(segment)
    if comment_type:
        header_parts.append(comment_type)
    if category:
        header_parts.append(category)
    if emotion:
        header_parts.append(emotion)
    header = " / ".join(header_parts) if header_parts else "Genel"

    return (
        f"**Ornek Yorumlar** - {header} ({date_label}, {len(sample)} yorum)\n\n"
        + "\n\n".join(lines)
    )


def _segment_label(score: int) -> str:
    if score <= 6:
        return "Detractor"
    if score <= 8:
        return "Passive"
    return "Promoter"


def _comment_priority(value: object) -> int:
    text = str(value).casefold().replace("ı", "i")
    norm = "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )
    if "sikayet" in norm:
        return 0
    if "talep" in norm or "oneri" in norm:
        return 1
    if "memnuniyet" in norm:
        return 2
    if "veri" in norm:
        return 3
    return 9
