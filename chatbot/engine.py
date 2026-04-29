"""
Chatbot Engine — IntentRouter + mode modüllerini birleştirir.

Kullanım:
    from chatbot.engine import NPSChatbot
    bot = NPSChatbot()
    print(bot.chat("Merhaba!"))
    print(bot.chat("Bu haftaki özet nedir?"))
"""

from __future__ import annotations
from chatbot.intent_router import IntentRouter, RouterResult, State
from chatbot.modes import summary, topic, example
from config.llm_config import chat as llm_chat

# Chatbot'un genel kimliği — tüm LLM çağrılarında kullanılır
_BOT_SYSTEM = """\
Sen bir bankanın NPS (Net Promoter Score) analiz chatbot'usun.
Müşteri geri bildirimlerini analiz eder, trend ve kategori bazlı sorulara cevap verirsin.
Türkçe konuş, sade ve profesyonel ol.
Selamlama veya genel sorularda kısaca kendini tanıt ve ne yapabileceğini söyle.
"""


class NPSChatbot:
    def __init__(self, use_llm: bool = True):
        self.router = IntentRouter(use_llm=use_llm)
        self.use_llm = use_llm
        self._history: list[dict] = []   # konuşma geçmişi (LLM context için)

    def chat(self, user_message: str) -> str:
        result: RouterResult = self.router.process(user_message)

        # Veri gerektirmeyen hazır mesajlar (nonsense, clarify soruları)
        if result.response is not None and not result.needs_data:
            self._add_to_history(user_message, result.response)
            return result.response

        # Veri gerektiren modlar
        if result.needs_data:
            mode_response = self._dispatch(result, user_message)
            self.router.conv.state = State.DIRECT
            self.router.conv.detail_nonsense_count = 0
            self._add_to_history(user_message, mode_response)
            return mode_response

        return result.response or "Bir hata oluştu, lütfen tekrar deneyin."

    def _dispatch(self, result: RouterResult, user_message: str) -> str:
        mode = result.mode

        if mode == "greeting":
            return self._llm_respond(user_message)

        if mode == "summary":
            return summary.respond(result.params)

        if mode == "topic":
            return topic.respond(result.params)

        if mode == "example":
            return example.respond(result.params)

        if mode == "direct":
            return summary.respond(result.params)

        return self._llm_respond(user_message)

    def _llm_respond(self, user_message: str) -> str:
        """
        Genel LLM cevabı — greeting, chitchat veya fallback için.
        Konuşma geçmişini (son 6 tur) context olarak taşır.
        """
        if not self.use_llm:
            return (
                "Merhaba! Ben NPS analiz chatbot'uyum. "
                "Müşteri yorumları, NPS trend ve kategori analizleri konusunda yardımcı olabilirim."
            )
        messages = [{"role": "system", "content": _BOT_SYSTEM}]
        messages += self._history[-6:]   # son 6 mesaj context
        messages.append({"role": "user", "content": user_message})
        try:
            return llm_chat(messages, temperature=0.5, max_tokens=512)
        except Exception as e:
            return f"LLM bağlantı hatası: {e}"

    def _add_to_history(self, user_msg: str, assistant_msg: str):
        self._history.append({"role": "user",      "content": user_msg})
        self._history.append({"role": "assistant",  "content": assistant_msg})
        # Max 20 tur tut (40 mesaj)
        if len(self._history) > 40:
            self._history = self._history[-40:]

    def reset(self):
        self.router.reset()
        self._history = []
