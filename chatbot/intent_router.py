"""
Conversation router for the NPS analytics assistant.

The router is LLM-first. Rules are intentionally limited to:
- date expression normalization,
- category canonicalization,
- validation and slot completion checks.

The public RouterResult shape is kept compatible with engine.py.
"""

from __future__ import annotations

import calendar
import json
import logging
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from enum import Enum, auto
from typing import Any, Literal

from config.constants import COMMENT_TYPES, EMOTIONS, MAIN_CATEGORIES
from config.llm_config import chat

logger = logging.getLogger("nps_chatbot.router")


class State(Enum):
    DIRECT = auto()
    DETAIL = auto()
    RESPONSE = auto()


MessageType = Literal["small_talk", "help", "out_of_scope", "analytics", "ambiguous"]
TargetMode = Literal["summary", "topic", "example", "none"]
RouterAction = Literal["answer", "ask_detail", "run_query"]


@dataclass
class StructuredQuery:
    metric: str | None = None
    analysis_type: str | None = None
    date_range: dict[str, Any] = field(default_factory=dict)
    filters: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    raw_slots: dict[str, Any] = field(default_factory=dict)


@dataclass
class RouterOutput:
    message_type: MessageType
    target_mode: TargetMode
    action: RouterAction
    confidence: float
    complete: bool
    slots: dict[str, Any] = field(default_factory=dict)
    missing_slots: list[str] = field(default_factory=list)
    requires_confirmation: bool = False
    assistant_message: str | None = None
    structured_query: StructuredQuery | None = None
    source: str = "llm"


@dataclass
class ConversationState:
    state: State = State.DIRECT
    detail_nonsense_count: int = 0
    pending_mode: str | None = None
    pending_params: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    last_structured_query: dict[str, Any] | None = None


@dataclass
class RouterResult:
    mode: str
    response: str | None
    params: dict
    needs_data: bool = False
    structured_query: dict | None = None


_DIRECT_NONSENSE_MSG = (
    "Bu mesaj NPS analitigi kapsaminda gorunmuyor. NPS ozetleri, trendler, "
    "kategori analizleri veya ornek yorumlar hakkinda soru sorabilirsiniz."
)
_ON_IT_MSG = "Anliyorum, hemen bakiyorum."

_CATEGORY_ALIASES = {
    "alisveris kredisi": "Alışveriş Kredisi",
    "atm": "ATM",
    "ihtiyac kredisi": "İhtiyaç Kredileri",
    "kredi": "İhtiyaç Kredileri",
    "mobil": "Mobil Bankacılık",
    "mobil uygulama": "Mobil Bankacılık",
    "mobil bankacilik": "Mobil Bankacılık",
    "sube": "Şube",
    "banka": "Banka",
    "borsa": "Borsa Market",
    "fon": "Fon Market",
    "getirfinans": "Getirfinans",
    "fx": "FX Market",
    "goruntulu bankacilik": "Görüntülü Bankacılık",
    "kart": "Kartlar",
    "kartlar": "Kartlar",
    "kiraz": "Kiraz (Vadeli Hesap)",
    "hizli para": "Hızlı Para (KMH)",
    "kmh": "Hızlı Para (KMH)",
    "kripto": "Kripto Market",
    "kurumsal": "Kurumsal Bankacılık",
    "kampanya": "Kampanyalar",
    "kampanyalar": "Kampanyalar",
    "cagri merkezi": "Çağrı Merkezi",
}

_COMMENT_TYPE_ALIASES = {
    "sikayet": "Şikayet",
    "sikayetler": "Şikayet",
    "memnuniyet": "Memnuniyet",
    "memnun": "Memnuniyet",
    "talep": "Talep/Öneri",
    "oneri": "Talep/Öneri",
    "talep oneri": "Talep/Öneri",
}

_EMOTION_ALIASES = {
    "mutsuz": "Mutsuz",
    "kizgin": "Kızgın",
    "sinirli": "Kızgın",
    "endisel": "Endişeli",
    "endiseli": "Endişeli",
    "mutlu": "Mutlu",
    "umutlu": "Umutlu",
    "minnettar": "Minnettar",
}

