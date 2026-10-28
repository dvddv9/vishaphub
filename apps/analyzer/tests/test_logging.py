# -*- coding: utf-8 -*-
"""Tests for structlog-based observability (v6.1).

Covers setup_logging (pretty/json), level filtering, contextvars binding,
job-store logging, and orchestrator stage logging.
"""
import contextlib
import io
import json
from unittest.mock import patch

import pytest
import structlog
from structlog.testing import capture_logs

from src.observability.logging import (
    setup_logging,
    get_logger,
    bind_job_id,
    bind_request_id,
    clear_context,
)
from src.api.job_store import JobStatus
from src.api.job_store_memory import InMemoryJobStore
from src.pipeline import orchestrator


@pytest.fixture(autouse=True)
def _reset_structlog():
    """Isolate structlog global config + contextvars between tests."""
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()
    structlog.reset_defaults()


# --- setup / format --------------------------------------------------------

def test_setup_logging_pretty_format():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        setup_logging(fmt="pretty")
        log = get_logger()
        log.info("pretty_event", key="value")
    assert "pretty_event" in buf.getvalue()


def test_setup_logging_json_format():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        setup_logging(fmt="json")
        get_logger().info("json_event", key="value")
    line = buf.getvalue().strip().splitlines()[-1]
    parsed = json.loads(line)
    assert parsed["event"] == "json_event"


def test_json_has_level_and_timestamp():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        setup_logging(fmt="json")
        get_logger().info("x")
    parsed = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert "level" in parsed
    assert "timestamp" in parsed


def test_json_has_event():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        setup_logging(fmt="json")
        get_logger().info("evt123")
    parsed = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert "event" in parsed
    assert parsed["event"] == "evt123"


def test_log_level_filters_debug():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        setup_logging(level="INFO", fmt="pretty")
        log = get_logger()
        log.debug("debug_should_not_appear")
        log.info("info_should_appear")
    out = buf.getvalue()
    assert "debug_should_not_appear" not in out
    assert "info_should_appear" in out


def test_log_level_allows_error():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        setup_logging(level="INFO", fmt="pretty")
        get_logger().error("error_should_appear")
    assert "error_should_appear" in buf.getvalue()


def test_get_logger_returns_bound():
    logger = get_logger("mylogger")
    assert logger is not None
    assert hasattr(logger, "info")
    with capture_logs() as cap:
        logger.info("bound_check")
    assert any(e["event"] == "bound_check" for e in cap)


# --- contextvars -----------------------------------------------------------

def test_bind_job_id_in_context():
    log = get_logger()
    bind_job_id("job-1")
    try:
        with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as cap:
            log.info("with_job")
        assert any(e.get("job_id") == "job-1" for e in cap)
    finally:
        clear_context()


def test_bind_request_id_in_context():
    log = get_logger()
    bind_request_id("req-1")
    try:
        with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as cap:
            log.info("with_req")
        assert any(e.get("request_id") == "req-1" for e in cap)
    finally:
        clear_context()


def test_clear_context():
    log = get_logger()
    bind_job_id("job-9")
    clear_context()
    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as cap:
        log.info("no_job")
    assert all("job_id" not in e for e in cap)


def test_exception_logged_with_traceback():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        setup_logging(fmt="pretty")
        log = get_logger()
        try:
            1 / 0
        except ZeroDivisionError:
            log.error("boom", exc_info=True)
    assert "ZeroDivisionError" in buf.getvalue()


# --- job store (memory) ----------------------------------------------------

@pytest.mark.asyncio
async def test_job_store_memory_logs_create():
    store = InMemoryJobStore()
    with capture_logs() as cap:
        await store.create("x.py")
    assert any(e["event"] == "job_created" for e in cap)


@pytest.mark.asyncio
async def test_job_store_memory_logs_update():
    store = InMemoryJobStore()
    job = await store.create("x.py")
    with capture_logs() as cap:
        await store.update(job.job_id, status=JobStatus.RUNNING)
    assert any(e["event"] == "job_updated" for e in cap)


@pytest.mark.asyncio
async def test_job_store_memory_logs_delete():
    store = InMemoryJobStore()
    job = await store.create("x.py")
    with capture_logs() as cap:
        await store.delete(job.job_id)
    assert any(e["event"] == "job_deleted" for e in cap)


# --- orchestrator stage logging -------------------------------------------

MOCK_STAGE0 = {
    "level": "D0",
    "route": [],
    "research_first": False,
    "subst_count": 0,
    "flags": [],
    "_meta": {"tokens_in": 10, "tokens_out": 5},
}
MOCK_STAGE1 = {"files": [], "deps": [], "_meta": {"tokens_in": 10, "tokens_out": 5}}
MOCK_STAGE2 = {"risk_nodes": [], "resilience_score": 8, "_meta": {}}
MOCK_STAGE4 = {"options": [], "force_emergency": False, "_meta": {}}
MOCK_STAGE5 = (
    "# D0 — foo()\n\n"
    "[CONCLUSION] Test conclusion.\n"
    "[RISK] No risks.\n"
    "[FUNC:FULL]\n"
    "- ECON: effort ~5 min, cost $0, ROI high.\n"
)


@patch("src.pipeline.orchestrator.stage5_transmitter", return_value=MOCK_STAGE5)
@patch("src.pipeline.orchestrator.stage4_synthesizer", return_value=MOCK_STAGE4)
@patch("src.pipeline.orchestrator.stage2_analyst", return_value=MOCK_STAGE2)
@patch("src.pipeline.orchestrator.stage1_scanner", return_value=MOCK_STAGE1)
@patch("src.pipeline.orchestrator.stage0_orchestrator", return_value=MOCK_STAGE0)
def test_orchestrator_logs_stage(s0, s1, s2, s4, s5):
    with capture_logs() as cap:
        orchestrator.run_pipeline("def foo(): pass", "a.py", verbose=False)
    events = [e["event"] for e in cap]
    assert "stage_started" in events
    assert "stage_done" in events
    assert "pipeline_done" in events
