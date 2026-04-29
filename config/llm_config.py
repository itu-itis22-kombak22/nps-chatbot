"""
LLM bağlantı ayarları.
On-prem / kurum içi OpenAI-uyumlu endpoint desteği.

.env dosyasına ekle:
    OPENAI_API_KEY=...
    OPENAI_BASE_URL=http://your-onprem-host:port/v1
    LLM_MODEL=gpt-oss120b          # ya da sunucudaki model adı
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY  = os.getenv("OPENAI_API_KEY", "")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL    = os.getenv("LLM_MODEL", "gpt-4o")
CTX_SIZE = int(os.getenv("LLM_CONTEXT_WINDOW", "128000"))


def get_client() -> OpenAI:
    """On-prem veya OpenAI endpoint'e bağlı istemci döndürür."""
    return OpenAI(api_key=API_KEY, base_url=BASE_URL)


def chat(messages: list[dict], temperature: float = 0.2, max_tokens: int = 1024) -> str:
    """
    Tek seferlik chat çağrısı.
    messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
    """
    client = get_client()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()