_MONTHS = {
    "ocak": 1,
    "subat": 2,
    "mart": 3,
    "nisan": 4,
    "mayis": 5,
    "haziran": 6,
    "temmuz": 7,
    "agustos": 8,
    "eylul": 9,
    "ekim": 10,
    "kasim": 11,
    "aralik": 12,
}

_SYSTEM_PROMPT = """\
Sen bir banka NPS conversational analytics router'isin.
Kullanici mesajini anlamlandir ve SADECE JSON dondur.

Mesaj tipleri:
- small_talk: selamlama, sohbet
- help: kullanici ne sorabilecegini veya yardim ister
- out_of_scope: NPS/banka musteri geri bildirimi analitigi disi
- analytics: NPS yorumlari, skor, trend, kategori, segment, duygu, ornek yorum, kok neden analizi
- ambiguous: anlamli ama karar vermek icin guven dusuk

Target mode degerleri:
- summary: skor/ozet/NPS dagilimi/segment ozeti gibi sayisal veya genel ozet istekleri
- topic: kategori, konu, trend, kirilim, kok neden, issue veya insight analizi
- example: musteri yorumu ornekleri veya belirli yorum/musteri bulma istekleri
- none: analytics disi mesajlar veya kullanicinin hangi analizi istedigi net degilse

Slotlari dogal dilden cikar. Kelime listesine bagli kalma; anlami yorumla.
Eksik slotlari kod tarafi belirleyecek; sen sadece kullanicinin soyledigi bilgileri slots alanina yaz.
Tarih ifadesini normalize etme; ham ifadeyi date_expression alanina yaz.
Kategori adini kullanicinin dedigi haliyle yaz, canonical yapmak kod tarafinda yapilacak.
Emin degilsen confidence dusuk tut.

assistant_message alanina sadece veri sorgusu gerektirmeyen cevaplarda veya takip sorusu gerekiyorsa
kisa Turkce cevap/takip sorusu yaz. Sorgu calismaya hazirsa assistant_message null olsun.
Analytics mesajlarda target_mode sadece summary/topic/example olabilir.
Kullanici "NPS ile ilgili soru soracagim" gibi hazirlik cumlesi yazarsa target_mode none olsun.
Summary ve topic icin tarih yoksa date_expression eksik say.
Example icin kategori, segment, NPS araligi, duygu, yorum tipi veya customer_id filtrelerinden en az biri yoksa filter eksik say.
Conversation context verildiyse onceki target_mode ve slotlari dikkate al.
Kullanici "subattan da getir", "aynisini mart icin", "bundan 5 tane daha" gibi takip mesaji yazarsa
onceki query'deki eksik birakilan mode/filtreleri koru, sadece kullanicinin degistirdigi slotlari yenile.

JSON semasi:
{
  "message_type": "small_talk|help|out_of_scope|analytics|ambiguous",
  "target_mode": "summary|topic|example|none",
  "confidence": 0.0,
  "slots": {
    "date_expression": null,
    "metric": null,
    "category": null,
    "subcategory": null,
    "segment": null,
    "nps_min": null,
    "nps_max": null,
    "emotion": null,
    "comment_type": null,
    "output_type": null,
    "limit": null,
    "customer_id": null
  },
  "requires_confirmation": false,
  "assistant_message": null
}
"""


def _repair_mojibake(text: str) -> str:
    try:
        return text.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _normalize(text: str) -> str:
    text = _repair_mojibake(text).casefold()
    text = text.replace("i̇", "i")
    replacements = str.maketrans({
        "ç": "c", "ğ": "g", "ı": "i",
        "ö": "o", "ş": "s", "ü": "u",
    })
    text = text.translate(replacements)
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )


