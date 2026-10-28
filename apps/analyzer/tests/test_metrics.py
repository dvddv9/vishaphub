# -*- coding: utf-8 -*-
"""Tests for Prometheus /metrics endpoint (v6.1 Block 3)."""
from datetime import datetime, UTC, timedelta

import pytest
from fastapi.testclient import TestClient

from src.observability import metrics
from src.api.job_store import JobStatus
from src.api.job_store_memory import InMemoryJobStore


def _val(name, labels):
    return metrics.get_sample_value(name, labels)


@pytest.fixture
def client():
    from src.main import app
    return TestClient(app)


# --- endpoint ---

def test_metrics_endpoint_exists(client):
    r = client.get("/metrics")
    assert r.status_code == 200


def test_metrics_content_type(client):
    r = client.get("/metrics")
    assert r.headers["content-type"].startswith("text/plain; version=0.0.4")


# --- job counters ---

@pytest.mark.asyncio
async def test_jobs_created_counter_increments():
    store = InMemoryJobStore()
    before = _val("vishap_jobs_created_total", {"status": "queued"})
    await store.create("x.py")
    assert _val("vishap_jobs_created_total", {"status": "queued"}) == before + 1


@pytest.mark.asyncio
async def test_jobs_completed_counter_increments():
    store = InMemoryJobStore()
    job = await store.create("x.py")
    before = _val("vishap_jobs_completed_total", {"status": "done"})
    await store.update(job.job_id, status=JobStatus.DONE)
    assert _val("vishap_jobs_completed_total", {"status": "done"}) == before + 1


@pytest.mark.asyncio
async def test_jobs_failed_counter_increments():
    store = InMemoryJobStore()
    job = await store.create("x.py")
    before = _val("vishap_jobs_completed_total", {"status": "failed"})
    await store.update(job.job_id, status=JobStatus.FAILED)
    assert _val("vishap_jobs_completed_total", {"status": "failed"}) == before + 1


@pytest.mark.asyncio
async def test_job_duration_histogram_observed():
    store = InMemoryJobStore()
    job = await store.create("x.py")
    t0 = datetime.now(UTC)
    await store.update(job.job_id, status=JobStatus.RUNNING, started_at=t0)
    before = _val("vishap_job_duration_seconds_count", {})
    await store.update(job.job_id, status=JobStatus.DONE, finished_at=t0 + timedelta(seconds=2))
    assert _val("vishap_job_duration_seconds_count", {}) == before + 1


# --- http counters ---

def test_http_requests_counter_increments(client):
    labels = {"method": "GET", "endpoint": "/", "status": "200"}
    before = _val("vishap_http_requests_total", labels)
    client.get("/")
    assert _val("vishap_http_requests_total", labels) == before + 1


def test_http_requests_by_status(client):
    client.get("/")
    client.get("/definitely-not-a-real-endpoint")
    assert _val("vishap_http_requests_total", {"method": "GET", "endpoint": "/", "status": "200"}) >= 1
    assert _val(
        "vishap_http_requests_total",
        {"method": "GET", "endpoint": "/definitely-not-a-real-endpoint", "status": "404"},
    ) >= 1


# --- format / robustness ---

def test_metrics_prometheus_format(client):
    body = client.get("/metrics").text
    assert "# HELP" in body
    assert "# TYPE" in body


def test_metrics_include_all_registered(client):
    body = client.get("/metrics").text
    for name in ("vishap_jobs_created_total", "vishap_jobs_completed_total",
                 "vishap_job_duration_seconds", "vishap_http_requests_total"):
        assert name in body


def test_metrics_survive_multiple_requests(client):
    labels = {"method": "GET", "endpoint": "/", "status": "200"}
    client.get("/")
    before = _val("vishap_http_requests_total", labels)
    client.get("/metrics")
    client.get("/metrics")
    assert _val("vishap_http_requests_total", labels) == before  # not reset by scrape


def test_metrics_no_exception_on_empty():
    out = metrics.get_metrics_output()
    assert isinstance(out, str)
    assert "vishap_jobs_created_total" in out
