# src/api/llm_config.py
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.storage.settings import get_settings, update_settings

router = APIRouter(prefix="/llm", tags=["llm"])


class LLMConfig(BaseModel):
    provider: str
    custom_url: str | None = None
    custom_model: str | None = None
    custom_key: str | None = None  # never returned in GET


@router.get("/config")
def read_config():
    s = get_settings()
    return {
        "provider": s.get("LLM_PROVIDER", os.getenv("LLM_PROVIDER", "custom")),
        "custom_url": s.get("CUSTOM_LLM_URL", os.getenv("CUSTOM_LLM_URL", "")),
        "custom_model": s.get("CUSTOM_LLM_MODEL", os.getenv("CUSTOM_LLM_MODEL", "")),
        "has_custom_key": bool(s.get("CUSTOM_LLM_KEY") or os.getenv("CUSTOM_LLM_KEY")),
    }


@router.post("/config")
def write_config(cfg: LLMConfig):
    if cfg.provider not in ("custom", "anthropic", "android", "openai", "groq", "ollama", "mistral", "deepseek"):
        raise HTTPException(400, f"Unsupported provider: {cfg.provider}")
    patch = {"LLM_PROVIDER": cfg.provider}
    if cfg.provider in ("custom", "anthropic", "android", "openai", "groq", "ollama", "mistral", "deepseek"):
        if not cfg.custom_url:
            raise HTTPException(400, "custom_url required for custom/anthropic provider")
        if not cfg.custom_model:
            raise HTTPException(400, "custom_model required for custom/anthropic provider")
        patch["CUSTOM_LLM_URL"] = cfg.custom_url
        patch["CUSTOM_LLM_MODEL"] = cfg.custom_model
        if cfg.custom_key:
            patch["CUSTOM_LLM_KEY"] = cfg.custom_key
    update_settings(patch)
    # apply to the current process
    for k, v in patch.items():
        os.environ[k] = v
    return {"status": "ok", "provider": cfg.provider}
