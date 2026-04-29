"""
LLM bağlantı ayarları.

Varsayılan: Groq (ücretsiz, 128k context, OpenAI-uyumlu)
  GROQ_API_KEY=gsk_...          → console.groq.com'dan alınır
  LLM_MODEL=llama-3.1-8b-instant

On-prem geçişi için:
  OPENAI_API_KEY=...
  OPENAI_BASE_URL=http://your-onprem-host:port/v1
  LLM_MODEL=gpt-oss120b
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Groq öncelikli, yoksa OpenAI/on-prem
GROQ_KEY = os.getenv("GROQ_API_KEY", "")
OAI_KEY  = os.getenv("OPENAI_API_KEY", "")

API_KEY  = GROQ_KEY or OAI_KEY
BASE_URL = (
    "https://api.groq.com/openai/v1"
    if GROQ_KEY
    else os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
)
MODEL    = os.getenv("LLM_MODEL", "llama-3.1-8b-instant" if GROQ_KEY else "gpt-4o")
CTX_SIZE = int(os.getenv("LLM_CONTEXT_WINDOW", "131072"))


def get_client() -> OpenAI:
    return OpenAI(api_key=API_KEY, base_url=BASE_URL)


def chat(messages: list[dict], temperature: float = 0.2, max_tokens: int = 1024) -> str:
    client = get_client()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()
