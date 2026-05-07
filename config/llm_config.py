"""
LLM baglanti ayarlari.

Varsayilan endpoint LiteLLM uzerinden kurum ici modele gider:
  LITELLM_URL=https://litellm.fibabanka.local/v1/chat/completions
  LITELLM_API_KEY=...
  LLM_MODEL=openai/gpt-oss-120b
"""

from __future__ import annotations

import os
import logging

try:
    import httpx
except ImportError:
    httpx = None

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False


load_dotenv()

logger = logging.getLogger("nps_chatbot.llm")

URL = os.getenv("LITELLM_URL", "https://litellm.fibabanka.local/v1/chat/completions")
API_KEY = os.getenv("LITELLM_API_KEY", "")
MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
TIMEOUT = float(os.getenv("LITELLM_TIMEOUT", "60"))
VERIFY_SSL = os.getenv("LITELLM_VERIFY_SSL", "false").lower() in {"1", "true", "yes", "on"}
CTX_SIZE = int(os.getenv("LLM_CONTEXT_WINDOW", "131072"))


def _headers() -> dict[str, str]:
    if not API_KEY:
        raise RuntimeError("LITELLM_API_KEY tanimli degil. Key'i .env dosyasina manuel ekleyin.")

    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }


def chat(messages: list[dict], temperature: float = 0.2, max_tokens: int = 1024) -> str:
    if httpx is None:
        raise RuntimeError("httpx paketi kurulu degil. `pip install -r requirements.txt` calistirin.")

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    with httpx.Client(verify=VERIFY_SSL, timeout=TIMEOUT) as client:
        logger.debug(
            "[http] post url=%s model=%s message_count=%s max_tokens=%s temperature=%s verify_ssl=%s",
            URL,
            MODEL,
            len(messages),
            max_tokens,
            temperature,
            VERIFY_SSL,
        )
        response = client.post(URL, headers=_headers(), json=payload)
        logger.debug("[http] status=%s", response.status_code)
        response.raise_for_status()
        data = response.json()

    content = data["choices"][0]["message"]["content"].strip()
    logger.debug("[http] response_chars=%s", len(content))
    return content
