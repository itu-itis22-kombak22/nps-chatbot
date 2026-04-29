"""
Intent Router — State Machine

Diyagram akışı:
                         nonsense
                        ┌────────┐
                        ↓        │
user → prompt →  [DIRECT_ANSWER] ──proper question──→ [DETAIL_MODE]
                        ↑                                    │  ↑ nonsense (1-2x, parametric)
                        │        nonsense 3x, parametric ←──┘  │
                        │                                       │
                        └──────── response ←── [SUMMARY/TOPIC/EXAMPLE]

State geçişleri:
  DIRECT:
    - proper question  → DETAIL  (chatbot "on it!" veya ikinci soru sorar)
    - nonsense         → DIRECT  (kısa yönlendirme, sayaç tutulmaz)

  DETAIL:
    - "on it!" / clarification resolved → RESPONSE (summary|topic|example)
    - nonsense 1. ve 2. kez → DETAIL  (parametric uyarı)
    - nonsense 3. kez       → DIRECT  (parametric + sayaç sıfırlama)

  RESPONSE:
    - cevap üretildikten sonra → DIRECT  (otomatik)
"""

from __future__ import annotations

import re
import json
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Literal

from config.llm_config import chat

# ──────────────────────────────────────────────────────────────────────────────
# State ve Intent tanımları
# ──────────────────────────────────────────────────────────────────────────────

class State(Enum):
    DIRECT   = auto()   # başlangıç / idle
    DETAIL   = auto()   # kullanıcıdan detay bekleniyor / mode seçiliyor
    RESPONSE = auto()   # cevap üretildi, DIRECT'e dönülecek


ResponseMode = Literal["summary", "topic", "example"]


@dataclass
class ConversationState:
    state: State = State.DIRECT

    # DETAIL'daki nonsense sayacı (3'te DIRECT'e döner)
    detail_nonsense_count: int = 0

    # DETAIL modunda pending intent (örn: "summary" soru anlaşıldı ama tarih lazım)
    pending_intent: ResponseMode | None = None

    # Birikmiş filtreler (tarih, kategori, segment, duygu)
    context: dict = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────────────
# Sabit mesajlar
# ──────────────────────────────────────────────────────────────────────────────

_DIRECT_NONSENSE_MSG = (
    "Sorunuzu anlayamadım. NPS analizi, kategori bazlı sorgu veya örnek yorum "
    "konularında soru sorabilirsiniz."
)

_DETAIL_NONSENSE_1 = (
    "Bu yanıtı işleyemedim. Devam etmek için bir periyot (haftalık/aylık) veya "
    "kategori belirtebilirsiniz."
)

_DETAIL_NONSENSE_2 = (
    "⚠️ Yine anlayamadım. Lütfen net bir seçim yapın:\n"
    "• 'haftalık özet'\n"
    "• 'Mobil Bankacılık şikayetleri'\n"
    "• 'Kızgın müşterilerden örnek'"
)

_DETAIL_NONSENSE_3 = (
    "❌ Konuşmayı sıfırlıyorum. Yeni bir soru sorabilirsiniz.\n\n"
    "Örnek sorular:\n"
    "• 'Bu haftaki özet nedir?'\n"
    "• 'ATM şikayetleri hangi kategoride yoğunlaşıyor?'\n"
    "• 'Detractor'lardan örnek yorum göster.'"
)

_ON_IT_MSG = "Anlıyorum, hemen bakıyorum! 🔍"

# DETAIL modunda eksik bilgi istemek için kullanılır
_CLARIFY_TEMPLATES = {
    "summary": "Hangi dönem için özet istiyorsunuz? (haftalık / aylık / günlük)",
    "topic":   "Hangi kategori veya segment hakkında bilgi almak istiyorsunuz?",
    "example": "Hangi segment veya duygudan örnek yorumlar göstereyim? (Detractor, Kızgın, vb.)",
}


# ──────────────────────────────────────────────────────────────────────────────
# Kural tabanlı ön filtre
# ──────────────────────────────────────────────────────────────────────────────

