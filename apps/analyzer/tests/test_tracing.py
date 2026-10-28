# -*- coding: utf-8 -*-
"""Tests for OTel tracing (v6.1, fail-open)."""
from unittest.mock import patch

import pytest

from src.observability import tracing


@pytest.fixture(autouse=True)
def _reset():
    tracing._TRACER = None
    yield
    tracing._TRACER = None


def test_setup_tracing_no_crash(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    tracing.setup_tracing()  # must not raise


def test_get_tracer_returns_tracer():
    tracer = tracing.get_tracer()
    assert tracer is not None
    assert hasattr(tracer, "start_as_current_span")


def test_span_context_manager():
    with tracing.get_tracer().start_as_current_span("test_span"):
        pass


def test_fail_open_missing_otel(monkeypatch):
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    with patch("src.observability.tracing._load_otel", side_effect=ImportError("no otel")):
        tracing.setup_tracing()  # must not raise
    assert isinstance(tracing.get_tracer(), tracing._NoOpTracer)


def test_otel_disabled_env(monkeypatch):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    tracing.setup_tracing()
    assert isinstance(tracing.get_tracer(), tracing._NoOpTracer)
