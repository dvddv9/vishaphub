# -*- coding: utf-8 -*-
"""LLM mode: custom (OpenAI-compatible) — only valid mode (v7.3.5)."""
import json

from src.config import DATA_DIR

MODE_FILE = DATA_DIR / "mode.json"
DEFAULT_MODE = "custom"
VALID_MODES = ("custom", "openai", "groq", "ollama", "anthropic", "android")


def get_mode() -> str:
    try:
        if MODE_FILE.exists():
            with open(MODE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                mode = data.get("mode", DEFAULT_MODE)
                if mode in VALID_MODES:
                    return mode
    except Exception:
        pass
    return DEFAULT_MODE


def set_mode(mode: str) -> bool:
    if mode not in VALID_MODES:
        return False
    try:
        MODE_FILE.parent.mkdir(exist_ok=True)
        with open(MODE_FILE, "w", encoding="utf-8") as f:
            json.dump({"mode": mode}, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False
