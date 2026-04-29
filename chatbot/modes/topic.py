"""
Topic Mode — kategori / segment / duygu bazlı detay analiz.
"""

from __future__ import annotations
import pandas as pd
from chatbot.data_loader import get_raw, get_summary_table
from config.llm_config import chat

_SYSTEM = """\
Sen bir banka NPS analisti chatbot'usun.
Kullanıcının sorduğu kategori veya segment hakkında aşağıdaki istatistiklere
dayanarak Türkçe, sade ve analitik bir cevap üret. Maksimum 250 kelime.
"""


def _build_stats(df: pd.DataFrame, label: str) -> str:
    if df.empty:
        return f"'{label}' için yeterli veri yok."

    total    = len(df)
    avg_nps  = df["NPS_SCORE"].mean()
    det_rate = len(df[df["NPS_SCORE"] <= 6]) / total * 100
    pro_rate = len(df[df["NPS_SCORE"] >= 9]) / total * 100

    top_sub  = df["FIRST_SUBCATEGORY"].value_counts().head(3).to_dict()
    top_emot = df["EMOTION"].value_counts().head(3).to_dict()
    top_type = df["COMMENT_TYPE"].value_counts().to_dict()

    return (
        f"Konu: {label}\n"
        f"Toplam yorum: {total:,}\n"
        f"Ortalama NPS: {avg_nps:.2f}\n"
        f"Detractor oranı: %{det_rate:.1f} | Promoter oranı: %{pro_rate:.1f}\n"
        f"Öne çıkan alt konular: {top_sub}\n"
        f"Baskın duygular: {top_emot}\n"
        f"Yorum tipleri: {top_type}"
    )


def respond(params: dict) -> str:
    category     = params.get("category")
    segment      = params.get("segment")
    emotion      = params.get("emotion")
    period       = params.get("period") or "aylık"

    df = get_raw(
        period=period,
        category=category,
        segment=segment,
        emotion=emotion,
    )

    label_parts = []
    if category: label_parts.append(category)
    if segment:  label_parts.append(segment)
    if emotion:  label_parts.append(emotion)
    label = " / ".join(label_parts) if label_parts else "Genel"

    stats = _build_stats(df, label)

    try:
        return chat(
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": stats},
            ],
            max_tokens=512,
        )
    except Exception:
        return f"📊 **{label} Analizi** ({period})\n\n```\n{stats}\n```"
