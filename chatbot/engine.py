"""
Chatbot Engine — IntentRouter + mode modüllerini birleştirir.

Kullanım:
    from chatbot.engine import NPSChatbot
    bot = NPSChatbot()
    print(bot.chat("Bu haftaki özet nedir?"))
"""

from __future__ import annotations
from chatbot.intent_router import IntentRouter, RouterResult, State
from chatbot.modes import summary, topic, example


class NPSChatbot:
    def __init__(self, use_llm: bool = True):
        self.router = IntentRouter(use_llm=use_llm)

    def chat(self, user_message: str) -> str:
        result: RouterResult = self.router.process(user_message)

        # Hazır mesaj varsa direkt dön (nonsense, clarify, "on it!")
        if result.response is not None and not result.needs_data:
            return result.response

        # Veri gerektiren mode → ilgili modülü çağır
        if result.needs_data:
            mode_response = self._dispatch(result)
            # Cevap üretildi, state'i DIRECT'e döndür
            self.router.conv.state = State.DIRECT
            self.router.conv.detail_nonsense_count = 0

            # "on it!" varsa önce göster, sonra asıl cevap
            if result.response:
                return f"{result.response}\n\n{mode_response}"
            return mode_response

        return result.response or "Bir hata oluştu, lütfen tekrar deneyin."

    def _dispatch(self, result: RouterResult) -> str:
        mode   = result.mode
        params = result.params

        if mode == "summary":
            return summary.respond(params)
        elif mode == "topic":
            return topic.respond(params)
        elif mode == "example":
            return example.respond(params)
        elif mode == "direct":
            # Direct sorular da summary modülü ile karşılanır (istatistik bazlı)
            return summary.respond(params)
        else:
            return "Bu isteği işleyemedim."

    def reset(self):
        self.router.reset()
