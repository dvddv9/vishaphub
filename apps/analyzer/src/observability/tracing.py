# -*- coding: utf-8 -*-
"""OpenTelemetry tracing (v6.1), fail-open.

If OTel is missing (or ``OTEL_SDK_DISABLED=true``), every helper degrades to a
no-op so the app and the test suite keep working without a tracing backend.
"""
import asyncio
import functools
import logging
import os
from contextlib import contextmanager

log = logging.getLogger(__name__)

_TRACER = None


class _NoOpSpan:
    """Minimal no-op span (supports ``with`` + attribute setters)."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def set_attribute(self, *args, **kwargs):
        return self

    def record_exception(self, *args, **kwargs):
        return self


class _NoOpTracer:
    """No-op tracer used when OTel is unavailable."""

    def start_as_current_span(self, name, *args, **kwargs):
        return _NoOpSpan()


def _otel_disabled() -> bool:
    return os.getenv("OTEL_SDK_DISABLED", "").lower() in ("1", "true", "yes")


def _load_otel():
    """Import the OTel SDK modules; raise ImportError when unavailable."""
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    return trace, Resource, TracerProvider, BatchSpanProcessor


def setup_tracing(service_name: str | None = None) -> None:
    """Initialize OTel tracing; no-op if OTel is missing or disabled."""
    global _TRACER
    if _TRACER is not None:
        return
    name = service_name or os.getenv("OTEL_SERVICE_NAME", "vishap")
    if _otel_disabled():
        log.info("OTel tracing disabled via OTEL_SDK_DISABLED")
        return
    try:
        trace, Resource, TracerProvider, BatchSpanProcessor = _load_otel()
    except ImportError as e:
        log.warning("OTel not available, tracing disabled: %s", e)
        return
    try:
        provider = TracerProvider(resource=Resource.create({"service.name": name}))
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint.rstrip("/") + "/v1/traces"))
            )
        except ImportError:
            log.info("OTLP exporter not installed; spans kept in-memory")
        trace.set_tracer_provider(provider)
        _TRACER = trace.get_tracer(name)
        log.info("OTel tracing initialized (service=%s)", name)
    except Exception as e:  # pragma: no cover - defensive
        log.warning("OTel setup failed, tracing disabled: %s", e)


def get_tracer(name: str | None = None):
    """Return the configured tracer, or a no-op tracer when OTel is absent."""
    if _TRACER is not None:
        return _TRACER
    return _NoOpTracer()


@contextmanager
def span(name: str, **attributes):
    """Context manager for a span (no-op when tracing is unavailable)."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as sp:
        for key, value in attributes.items():
            try:
                sp.set_attribute(key, value)
            except Exception:
                pass
        yield sp


def traced(name: str | None = None):
    """Decorator that wraps a sync/async function in a span."""
    def decorator(fn):
        span_name = name or fn.__name__
        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                with span(span_name):
                    return await fn(*args, **kwargs)

            return async_wrapper

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with span(span_name):
                return fn(*args, **kwargs)

        return wrapper

    return decorator