def _clean_json(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("LLM response did not contain JSON")
    return json.loads(match.group())


def _llm_extract(text: str, conversation_context: dict[str, Any] | None = None) -> dict:
    logger.info("[classifier] llm request chars=%s", len(text))
    user_content = {
        "current_user_message": text,
        "conversation_context": conversation_context or {},
    }
    raw = chat(
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
        ],
        temperature=0.0,
        max_tokens=700,
    )
    logger.info("[classifier] llm raw=%s", raw[:1500])
    data = _clean_json(raw)
    data["_source"] = "llm"
    return data


def _canonical_category(value: Any) -> str | None:
    if not value:
        return None
    raw = str(value).strip()
    norm = _normalize(raw)
    for category in MAIN_CATEGORIES:
        if norm == _normalize(category):
            return category
    for alias, category in _CATEGORY_ALIASES.items():
        if norm == alias or alias in norm:
            return category
    return None


def _canonical_comment_type(value: Any) -> str | None:
    if not value:
        return None
    norm = _normalize(str(value))
    for item in COMMENT_TYPES:
        if norm == _normalize(item):
            return item
    for alias, item in _COMMENT_TYPE_ALIASES.items():
        if alias in norm:
            return item
    return None


def _canonical_emotion(value: Any) -> str | None:
    if not value:
        return None
    norm = _normalize(str(value))
    for item in EMOTIONS:
        if norm == _normalize(item):
            return item
    for alias, item in _EMOTION_ALIASES.items():
        if alias in norm:
            return item
    return None


def _segment_from_slots(slots: dict[str, Any]) -> tuple[str | None, int | None, int | None]:
    segment = slots.get("segment")
    nps_min = slots.get("nps_min")
    nps_max = slots.get("nps_max")

    if isinstance(segment, str):
        norm = _normalize(segment)
        if "detractor" in norm or "0-6" in norm:
            return "Detractor", 0, 6
        if "passive" in norm or "pasif" in norm or "7-8" in norm:
            return "Passive", 7, 8
        if "promoter" in norm or "9-10" in norm:
            return "Promoter", 9, 10

    if nps_min is not None and nps_max is not None:
        try:
            lo, hi = int(nps_min), int(nps_max)
            if lo == 0 and hi == 6:
                return "Detractor", lo, hi
            if lo == 7 and hi == 8:
                return "Passive", lo, hi
            if lo == 9 and hi == 10:
                return "Promoter", lo, hi
            return None, lo, hi
        except (TypeError, ValueError):
            pass

    return None, None, None


def _add_months(base: date, months: int) -> date:
    month = base.month - 1 + months
    year = base.year + month // 12
    month = month % 12 + 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _date_range(start: date, end: date, grain: str, raw: str) -> dict[str, str]:
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "grain": grain,
        "raw": raw,
    }


def _month_range(year: int, month: int, raw: str) -> dict[str, str]:
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return _date_range(start, end, "month", raw)


def _month_name_pattern() -> str:
    return "|".join(_MONTHS.keys())


def _month_token_pattern() -> str:
    suffix = r"(?:\s+ayi|\s+ayina|\s+ayinda|\s+ayinin|tan|ten|dan|den|ta|te|da|de)?"
    return rf"({_month_name_pattern()}){suffix}"


def _contains_month_name(text: Any) -> bool:
    if not text:
        return False
    return re.search(rf"\b{_month_token_pattern()}\b", _normalize(str(text))) is not None


def _has_year(text: Any) -> bool:
    return bool(text and re.search(r"\b\d{4}\b", str(text)))


def _year_from_context(context: dict[str, Any], last_query: dict[str, Any] | None) -> int | None:
    raw = context.get("date_expression")
    if raw:
        match = re.search(r"\b(\d{4})\b", str(raw))
        if match:
            return int(match.group(1))

    if last_query:
        start = (last_query.get("date_range") or {}).get("start")
        if start:
            match = re.match(r"(\d{4})-", str(start))
            if match:
                return int(match.group(1))

    return None


def _apply_context_year(
    slots: dict[str, Any],
    context: dict[str, Any],
    last_query: dict[str, Any] | None,
) -> dict[str, Any]:
    raw_date = slots.get("date_expression")
    if raw_date and _contains_month_name(raw_date) and not _has_year(raw_date):
        year = _year_from_context(context, last_query)
        if year:
            slots["date_expression"] = f"{raw_date} {year}"
    return slots


