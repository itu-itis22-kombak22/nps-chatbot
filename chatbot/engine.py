"""
Chatbot Engine — IntentRouter + mode modüllerini birleştirir.

Kullanım:
    from chatbot.engine import NPSChatbot
    bot = NPSChatbot()
    print(bot.chat("Merhaba!"))
    print(bot.chat("Bu haftaki özet nedir?"))
"""

from __future__ import annotations
import argparse
import json
import logging
import sys

from chatbot.intent_router import IntentRouter, RouterResult, State

logger = logging.getLogger("nps_chatbot.engine")

# Chatbot'un genel kimliği — tüm LLM çağrılarında kullanılır
_BOT_SYSTEM = """\
Sen bir bankanın NPS (Net Promoter Score) analiz chatbot'usun.
Müşteri geri bildirimlerini analiz eder, trend ve kategori bazlı sorulara cevap verirsin.
Türkçe konuş; doğal, akıcı ve gerektiğinde kısa takip soruları soran bir chatbot gibi davran.
Kullanıcı NPS dışına çıkarsa sohbeti nazikçe müşteri geri bildirimi, NPS, kategori, duygu,
trend veya örnek yorum analizine geri yönlendir. Kullanıcı NPS analizi istediğinde, öncelikle hangi tarih aralığı için istediğini öğrenmeye çalış, sonrasında NPS skor aralığını sor, en son kategori duygu durumu ve yorum tipi üzerine sorular sorabilirsin isteği netleştirmek için. 
"""


class NPSChatbot:
    def __init__(self):
        self.router = IntentRouter()
        self.last_debug_json: dict | None = None
        self._history: list[dict] = []   # konuşma geçmişi (LLM context için)

    def chat(self, user_message: str) -> str:
        logger.info("[chat] received chars=%s", len(user_message))
        result: RouterResult = self.router.process(user_message)
        self.last_debug_json = self.router.last_debug_json
        logger.info(
            "[chat] router_result mode=%s needs_data=%s params=%s response_preview=%r",
            result.mode,
            result.needs_data,
            result.params,
            (result.response or "")[:120],
        )

        # Veri gerektirmeyen turlarda router sadece akışı belirler; metni mümkün olduğunca LLM üretir.
        if not result.needs_data:
            response = result.response or self._llm_respond(user_message)
            self._add_to_history(user_message, response)
            return response

        # Veri gerektiren modlar
        if result.needs_data:
            mode_response = self._dispatch(result, user_message)
            old_state = self.router.conv.state
            self.router.conv.state = State.DIRECT
            self.router.conv.detail_nonsense_count = 0
            logger.info(
                "[transition] %s -> %s reason=response_complete",
                old_state.name,
                self.router.conv.state.name,
            )
            self._add_to_history(user_message, mode_response)
            return mode_response

        return self._llm_respond(user_message)

    def _dispatch(self, result: RouterResult, user_message: str) -> str:
        mode = result.mode
        logger.info("[dispatch] mode=%s params=%s", mode, result.params)

        try:
            if mode == "greeting":
                return self._llm_respond(user_message)

            if mode == "summary":
                from chatbot.modes import summary
                return summary.respond(result.params)

            if mode == "topic":
                from chatbot.modes import topic
                return topic.respond(result.params)

            if mode == "example":
                from chatbot.modes import example
                return example.respond(result.params)

            return self._llm_respond(user_message)
        except ModuleNotFoundError as e:
            return (
                f"Eksik Python paketi: {e.name}. "
                "`pip install -r requirements.txt` çalıştırıp tekrar deneyin."
            )

    def _llm_respond(self, user_message: str) -> str:
        """
        Genel LLM cevabı — greeting, chitchat veya fallback için.
        Konuşma geçmişini (son 6 tur) context olarak taşır.
        """
        messages = [{"role": "system", "content": _BOT_SYSTEM}]
        messages += self._history[-6:]   # son 6 mesaj context
        messages.append({"role": "user", "content": user_message})
        try:
            from config.llm_config import chat as llm_chat
            logger.info("[llm_response] request message_count=%s history_items=%s", len(messages), len(self._history[-6:]))
            response = llm_chat(messages, temperature=0.5, max_tokens=512)
            logger.info("[llm_response] success chars=%s", len(response))
            return response
        except Exception as e:
            logger.warning("[llm_response] error=%s", e)
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
        self.last_debug_json = None
        logger.info("[chat] history_reset")


def _format_debug_json(payload: dict | None) -> str:
    if payload is None:
        return "{}"
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="NPS Chatbot terminal arayuzu",
    )
    parser.add_argument(
        "--log-level",
        default="ERROR",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Terminal log seviyesi.",
    )
    parser.add_argument(
        "--show-json",
        action="store_true",
        help="Her cevaptan sonra state ve final parametre JSON'larini yazdirir.",
    )
    parser.add_argument(
        "--router-debug",
        action="store_true",
        help="Geriye uyumlu kisa yol: --show-json ile ayni iki JSON ciktisini acar.",
    )
    args = parser.parse_args()
    show_json = args.show_json or args.router_debug
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    logging.getLogger("nps_chatbot.llm").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    bot = NPSChatbot()
    exit_commands = {"exit", "quit", "q", "çık", "cikis"}

    print("NPS Chatbot CLI")
    print("Mesajinizi yazin. Cikmak icin: exit, quit, q, cikis veya çık")
    print("Konusma hafizasini sifirlamak icin: reset")
    print()

    while True:
        try:
            user_message = input("Sen> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGorusmek uzere.")
            break

        if not user_message:
            continue

        command = user_message.casefold()
        if command in exit_commands:
            print("Gorusmek uzere.")
            break

        if command == "reset":
            bot.reset()
            print("Bot> Konusma hafizasi sifirlandi.")
            continue

        response = bot.chat(user_message)
        print(f"\nBot> {response}\n")
        if show_json:
            debug_json = bot.last_debug_json or {}
            print(_format_debug_json(debug_json.get("state_json")))
            print(_format_debug_json(debug_json.get("final_json")))
            print()


if __name__ == "__main__":
    main()
