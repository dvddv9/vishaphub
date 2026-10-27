# -*- coding: utf-8 -*-
"""Markdown report download tests (v6.5) — filesystem only, no Postgres."""
import shutil
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api import reports
from src.config import CONVEYOR_API_KEY as _KEY

_AUTH = {"X-API-Key": _KEY} if _KEY else {}

JOB_ID = "job-abc123def456"


@pytest.fixture
def reports_root(monkeypatch):
    """Point the reports directory at a scratch folder inside data/ (gitignored)."""
    root = Path("data") / f"reports_test_{uuid.uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(reports, "reports_dir", lambda: root)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _job(markdown: str | None = None) -> dict:
    result = {"session_id": "sess-1"}
    if markdown is not None:
        result["final_markdown"] = markdown
    return {"job_id": JOB_ID, "status": "done", "filename": "a.py", "result": result}


def test_download_report(reports_root):
    """The .md file exists: served straight from disk."""
    from src.main import app

    content = "# Report\n\nfinal markdown\n"
    (reports_root / f"{JOB_ID}.md").write_bytes(content.encode("utf-8"))

    with patch("src.main.get_job_async", AsyncMock(return_value=_job())):
        response = TestClient(app).get(f"/report/{JOB_ID}/download", headers=_AUTH)

    assert response.status_code == 200
    assert response.text == content
    assert response.headers["content-type"].startswith("text/markdown")
    assert JOB_ID in response.headers["content-disposition"]


def test_download_report_falls_back_to_job_result(reports_root):
    """No file on disk (worker wrote it elsewhere): serve from the job result."""
    from src.main import app

    content = "# Report\n\nfrom the job result\n"

    with patch("src.main.get_job_async", AsyncMock(return_value=_job(content))):
        response = TestClient(app).get(f"/report/{JOB_ID}/download", headers=_AUTH)

    assert response.status_code == 200
    assert response.text == content
    assert response.headers["content-type"].startswith("text/markdown")
    # The missing file is repaired for the next request.
    assert (reports_root / f"{JOB_ID}.md").read_bytes() == content.encode("utf-8")


def test_download_report_not_found(reports_root):
    """Neither a file nor a Markdown result: genuinely 404."""
    from src.main import app

    with patch("src.main.get_job_async", AsyncMock(return_value=_job())):
        response = TestClient(app).get(f"/report/{JOB_ID}/download", headers=_AUTH)

    assert response.status_code == 404
    assert response.json()["detail"] == "report not found"


def test_download_report_unknown_job(reports_root):
    from src.main import app

    with patch("src.main.get_job_async", AsyncMock(return_value=None)):
        response = TestClient(app).get(f"/report/{JOB_ID}/download", headers=_AUTH)

    assert response.status_code == 404
    assert response.json()["detail"] == "job not found"
