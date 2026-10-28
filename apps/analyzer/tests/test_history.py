# -*- coding: utf-8 -*-
"""Tenant isolation for the analysis history (v6.3, Block 16.1).

The history is stored in a JSON file, so PostgreSQL RLS does not protect it.
These tests pin the application-level filter instead.
"""
import pytest
from fastapi.testclient import TestClient

from src.api.job_store import tenant_scope
from src.storage import history as history_mod


@pytest.fixture
def history_file(monkeypatch):
    """Point the history module at a scratch file inside data/ (gitignored)."""
    path = history_mod.DATA_DIR / "history_tenant_test.json"
    if path.exists():
        path.unlink()
    monkeypatch.setattr(history_mod, "HISTORY_FILE", path)
    try:
        yield path
    finally:
        if path.exists():
            path.unlink()


def _client_for(tenant_id: str) -> TestClient:
    from src.auth.middleware import current_tenant
    from src.main import app

    app.dependency_overrides[current_tenant] = lambda: tenant_id
    return TestClient(app)


def _release() -> None:
    from src.auth.middleware import current_tenant
    from src.main import app

    app.dependency_overrides.pop(current_tenant, None)


def _api_headers() -> dict:
    """`/history/clear` also requires the API key when CONVEYOR_API_KEY is set."""
    from src.api import auth as auth_mod

    return {"X-API-Key": auth_mod.API_KEY} if auth_mod.API_KEY else {}


# ---------------------------------------------------------------- storage layer

def test_add_entry_tags_entry_with_bound_tenant(history_file):
    with tenant_scope("t9"):
        entry = history_mod.add_entry({"filename": "ctx.py", "verdict": "SAFE"})

    assert entry["tenant_id"] == "t9"
    assert [e["filename"] for e in history_mod.load_history("t9")] == ["ctx.py"]


def test_load_history_filters_by_tenant(history_file):
    history_mod.add_entry({"filename": "a.py"}, tenant_id="t1")
    history_mod.add_entry({"filename": "b.py"}, tenant_id="t2")

    assert [e["filename"] for e in history_mod.load_history("t1")] == ["a.py"]
    assert [e["filename"] for e in history_mod.load_history("t2")] == ["b.py"]
    assert len(history_mod.load_history()) == 2  # unscoped: everything


def test_legacy_entries_are_visible_only_as_public(history_file):
    # Pre-v6.3 rows have no tenant_id at all.
    history_mod.save_history([{"filename": "old.py", "verdict": "SAFE"}])

    assert [e["filename"] for e in history_mod.load_history("public")] == ["old.py"]
    assert history_mod.load_history("t1") == []


def test_clear_history_removes_only_one_tenant(history_file):
    history_mod.add_entry({"filename": "a.py"}, tenant_id="t1")
    history_mod.add_entry({"filename": "b.py"}, tenant_id="t2")

    assert history_mod.clear_history("t1") == 1
    assert [e["filename"] for e in history_mod.load_history()] == ["b.py"]


# --------------------------------------------------------------- HTTP endpoints

def test_history_endpoint_is_isolated(history_file):
    history_mod.add_entry({"filename": "a.py"}, tenant_id="tenant-a")
    history_mod.add_entry({"filename": "b.py"}, tenant_id="tenant-b")

    client = _client_for("tenant-a")
    try:
        payload = client.get("/history")
    finally:
        _release()

    assert payload.status_code == 200
    assert [item["filename"] for item in payload.json()] == ["a.py"]


def test_history_clear_endpoint_is_isolated(history_file):
    history_mod.add_entry({"filename": "a.py"}, tenant_id="tenant-a")
    history_mod.add_entry({"filename": "b.py"}, tenant_id="tenant-b")

    client = _client_for("tenant-a")
    try:
        response = client.post("/history/clear", headers=_api_headers())
    finally:
        _release()

    assert response.status_code == 200
    assert response.json()["removed"] == 1
    assert [e["filename"] for e in history_mod.load_history()] == ["b.py"]
