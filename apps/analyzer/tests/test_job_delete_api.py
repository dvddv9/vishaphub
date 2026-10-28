# -*- coding: utf-8 -*-
"""`DELETE /status/{job_id}` вЂ” the endpoint behind the UI's delete buttons.

The dashboard and the report page both call it, so it must be boring: 200 when
the job existed, 404 when it did not, and never a 500 for a missing job.
"""
import pytest
from fastapi.testclient import TestClient

import src.main as main
from src.config import CONVEYOR_API_KEY

# The API key is enforced whenever `.env` sets one (it does in this project), so
# every request carries it вЂ” same pattern as tests/test_async_api.py.
HEADERS = {"X-API-Key": CONVEYOR_API_KEY} if CONVEYOR_API_KEY else {}


@pytest.fixture()
def client():
    return TestClient(main.app)


def test_delete_removes_an_existing_job(client, monkeypatch):
    seen = {}

    async def fake_delete(job_id: str) -> bool:
        seen["job_id"] = job_id
        return True

    monkeypatch.setattr(main, "delete_job_async", fake_delete)

    response = client.delete("/status/job-123", headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {"deleted": True, "job_id": "job-123"}
    assert seen == {"job_id": "job-123"}


def test_delete_answers_404_for_an_unknown_job(client, monkeypatch):
    async def fake_delete(job_id: str) -> bool:
        return False

    monkeypatch.setattr(main, "delete_job_async", fake_delete)

    response = client.delete("/status/nope", headers=HEADERS)
    assert response.status_code == 404
    assert response.json()["detail"] == "job not found"


def test_delete_requires_the_api_key(client, monkeypatch):
    """Without the header the endpoint must be rejected before the store is hit."""
    import src.api.auth as auth_mod
    monkeypatch.setattr(auth_mod, "API_KEY", "test-key-123")
    response = client.delete("/status/job-1")
    assert response.status_code == 401

def test_delete_is_scoped_to_the_tenant(client, monkeypatch):
    """The handler must run inside the current tenant scope, or Postgres RLS
    would make the delete invisible."""
    used = {}

    async def fake_delete(job_id: str) -> bool:
        from src.api.jobs import get_current_tenant

        used["tenant"] = get_current_tenant()
        return True

    monkeypatch.setattr(main, "delete_job_async", fake_delete)
    assert client.delete("/status/job-1", headers=HEADERS).status_code == 200
    assert "tenant" in used