_KW: dict[str, list[str]] = {
    "greeting": [
        "merhaba", "selam", "hey", "hi", "hello", "günaydın", "iyi günler",
        "iyi akşamlar", "nasılsın", "naber", "ne haber",
    ],
    "summary": [
        "özet", "özetle", "haftalık", "aylık", "günlük", "trend",
        "genel durum", "nasıl gidiyor", "rapor", "ne durumda",
    ],
    "topic": [
        "kategori", "konu", "segment", "dağılım", "şikayet", "memnuniyet",
        "mobil", "atm", "kartlar", "şube", "kredi", "borsa", "fon",
        "en çok", "hangi", "neden", "neden oluyor", "neyi şikayet",
    ],
    "example": [
        "örnek", "yorum göster", "listele", "bul", "benzer", "ne diyor",
        "müşteri ne diyor", "detractor yorum", "promoter yorum",
    ],
    "direct": [
        "kaç", "oran", "yüzde", "en yüksek", "en düşük", "toplam",
        "ortalama nps", "nps kaç",
    ],
}


def _keyword_intent(text: str) -> str | None:
    low = text.lower()
    for intent, keywords in _KW.items():
        if any(k in low for k in keywords):
            return intent
    if len(text.strip()) <= 3:
        return "nonsense"
    return None


# ──────────────────────────────────────────────────────────────────────────────
# LLM intent sınıflandırıcı
# ──────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
Sen bir banka NPS chatbot'unun intent sınıflandırıcısısın.
Kullanıcı mesajını analiz et ve SADECE aşağıdaki JSON formatında yanıt ver:

{
  "intent": "greeting" | "summary" | "topic" | "example" | "direct" | "nonsense",
  "confidence": 0.0-1.0,
  "complete": true | false,
  "params": {
    "period": "haftalık" | "aylık" | "günlük" | null,
    "category": "<ana kategori adı veya null>",
    "segment": "Detractor" | "Passive" | "Promoter" | null,
    "emotion": "<duygu adı veya null>"
  }
}

Açıklamalar:
- intent    : greeting=selamlama/tanışma/genel sohbet, summary=özet/rapor,
              topic=kategori/konu analizi, example=yorum göster,
              direct=sayısal/anlık soru, nonsense=NPS ile tamamen alakasız
- complete  : true → tüm gerekli parametreler mesajda mevcut (direkt cevap üretilebilir)
              false → eksik parametre var, detay sormak gerekiyor
- confidence: tahminin güven skoru