def _has_meaningful_slot(slots: dict[str, Any]) -> bool:
    return any(value is not None for key, value in slots.items() if key != "metric")


def _normalize_date_expression(raw_value: Any, today: date | None = None) -> tuple[dict[str, str], str | None]:
    if not raw_value:
        return {}, None

    today = today or date.today()
    raw = str(raw_value).strip()
    norm = _normalize(raw)
    month_pattern = _month_token_pattern()

    month_year = re.search(rf"\b{month_pattern}\s+(\d{{4}})\b", norm)
    if month_year:
        month = _MONTHS[month_year.group(1)]
        year = int(month_year.group(2))
        return _month_range(year, month, raw), "aylık"

    year_month = re.search(rf"\b(\d{{4}})\s+{month_pattern}\b", norm)
    if year_month:
        year = int(year_month.group(1))
        month = _MONTHS[year_month.group(2)]
        return _month_range(year, month, raw), "aylık"

    if re.search(r"\bbugun\b", norm):
        return _date_range(today, today, "day", raw), "günlük"
    if re.search(r"\bdun\b", norm):
        d = today - timedelta(days=1)
        return _date_range(d, d, "day", raw), "günlük"

    m = re.search(r"son\s+(\d+)\s*(gun|hafta|ay|yil)", norm)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        if unit == "gun":
            start = today - timedelta(days=amount)
            return _date_range(start, today, "day", raw), "günlük"
        if unit == "hafta":
            start = today - timedelta(weeks=amount)
            return _date_range(start, today, "week", raw), "haftalık"
        if unit == "ay":
            start = _add_months(today, -amount)
            return _date_range(start, today, "month", raw), "aylık"
        if unit == "yil":
            start = _add_months(today, -12 * amount)
            return _date_range(start, today, "year", raw), None

    if "bu hafta" in norm or "haftalik" in norm:
        start = today - timedelta(days=today.weekday())
        return _date_range(start, today, "week", raw), "haftalık"
    if "gecen hafta" in norm or "gecmis hafta" in norm:
        this_week = today - timedelta(days=today.weekday())
        start = this_week - timedelta(days=7)
        end = this_week - timedelta(days=1)
        return _date_range(start, end, "week", raw), "haftalık"
    if "bu ay" in norm or "aylik" in norm:
        start = today.replace(day=1)
        return _date_range(start, today, "month", raw), "aylık"
    if "gecen ay" in norm or "gecmis ay" in norm:
        first_this_month = today.replace(day=1)
        end = first_this_month - timedelta(days=1)
        start = end.replace(day=1)
        return _date_range(start, end, "month", raw), "aylık"
    if "bu yil" in norm:
        start = today.replace(month=1, day=1)
        return _date_range(start, today, "year", raw), None
    if "gecen yil" in norm or "gecmis yil" in norm or "gectigimiz yil" in norm:
        start = date(today.year - 1, 1, 1)
        end = date(today.year - 1, 12, 31)
        return _date_range(start, end, "year", raw), None

    return {}, None


def _mode_for_target(target_mode: str) -> str:
    if target_mode in {"summary", "topic", "example"}:
        return target_mode
    return "summary"


def _is_yes(text: str) -> bool:
    norm = _normalize(text)
    return norm in {"evet", "onay", "onayla", "tamam", "calistir", "baslat", "olur"}


def _is_no(text: str) -> bool:
    norm = _normalize(text)
    return norm in {"hayir", "iptal", "vazgec", "dur", "calistirma"}


