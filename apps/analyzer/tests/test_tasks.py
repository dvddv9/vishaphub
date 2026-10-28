# -*- coding: utf-8 -*-
"""Tests for the Celery analysis task (v6.1)."""
from unittest.mock import MagicMock, patch

import pytest

from src.api import tasks


def test_task_updates_job_status():
    store = MagicMock()
    with patch("src.api.tasks.get_store", return_value=store), \
         patch("src.api.tasks.run_pipeline", return_value={"session_id": "sess-1"}):
        tasks.run_analysis_task("job-1", "code", "x.py")
    statuses = [c.kwargs.get("status") for c in store.update.call_args_list]
    assert "running" in statuses
    assert "done" in statuses


def test_task_handles_exception():
    store = MagicMock()
    with patch("src.api.tasks.get_store", return_value=store), \
         patch("src.api.tasks.run_pipeline", side_effect=RuntimeError("boom")):
        with pytest.raises(Exception):
            tasks.run_analysis_task("job-1", "code", "x.py")
    failed = [c for c in store.update.call_args_list if c.kwargs.get("status") == "failed"]
    assert len(failed) == 1


def test_task_retry_on_failure():
    assert tasks.run_analysis_task.max_retries == 3
