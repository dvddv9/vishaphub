# apply_custom_llm.py
"""Adds an OpenAI-compatible LLM provider to Vishap."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# 1. src/llm/custom_client.py
CUSTOM_CLIENT = '''# src/llm/custom_client.py
import os
import httpx
from .client import LLMError

class CustomLLMClient:
    """OpenAI-compatible client (OpenAI, Mistral, Groq, Together, OpenRouter, etc.)."""
    def __init__(self):
        self.base_url = os.getenv("CUSTOM_LLM_URL", "https://api.openai.com/v1").rstrip("/")
        self.api_key = os.getenv("CUSTOM_LLM_KEY", "")
        self.model = os.getenv("CUSTOM_LLM_MODEL", "gpt-4o-mini")
        if not self.api_key:
            raise ValueError("CUSTOM_LLM_KEY is empty")
        self.client = httpx.Client(timeout=120.0)

    def chat(self, messages: list[dict]) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 4096,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        r = self.client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
        if r.status_code != 200:
            raise LLMError(f"{self.model}: HTTP {r.status_code}: {r.text[:200]}")
        return r.json()["choices"][0]["message"]["content"]
'''

# 2. src/llm/__init__.py
INIT_FILE = '''# src/llm/__init__.py
import os
from .client import DeepSeekClient
from .harness_client import HarnessClient
from .custom_client import CustomLLMClient

def get_llm_client():
    provider = os.getenv("LLM_PROVIDER", "deepseek").lower()
    if provider == "deepseek":
        return DeepSeekClient()
    elif provider == "harness":
        return HarnessClient()
    elif provider in ("custom", "openai-compatible"):
        return CustomLLMClient()
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider}")

__all__ = ["get_llm_client", "DeepSeekClient", "HarnessClient", "CustomLLMClient"]
'''

# 3. Env block
ENV_BLOCK = '''
# === LLM Provider ===
# Options: deepseek | harness | custom
LLM_PROVIDER=deepseek

# === Custom LLM (OpenAI-compatible) ===
# OpenAI:    CUSTOM_LLM_URL=https://api.openai.com/v1
# Groq:      CUSTOM_LLM_URL=https://api.groq.com/openai/v1
# Mistral:   CUSTOM_LLM_URL=https://api.mistral.ai/v1
# OpenRouter: CUSTOM_LLM_URL=https://openrouter.ai/api/v1
CUSTOM_LLM_URL=https://api.openai.com/v1
CUSTOM_LLM_KEY=
CUSTOM_LLM_MODEL=gpt-4o-mini
'''


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"[+] Written: {path.relative_to(ROOT)}")


def append_env_block(path: Path) -> None:
    if not path.exists():
        print(f"[!] Skipped (not found): {path.relative_to(ROOT)}")
        return
    text = path.read_text(encoding="utf-8")
    if "CUSTOM_LLM_URL" in text:
        print(f"[!] Already contains CUSTOM_LLM_URL: {path.relative_to(ROOT)}")
        return
    path.write_text(text.rstrip() + "\n" + ENV_BLOCK + "\n", encoding="utf-8")
    print(f"[+] Updated: {path.relative_to(ROOT)}")


def main() -> None:
    print("=== Adding Custom LLM Provider ===\n")
    write(ROOT / "src" / "llm" / "custom_client.py", CUSTOM_CLIENT)
    write(ROOT / "src" / "llm" / "__init__.py", INIT_FILE)
    append_env_block(ROOT / ".env.example")
    append_env_block(ROOT / ".env")
    print("\n=== Done ===")
    print("1. Edit .env: set LLM_PROVIDER=custom, fill CUSTOM_LLM_*")
    print("2. Restart API: python -m src.main")


if __name__ == "__main__":
    main()