def _build_structured_query(target_mode: str, slots: dict[str, Any], date_range: dict[str, str]) -> StructuredQuery:
    segment, nps_min, nps_max = _segment_from_slots(slots)
    category = _canonical_category(slots.get("category"))
    comment_type = _canonical_comment_type(slots.get("comment_type"))
    emotion = _canonical_emotion(slots.get("emotion"))

    filters = {
        "nps_segment": segment,
        "nps_min": nps_min,
        "nps_max": nps_max,
        "category": category,
        "subcategory": slots.get("subcategory"),
        "emotion": emotion,
        "comment_type": comment_type,
        "customer_id": slots.get("customer_id"),
    }

    output_type = slots.get("output_type")
    if not output_type:
        output_type = "examples" if target_mode == "example" else "summary"

    return StructuredQuery(
        metric=slots.get("metric") or "nps_score",
        analysis_type=target_mode,
        date_range=date_range,
        filters=filters,
        output={
            "format": output_type,
            "limit": slots.get("limit"),
        },
        raw_slots=slots.copy(),
    )


def _params_from_query(query: StructuredQuery) -> dict:
    params = {}
    date_range = query.date_range or {}
    filters = query.filters or {}
    output = query.output or {}

    if date_range.get("grain") == "day":
        params["period"] = "günlük"
    elif date_range.get("grain") == "week":
        params["period"] = "haftalık"
    elif date_range.get("grain") == "month":
        params["period"] = "aylık"

    if date_range.get("start"):
        params["date_start"] = date_range["start"]
    if date_range.get("end"):
        params["date_end"] = date_range["end"]
    if date_range.get("raw"):
        params["date_label"] = date_range["raw"]

    if filters.get("category"):
        params["category"] = filters["category"]
    if filters.get("nps_segment"):
        params["segment"] = filters["nps_segment"]
    if filters.get("emotion"):
        params["emotion"] = filters["emotion"]
    if filters.get("comment_type"):
        params["comment_type"] = filters["comment_type"]
    if filters.get("nps_min") is not None:
        params["nps_min"] = filters["nps_min"]
    if filters.get("nps_max") is not None:
        params["nps_max"] = filters["nps_max"]
    if output.get("limit"):
        params["limit"] = output["limit"]

    return params


def _validate_and_complete(data: dict) -> RouterOutput:
    message_type = data.get("message_type") or "ambiguous"
    target_mode = data.get("target_mode") or "none"
    slots = data.get("slots") or {}
    missing_slots: list[str] = []
    confidence = float(data.get("confidence") or 0.0)

    if message_type not in {"small_talk", "help", "out_of_scope", "analytics", "ambiguous"}:
        message_type = "ambiguous"
    if target_mode not in {"summary", "topic", "example", "none"}:
        target_mode = "none"

    date_range, period = _normalize_date_expression(slots.get("date_expression"))
    if period:
        slots["period"] = period

    canonical_category = _canonical_category(slots.get("category"))
    if slots.get("category") and not canonical_category:
        missing_slots.append("category")
    if canonical_category:
        slots["category"] = canonical_category

    comment_type = _canonical_comment_type(slots.get("comment_type"))
    if comment_type:
        slots["comment_type"] = comment_type
    emotion = _canonical_emotion(slots.get("emotion"))
    if emotion:
        slots["emotion"] = emotion

    query = None
    complete = message_type in {"small_talk", "help", "out_of_scope", "ambiguous"}
    if message_type != "analytics":
        target_mode = "none"

    if message_type == "analytics":
        query = _build_structured_query(target_mode, slots, date_range)
        if target_mode == "none" or confidence < 0.45:
            missing_slots.append("target_mode")
        if target_mode in {"summary", "topic", "example"} and not date_range:
            if _contains_month_name(slots.get("date_expression")):
                missing_slots.append("date_year")
            else:
                missing_slots.append("date_range")
        if target_mode == "example" and not any([
            query.filters.get("category"),
            query.filters.get("nps_segment"),
            query.filters.get("emotion"),
            query.filters.get("comment_type"),
            query.filters.get("customer_id"),
        ]):
            missing_slots.append("filter")
        complete = not missing_slots

    missing_aliases = {
        "date": "date_range",
        "date_expression": "date_range",
        "period": "date_range",
        "year": "date_year",
        "target": "target_mode",
        "mode": "target_mode",
    }
    missing_slots = [missing_aliases.get(slot, slot) for slot in missing_slots]
    missing_slots = list(dict.fromkeys(missing_slots))
    if message_type == "analytics":
        action = "run_query" if complete else "ask_detail"
    else:
        action = "answer"

    return RouterOutput(
        message_type=message_type,
        target_mode=target_mode,
        action=action,
        confidence=confidence,
        complete=complete,
        slots=slots,
        missing_slots=missing_slots,
        requires_confirmation=bool(data.get("requires_confirmation")),
        assistant_message=data.get("assistant_message"),
        structured_query=query,
        source=data.get("_source", "llm"),
    )


