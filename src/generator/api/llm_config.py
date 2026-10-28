"""Model settings that come with a request, and the /api/status answer."""

from __future__ import annotations

import importlib.util
import os
import shlex
import shutil

from generator.api.errors import ApiError
from generator.config import analyzer_command
from generator.llm import LLMConfigError, config_from_env
from generator.version import __version__

LLM_FIELDS = {"url": "CUSTOM_LLM_URL", "model": "CUSTOM_LLM_MODEL", "key": "CUSTOM_LLM_KEY",
              "thinking": "CUSTOM_LLM_THINKING"}


def client_llm_config(llm):
    """The model settings a request brings along, checked like the environment ones.

    They live for this one request only: nothing is stored, logged or returned.
    """
    if llm is None:
        return None
    if not isinstance(llm, dict):
        raise ApiError(400, '"llm" must be an object')
    env = {}
    for field, name in LLM_FIELDS.items():
        v = llm.get(field, "")
        if not isinstance(v, str):
            raise ApiError(400, f'"llm.{field}" must be text')
        env[name] = v
    try:
        return config_from_env(env)
    except LLMConfigError as e:
        raise ApiError(400, f"llm: {e}") from None


def status(token: str | None, client_llm: bool) -> dict:
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
        "token_required": bool(token),
        "analyzer_found": bool(cmd) and shutil.which(cmd[0]) is not None,
        "coverage": "package" if importlib.util.find_spec("coverage") else "built-in",
        "ruff_found": shutil.which("ruff") is not None,
        "stages": [{"key": s.key, "title": s.title, "prompts": list(s.prompts)} for s in STAGES],
    }
