# src/llm/__init__.py
import os
from .custom_client import CustomClient as CustomLLMClient
__all__ = [
    "CustomLLMClient",
]


def get_llm_client(api_key: str | None = None):
    """
    Returns a client object with a .chat(system, user) method,
    based on LLM_PROVIDER env variable.
    """
    provider = os.getenv("VISHAP_LLM_PROVIDER", "custom").strip().lower().lower()
