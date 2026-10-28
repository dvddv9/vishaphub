"""One request -> one pipeline run in a temporary folder. The API never writes to the disk."""

from __future__ import annotations

import tempfile
from pathlib import Path

from generator.api.errors import ApiError
from generator.api.llm_config import client_llm_config
from generator.api.rate_limit import RUN_LOCK
from generator.api.reports import report
from generator.config import DEFAULT_REPAIRS, MAX_REPAIRS, MAX_SPEC_CHARS
from generator.pipeline.orchestrator import run_pipeline


def handle_generate(body: dict, *, check_only: bool, run=run_pipeline, client_llm: bool = True,
                    loopback: bool = True, **run_kwargs) -> dict:
    spec_text = body.get("spec")
    if not isinstance(spec_text, str) or not spec_text.strip():
        raise ApiError(400, '"spec" must be the text of a spec.yaml')
    if len(spec_text) > MAX_SPEC_CHARS:
        raise ApiError(413, "spec is too long")
    repairs = body.get("repairs", DEFAULT_REPAIRS)
    if not isinstance(repairs, int) or isinstance(repairs, bool) or not 0 <= repairs <= MAX_REPAIRS:
        raise ApiError(400, f'"repairs" must be an integer from 0 to {MAX_REPAIRS}')
    gate = bool(body.get("gate", False))
    config = None
    if body.get("llm") is not None:
        if not client_llm:
            raise ApiError(403, "this server does not take model settings from the browser")
        config = client_llm_config(body["llm"], loopback)
    if not check_only and not RUN_LOCK.acquire(blocking=False):
        raise ApiError(429, "another run is in progress")
    try:
        with tempfile.TemporaryDirectory(prefix="vg-api-") as tmp:
            path = Path(tmp) / "spec.yaml"
            path.write_text(spec_text, encoding="utf-8")
            log: list[str] = []
            kwargs = dict(gate=gate, no_llm=check_only, repairs=repairs, allow_write=False,
                          require_coverage=bool(body.get("require_coverage", False)),
                          text_check=bool(body.get("text_check", True)), log=log.append)
            if config is not None:
                kwargs["config"] = config
            if body.get("no_analyzer"):
                kwargs["analyzer"] = None
            kwargs.update(run_kwargs)
            res = run(path, **kwargs)
    finally:
        if not check_only:
            RUN_LOCK.release()
    return report(res, log)
