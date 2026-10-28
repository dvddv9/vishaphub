"""One request -> one pipeline run in a temporary folder. The API never writes to the disk.

Two ways in: `handle_generate` answers when the run is over; `start_job` returns a job id at once and the run
goes on in a thread, so a browser can poll for the stage it is at (`POST /api/generate/async`,
`GET /api/jobs/<id>`). Both run the same code and give the same answer.
"""

from __future__ import annotations

import re
import tempfile
import threading
from pathlib import Path

from generator.api.errors import ApiError
from generator.api.job_store import JobStore
from generator.api.llm_config import client_llm_config
from generator.api.rate_limit import RUN_LOCK
from generator.api.reports import http_status, report
from generator.config import CANDIDATES_MAX, MAX_REPAIRS, MAX_SPEC_CHARS, MUTANTS_MAX
from generator.observability.logging import get_logger
from generator.pipeline.effort import EFFORTS
from generator.pipeline.orchestrator import run_pipeline

STAGE_TAG = re.compile(r"^\[(Intake|Design|Build|Verify|Repair|Deliver)\]")


def _prepare(body: dict, *, check_only: bool, client_llm: bool, loopback: bool) -> tuple[str, dict]:
    """Validate the request; returns the spec text and the keyword arguments for the run."""
    spec_text = body.get("spec")
    if not isinstance(spec_text, str) or not spec_text.strip():
        raise ApiError(400, '"spec" must be the text of a spec.yaml')
    if len(spec_text) > MAX_SPEC_CHARS:
        raise ApiError(413, "spec is too long")
    kwargs: dict = dict(gate=bool(body.get("gate", False)), no_llm=check_only, allow_write=False,
                        require_coverage=bool(body.get("require_coverage", False)),
                        strict=bool(body.get("strict", False)))
    repairs = body.get("repairs")            # absent: the effort decides
    if repairs is not None:
        if not isinstance(repairs, int) or isinstance(repairs, bool) or not 0 <= repairs <= MAX_REPAIRS:
            raise ApiError(400, f'"repairs" must be an integer from 0 to {MAX_REPAIRS}')
        kwargs["repairs"] = repairs
    effort = body.get("effort")
    if effort is not None:
        if effort not in EFFORTS:
            raise ApiError(400, f'"effort" must be one of: {", ".join(EFFORTS)}')
        kwargs["effort"] = effort
    candidates = body.get("candidates")
    if candidates is not None:
        if not isinstance(candidates, int) or isinstance(candidates, bool) or not 1 <= candidates <= CANDIDATES_MAX:
            raise ApiError(400, f'"candidates" must be an integer from 1 to {CANDIDATES_MAX}')
        kwargs["candidates"] = candidates
    mutants = body.get("mutants")
    if mutants is not None:
        if not isinstance(mutants, int) or isinstance(mutants, bool) or not 0 <= mutants <= MUTANTS_MAX:
            raise ApiError(400, f'"mutants" must be an integer from 0 to {MUTANTS_MAX}')
        kwargs["mutants"] = mutants
    if "text_check" in body:
        kwargs["text_check"] = bool(body["text_check"])
    if body.get("cove"):
        kwargs["cove"] = True
    if body.get("llm") is not None:
        if not client_llm:
            raise ApiError(403, "this server does not take model settings from the browser")
        config = client_llm_config(body["llm"], loopback)
        if config is not None:               # provider "server" means the server's own settings
            kwargs["config"] = config
    if body.get("no_analyzer"):
        kwargs["analyzer"] = None
    return spec_text, kwargs


def _execute(spec_text: str, kwargs: dict, run, log) -> dict:
    with tempfile.TemporaryDirectory(prefix="vg-api-") as tmp:
        path = Path(tmp) / "spec.yaml"
        path.write_text(spec_text, encoding="utf-8")
        lines: list[str] = []

        def both(line: str) -> None:
            lines.append(line)
            log(line)
        res = run(path, **kwargs, log=both)
    return report(res, lines)


def handle_generate(body: dict, *, check_only: bool, run=run_pipeline, client_llm: bool = True,
                    loopback: bool = True, **run_kwargs) -> dict:
    spec_text, kwargs = _prepare(body, check_only=check_only, client_llm=client_llm, loopback=loopback)
    kwargs.update(run_kwargs)
    if not check_only and not RUN_LOCK.acquire(blocking=False):
        raise ApiError(429, "another run is in progress")
    try:
        return _execute(spec_text, kwargs, run, lambda line: None)
    finally:
        if not check_only:
            RUN_LOCK.release()


def start_job(body: dict, store: JobStore, *, run=run_pipeline, client_llm: bool = True,
              loopback: bool = True, **run_kwargs) -> str:
    """Start a generate run in a thread; returns the job id. Raises ApiError like `handle_generate`."""
    spec_text, kwargs = _prepare(body, check_only=False, client_llm=client_llm, loopback=loopback)
    kwargs.update(run_kwargs)
    if not RUN_LOCK.acquire(blocking=False):
        raise ApiError(429, "another run is in progress")
    job = store.create()

    def work() -> None:
        logger = get_logger("jobs")
        store.start(job.id)
        try:
            def log(line: str) -> None:
                m = STAGE_TAG.match(line)
                store.append_log(job.id, line, m.group(1) if m else "")
            out = _execute(spec_text, kwargs, run, log)
            store.finish(job.id, out, http_status(out), out.get("error", ""))
        except Exception as e:          # the thread must always finish the job
            logger.exception("job %s failed", job.id[:6])
            store.finish(job.id, None, 500, f"{type(e).__name__}: {e}")
        finally:
            RUN_LOCK.release()

    try:
        threading.Thread(target=work, name=f"vg-job-{job.id[:6]}", daemon=True).start()
    except BaseException:
        RUN_LOCK.release()
        raise
    return job.id