Sadece JSON döndür.
"""


def _llm_classify(text: str) -> dict:
    try:
        raw = chat(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": text},
            ],
            temperature=0.0,
            max_tokens=300,
        )
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return {"intent": "nonsense", "confidence": 0.0, "complete": False, "params": {}}


# ──────────────────────────────────────────────────────────────────────────────
# RouterResult
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class RouterResult:
    """
    mode      : Hangi moda yönlendirildi
    response  : Chatbot'un kullanıcıya söyleyeceği hazır metin (varsa)
                None ise ilgili mode modülü cevabı üretecek
    params    : Mode modülüne iletilecek parametreler
    needs_data: True ise mode modülü veri tabanından çekip cevap üretmeli
    """
    mode:       str
    response:   str | None
    params:     dict
    needs_data: bool = False


# ──────────────────────────────────────────────────────────────────────────────
# IntentRouter — State Machine
# ──────────────────────────────────────────────────────────────────────────────

class IntentRouter:
    """
    Kullanım:
        router = IntentRouter()
        result: RouterResult = router.process("Bu haftaki özet nedir?")
    """

    def __init__(self, use_llm: bool = True):
        self.conv = ConversationState()
        self.use_llm = use_llm

    # ── public API ────────────────────────────────────────────────────────────

    def process(self, user_message: str) -> RouterResult:
        text = user_message.strip()

        if self.conv.state == State.DIRECT:
            return self._handle_direct(text)
        elif self.conv.state == State.DETAIL:
            return self._handle_detail(text)
        else:
            # RESPONSE state'i dışarıda yönetilmeli; garanti için DIRECT'e dön
            self._go_direct()
            return self._handle_direct(text)

    def reset(self):
        self.conv = ConversationState()

    @property
    def current_state(self) -> State:
        return self.conv.state

    # ── State: DIRECT ─────────────────────────────────────────────────────────

    def _handle_direct(self, text: str) -> RouterResult:
        intent_data = self._classify(text)
        intent      = intent_data.get("intent", "nonsense")
        params      = intent_data.get("params", {})
        complete    = intent_data.get("complete", False)

        if intent == "nonsense":
            return RouterResult(mode="nonsense", response=_DIRECT_NONSENSE_MSG, params={})

        if intent == "greeting":
            # Selamlama → state değişmez, LLM'e bırak
            return RouterResult(mode="greeting", response=None, params={}, needs_data=True)

        # Geçerli NPS intent → context'i güncelle
        self._update_context(params)

        if complete:
            # Tüm parametreler var → "on it!" + direkt RESPONSE moduna geç
            self.conv.pending_intent = intent
            self.conv.state = State.RESPONSE
            return RouterResult(
                mode=intent,
                response=_ON_IT_MSG,
                params=self.conv.context.copy(),
                needs_data=True,
            )
        else:
            # Eksik parametre → DETAIL moduna geç, netleştirme sorusu sor
            self.conv.pending_intent = intent
            self.conv.state = State.DETAIL
            clarify_msg = _CLARIFY_TEMPLATES.get(intent, "Daha fazla detay verir misiniz?")
            return RouterResult(
                mode="detail",
                response=clarify_msg,
                params={},
            )

    # ── State: DETAIL ─────────────────────────────────────────────────────────

    def _handle_detail(self, text: str) -> RouterResult:
        intent_data = self._classify(text)
        intent      = intent_data.get("intent", "nonsense")
        params      = intent_data.get("params", {})

        if intent == "nonsense":
            self.conv.detail_nonsense_count += 1
            n = self.conv.detail_nonsense_count

            if n == 1:
                return RouterResult(mode="nonsense", response=_DETAIL_NONSENSE_1, params={})
            elif n == 2:
                return RouterResult(mode="nonsense", response=_DETAIL_NONSENSE_2, params={})
            else:
                # 3. nonsense → DIRECT'e dön, sıfırla
                self._go_direct()
                return RouterResult(mode="nonsense", response=_DETAIL_NONSENSE_3, params={})

        # Geçerli yanıt → sayacı sıfırla, context güncelle
        self.conv.detail_nonsense_count = 0
        self._update_context(params)

        # Bekleyen intent'i koru, eğer yeni intent geldiyse güncelle
        final_intent = (
            intent if intent not in ("direct",) else self.conv.pending_intent
        ) or intent

        self.conv.pending_intent = final_intent
        self.conv.state = State.RESPONSE

        return RouterResult(
            mode=final_intent,
            response=_ON_IT_MSG,
            params=self.conv.context.copy(),
            needs_data=True,
        )

    # ── Yardımcılar ───────────────────────────────────────────────────────────

    def _classify(self, text: str) -> dict:
        """Önce keyword, yetersizse LLM."""
        quick = _keyword_intent(text)
        if quick and quick != "nonsense":
            # Keyword eşleşti ama parametreleri LLM'den iste
            if self.use_llm:
                return _llm_classify(text)
            # LLM yok → keyword var ama parametre bilinmiyor → DETAIL'a düş
            return {"intent": quick, "confidence": 0.7, "complete": False, "params": {}}
        if quick == "nonsense":
            return {"intent": "nonsense", "confidence": 1.0, "complete": False, "params": {}}
        # Keyword bulunamadı
        if self.use_llm:
            return _llm_classify(text)
        return {"intent": "nonsense", "confidence": 0.3, "complete": False, "params": {}}

    def _update_context(self, params: dict):
        for k, v in params.items():
            if v is not None:
                self.conv.context[k] = v

    def _go_direct(self):
        self.conv.state = State.DIRECT
        self.conv.detail_nonsense_count = 0
        self.conv.pending_intent = None