def _clarify_message(output: RouterOutput) -> str:
    if output.assistant_message:
        return output.assistant_message
    if "date_year" in output.missing_slots:
        return "Bir aralık/ay belirttiniz; hangi yil icin bakayim? Ornek: Ocak 2026."
    if "date_range" in output.missing_slots:
        return "Hangi donem icin bakayim? Ornek: gecen ay, son 1 ay, bu hafta."
    if "category" in output.missing_slots:
        return "Hangi kategori icin analiz edeyim? Ornek: Mobil Bankacilik, ATM, Kartlar."
    if "filter" in output.missing_slots:
        return "Ornek yorum icin kategori, segment, duygu veya yorum tipi belirtir misiniz?"
    if "target_mode" in output.missing_slots:
        return "NPS verisinde ozet, trend, kirilim ya da ornek yorum mu istiyorsunuz?"
    return "Sorguyu netlestirmek icin biraz daha detay verebilir misiniz?"


class IntentRouter:
    def __init__(self):
        self.conv = ConversationState()

    def process(self, user_message: str) -> RouterResult:
        text = user_message.strip()
        logger.info("[router.input] state=%s text=%r", self.conv.state.name, text)

        if self.conv.state == State.DIRECT:
            return self._handle_direct(text)
        if self.conv.state == State.DETAIL:
            return self._handle_detail(text)

        self._go_direct("unexpected_response_state")
        return self._handle_direct(text)

    def reset(self):
        old_state = self.conv.state
        self.conv = ConversationState()
        logger.info("[router.transition] %s -> %s reason=reset", old_state.name, self.conv.state.name)

    @property
    def current_state(self) -> State:
        return self.conv.state

    def _handle_direct(self, text: str) -> RouterResult:
        output = self._understand(text)
        output = self._prepare_output(output)
        return self._handle_output(output)

    def _handle_detail(self, text: str) -> RouterResult:
        if self.conv.last_structured_query and self.conv.pending_mode:
            if _is_yes(text):
                self._set_state(State.RESPONSE, "confirmation_accepted")
                logger.info(
                    "[router.ready] mode=%s structured_query=%s params=%s",
                    self.conv.pending_mode,
                    self.conv.last_structured_query,
                    self.conv.pending_params,
                )
                return RouterResult(
                    mode=self.conv.pending_mode,
                    response=_ON_IT_MSG,
                    params=self.conv.pending_params.copy(),
                    needs_data=True,
                    structured_query=self.conv.last_structured_query,
                )
            if _is_no(text):
                self._go_direct("confirmation_rejected")
                return RouterResult("cancelled", "Tamam, sorguyu calistirmiyorum.", {})

        output = self._understand(text)
        output = self._prepare_output(output)
        return self._handle_output(output)

    def _understand(self, text: str) -> RouterOutput:
        try:
            raw = _llm_extract(text, self._conversation_context())
        except Exception as e:
            logger.warning("[classifier] llm error=%s", e)
            raw = {
                "message_type": "ambiguous",
                "target_mode": "none",
                "confidence": 0.0,
                "slots": {},
                "requires_confirmation": False,
                "assistant_message": f"LLM baglantisi sirasinda hata olustu: {e}",
                "_source": "llm_error",
            }

        output = _validate_and_complete(raw)
        self._log_decision(output)
        return output

    def _conversation_context(self) -> dict[str, Any]:
        return {
            "state": self.conv.state.name,
            "pending_mode": self.conv.pending_mode,
            "known_slots": self.conv.context,
            "last_structured_query": self.conv.last_structured_query,
        }

    def _context_target_mode(self) -> str | None:
        if self.conv.pending_mode in {"summary", "topic", "example"}:
            return self.conv.pending_mode
        if self.conv.last_structured_query:
            mode = self.conv.last_structured_query.get("analysis_type")
            if mode in {"summary", "topic", "example"}:
                return mode
        return None

    def _prepare_output(self, output: RouterOutput) -> RouterOutput:
        context_mode = self._context_target_mode()
        has_context = bool(self.conv.context or self.conv.last_structured_query)

        if (
            output.message_type == "ambiguous"
            and has_context
            and _has_meaningful_slot(output.slots)
        ):
            output.message_type = "analytics"
            output.target_mode = context_mode or "none"
            output.action = "ask_detail"
            output.complete = False
            output.missing_slots = []
            logger.info(
                "[router.followup] ambiguous -> analytics target_mode=%s slots=%s",
                output.target_mode,
                output.slots,
            )

        if output.message_type == "analytics" and output.target_mode == "none" and context_mode:
            output.target_mode = context_mode
            output.action = "ask_detail"
            output.complete = False
            output.missing_slots = []
            logger.info("[router.followup] target_mode filled from context=%s", context_mode)

        if output.message_type == "analytics":
            self.conv.detail_nonsense_count = 0
            self._merge_context(output)
            output = self._rebuild_from_context(output)

        return output

    def _handle_output(self, output: RouterOutput) -> RouterResult:
        if output.message_type == "small_talk":
            self._log_transition(self.conv.state, self.conv.state, "small_talk")
            return RouterResult("greeting", None, {}, needs_data=True)

        if output.message_type == "help":
            self._log_transition(self.conv.state, self.conv.state, "help")
            return RouterResult("help", output.assistant_message, {})

        if output.message_type in {"out_of_scope", "ambiguous"}:
            if self.conv.state == State.DETAIL:
                return self._handle_detail_non_analytics(output)
            self._log_transition(self.conv.state, self.conv.state, output.message_type)
            return RouterResult("nonsense", output.assistant_message or _DIRECT_NONSENSE_MSG, {})

        self._merge_context(output)

        if output.requires_confirmation and output.complete:
            query = output.structured_query or _build_structured_query(output.target_mode, output.slots, {})
            mode = _mode_for_target(output.target_mode)
            params = _params_from_query(query)
            self.conv.pending_mode = mode
            self.conv.pending_params = params
            self.conv.last_structured_query = asdict(query)
            self._set_state(State.DETAIL, "requires_confirmation")
            return RouterResult(
                "confirm",
                output.assistant_message or "Bu sorguyu calistirmadan once onaylar misiniz?",
                self.conv.context.copy(),
            )

        if output.action == "ask_detail" or not output.complete:
            self.conv.pending_mode = None if output.target_mode == "none" else output.target_mode
            self._set_state(State.DETAIL, f"missing_slots_{','.join(output.missing_slots)}")
            return RouterResult("detail", _clarify_message(output), self.conv.context.copy())

        query = output.structured_query or _build_structured_query(output.target_mode, output.slots, {})
        params = _params_from_query(query)
        mode = _mode_for_target(output.target_mode)
        self.conv.pending_mode = mode
        self.conv.pending_params = params
        self.conv.last_structured_query = asdict(query)
        self._set_state(State.RESPONSE, f"ready_{output.target_mode}")
        logger.info("[router.ready] mode=%s structured_query=%s params=%s", mode, self.conv.last_structured_query, params)

        return RouterResult(
            mode=mode,
            response=_ON_IT_MSG,
            params=params,
            needs_data=True,
            structured_query=self.conv.last_structured_query,
        )

    def _handle_detail_non_analytics(self, output: RouterOutput) -> RouterResult:
        self.conv.detail_nonsense_count += 1
        if self.conv.detail_nonsense_count >= 2:
            self._go_direct("detail_non_analytics_limit")
            return RouterResult(
                "nonsense",
                output.assistant_message or "Sorguyu tamamlayamadim. Yeni bir NPS sorusu sorabilirsiniz.",
                {},
            )

        self._log_transition(self.conv.state, self.conv.state, output.message_type)
        return RouterResult(
            "detail",
            output.assistant_message or self._pending_detail_message(),
            self.conv.context.copy(),
        )

    def _pending_detail_message(self) -> str:
        if self.conv.pending_mode == "example":
            return "Yorumlari getirmek icin tarih, kategori, segment veya duygu gibi bir filtre belirtir misiniz?"
        if self.conv.pending_mode == "topic":
            return "Konu analizini tamamlamak icin tarih ve kategori/konu detayini belirtir misiniz?"
        if self.conv.pending_mode == "summary":
            return "Ozeti tamamlamak icin hangi donem icin bakacagimi belirtir misiniz?"
        return "Sorguyu netlestirmek icin biraz daha detay verir misiniz?"

    def _merge_context(self, output: RouterOutput):
        before = self.conv.context.copy()
        if output.structured_query:
            params = _params_from_query(output.structured_query)
            for key, value in params.items():
                if value is not None:
                    self.conv.context[key] = value
        for key, value in output.slots.items():
            if value is not None:
                self.conv.context[key] = value
        if before != self.conv.context:
            logger.info("[router.context] %s -> %s", before, self.conv.context)

    def _rebuild_from_context(self, output: RouterOutput) -> RouterOutput:
        slots = output.slots.copy()
        for key, value in self.conv.context.items():
            if slots.get(key) is None:
                slots[key] = value
        slots = _apply_context_year(slots, self.conv.context, self.conv.last_structured_query)
        date_range, _ = _normalize_date_expression(slots.get("date_expression"))
        if not date_range and slots.get("period"):
            date_range, _ = _normalize_date_expression(slots["period"])
        query = _build_structured_query(output.target_mode, slots, date_range)
        missing = [
            slot for slot in output.missing_slots
            if slot not in {"date_range", "date_year", "category", "filter", "target_mode"}
        ]
        if output.target_mode == "none":
            missing.append("target_mode")
        if output.target_mode in {"summary", "topic", "example"} and not date_range:
            if _contains_month_name(slots.get("date_expression")):
                missing.append("date_year")
            else:
                missing.append("date_range")
        if output.target_mode == "example" and not any([
            query.filters.get("category"),
            query.filters.get("nps_segment"),
            query.filters.get("emotion"),
            query.filters.get("comment_type"),
            query.filters.get("customer_id"),
        ]):
            missing.append("filter")
        output.slots = slots
        output.structured_query = query
        output.missing_slots = list(dict.fromkeys(missing))
        output.complete = not output.missing_slots
        output.action = "run_query" if output.complete else "ask_detail"
        return output

    def _log_decision(self, output: RouterOutput):
        logger.info(
            "[router.decision] state=%s source=%s message_type=%s target_mode=%s action=%s confidence=%s complete=%s missing=%s slots=%s",
            self.conv.state.name,
            output.source,
            output.message_type,
            output.target_mode,
            output.action,
            output.confidence,
            output.complete,
            output.missing_slots,
            output.slots,
        )

    def _log_transition(self, old_state: State, new_state: State, reason: str):
        logger.info(
            "[router.transition] %s -> %s reason=%s pending=%s context=%s",
            old_state.name,
            new_state.name,
            reason,
            self.conv.pending_mode,
            self.conv.context,
        )

    def _set_state(self, next_state: State, reason: str):
        old_state = self.conv.state
        self.conv.state = next_state
        self._log_transition(old_state, next_state, reason)

    def _go_direct(self, reason: str):
        old_state = self.conv.state
        self.conv.state = State.DIRECT
        self.conv.detail_nonsense_count = 0
        self.conv.pending_mode = None
        self.conv.pending_params = {}
        self.conv.last_structured_query = None
        self._log_transition(old_state, self.conv.state, reason)
