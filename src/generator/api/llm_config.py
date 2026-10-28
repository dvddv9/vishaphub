"""Model settings that come with a request, and the /api/status answer."""

from __future__ import annotations

import importlib.util
import shlex
import shutil

from generator.api.errors import ApiError
from generator.config import analyzer_command
from generator.llm import LLMConfigError, config_from_env
from generator.llm.providers import ProviderError, config_for, list_providers
from generator.version import __version__

LLM_FIELDS = ("provider", "model", "key", "thinking")


def client_llm_config(llm, loopback: bool = False):
    """The model settings a request brings along: a provider id, a model, a key.

    The URL is never taken from a request (see llm/providers.py): the browser picks a provider from the
    server's allow-list. The settings live for this one request only: nothing is stored, logged or returned.
    """
    if llm is None:
        return None
    if not isinstance(llm, dict):
        raise ApiError(400, '"llm" must be an object')
    if "url" in llm:
        raise ApiError(400, 'llm: a request cannot name a URL; pick a "provider" (see /api/providers)')
    values = {}
    for field in LLM_FIELDS:
        v = llm.get(field, "")
        if not isinstance(v, str):
            raise ApiError(400, f'"llm.{field}" must be text')
        values[field] = v
    try:
        return config_for(values["provider"], values["model"], values["key"], values["thinking"], loopback)
    except (ProviderError, LLMConfigError) as e:
        raise ApiError(400, f"llm: {e}") from None


def status(token: str | None, client_llm: bool, loopback: bool = True, check_only: bool = False) -> dict:
    from generator.pipeline.stages import STAGES
    try:
        config_from_env()
        llm_env = True
    except LLMConfigError:
        llm_env = False
    cmd = shlex.split(analyzer_command())
    return {
        "version": __version__,
        "llm_from_environment": llm_env,
        "client_llm_allowed": client_llm,
        "providers": list_providers(loopback) if client_llm else [],
        "token_required": bool(token),
        "check_only": check_only,
        "analyzer_found": bool(cmd) and shutil.which(cmd[0]) is not None,
        "coverage": "package" if importlib.util.find_spec("coverage") else "built-in",
        "ruff_found": shutil.which("ruff") is not None,
        "stages": [{"key": s.key, "title": s.title, "prompts": list(s.prompts)} for s in STAGES],
    }
