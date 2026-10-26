# src/api/llm_config.py
import os
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.auth import verify_api_key
from src.storage.settings import get_settings, update_settings

# Every route needs the API key (this router used to be open to anyone).
router = APIRouter(prefix="/llm", tags=["llm"], dependencies=[Depends(verify_api_key)])


def config_locked() -> bool:
    """True when the operator owns the LLM settings (public / demo deployments).

    Writing the server's LLM URL/key from the web would let any visitor redirect
    the operator's key to a host of their choosing, so in this mode callers use
    their own key per request instead (X-LLM-Api-Key + X-LLM-Provider).
    """
    from src.llm.client import require_user_key, server_key_only
    if server_key_only():
        return True
    flag = os.getenv("VISHAP_LLM_CONFIG_LOCKED", "").strip().lower() in ("1", "true", "yes", "on")
    return flag or require_user_key()


class LLMConfig(BaseModel):
    provider: str
    custom_url: str | None = None
    custom_model: str | None = None
    custom_key: str | None = None  # never returned in GET


@router.get("/config")
def read_config():
    if config_locked():
        from src.llm.client import server_key_only
        return {
            "server_key_only": server_key_only(),
            "locked": True,
            "provider": "",
            "custom_url": "",
            "custom_model": "",
            "has_custom_key": False,
        }
    s = get_settings()
    return {
        "locked": False,
        "provider": s.get("LLM_PROVIDER", os.getenv("LLM_PROVIDER", "custom")),
        "custom_url": s.get("CUSTOM_LLM_URL", os.getenv("CUSTOM_LLM_URL", "")),
        "custom_model": s.get("CUSTOM_LLM_MODEL", os.getenv("CUSTOM_LLM_MODEL", "")),
        "has_custom_key": bool(s.get("CUSTOM_LLM_KEY") or os.getenv("CUSTOM_LLM_KEY")),
    }


@router.post("/config")
def write_config(cfg: LLMConfig):
    if config_locked():
        raise HTTPException(
            403,
            "Server LLM settings are managed by the operator. "
            "Enter your own key and provider in the form instead.",
        )
    if cfg.provider not in ("custom", "anthropic", "android", "openai", "groq", "ollama", "mistral", "deepseek"):
        raise HTTPException(400, f"Unsupported provider: {cfg.provider}")
    patch = {"LLM_PROVIDER": cfg.provider}
    if cfg.provider in ("custom", "anthropic", "android", "openai", "groq", "ollama", "mistral", "deepseek"):
        if not cfg.custom_url:
            raise HTTPException(400, "custom_url required for custom/anthropic provider")
        if not cfg.custom_model:
            raise HTTPException(400, "custom_model required for custom/anthropic provider")
        if urlparse(cfg.custom_url).scheme not in ("http", "https"):
            raise HTTPException(400, "custom_url must start with http:// or https://")
        patch["CUSTOM_LLM_URL"] = cfg.custom_url
        patch["CUSTOM_LLM_MODEL"] = cfg.custom_model
        if cfg.custom_key:
            patch["CUSTOM_LLM_KEY"] = cfg.custom_key
    update_settings(patch)
    # apply to the current process
    for k, v in patch.items():
        os.environ[k] = v
    return {"status": "ok", "provider": cfg.provider}
