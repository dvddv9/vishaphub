# -*- coding: utf-8 -*-
"""Regression tests: update_job must convert ISO-string started_at/finished_at
to datetime (v6.0.3-shim-fix).

main.py passes started_at/finished_at as datetime.now(UTC).isoformat() (str).
The shim must convert them so Job stays strictly typed (datetime | None),
and get_job() must not raise AttributeError on .isoformat().
"""
from datetime import datetime, UTC

from src.api.jobs import create_job, get_job, update_job, get_store
from src.api.job_store import Job

import asyncio


def _store_get(job_id: str):
    """The store is async since v6.3; this module exercises the sync facade."""
    return asyncio.run(get_store().get(job_id))


def test_update_job_converts_started_at_from_iso_string():
    jid = create_job("test.py")
    ok = update_job(jid, status="running", started_at=datetime.now(UTC).isoformat())
    assert ok is True
    d = get_job(jid)
    assert isinstance(d["started_at"], str)  # legacy: ISO string, no crash
    job = _store_get(jid)
    assert isinstance(job, Job)
    assert isinstance(job.started_at, datetime)  # strictly typed


def test_update_job_converts_finished_at_from_iso_string():
    jid = create_job("test.py")
    ok = update_job(jid, status="done", finished_at=datetime.now(UTC).isoformat())
    assert ok is True
    d = get_job(jid)
    assert isinstance(d["finished_at"], str)
    job = _store_get(jid)
    assert isinstance(job.finished_at, datetime)


def test_update_job_accepts_datetime_natively():
    jid = create_job("test.py")
    ts = datetime.now(UTC)
    ok = update_job(jid, started_at=ts)
    assert ok is True
    job = _store_get(jid)
    assert job.started_at == ts


def test_get_job_returns_iso_after_real_update():
    jid = create_job("test.py")
    update_job(jid, status="running", started_at=datetime.now(UTC).isoformat())
    update_job(jid, status="done", finished_at=datetime.now(UTC).isoformat())
    d = get_job(jid)  # must NOT raise AttributeError
    assert isinstance(d["started_at"], str)
    assert isinstance(d["finished_at"], str)
    assert d["status"] == "done"
