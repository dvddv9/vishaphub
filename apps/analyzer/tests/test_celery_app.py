# -*- coding: utf-8 -*-
"""Tests for the Celery app configuration (v6.1)."""
from celery import Celery

from src.api.celery_app import celery_app, _get_celery_app


def test_celery_app_exists():
    assert isinstance(celery_app, Celery)


def test_broker_url_from_env(monkeypatch):
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://test:6379/5")
    app = _get_celery_app()
    assert app.conf.broker_url == "redis://test:6379/5"


def test_result_backend_from_env(monkeypatch):
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://test:6379/6")
    app = _get_celery_app()
    assert app.conf.result_backend == "redis://test:6379/6"


def test_task_registered():
    from src.api import tasks  # registers the task on import
    assert "src.api.tasks.run_analysis_task" in tasks.celery_app.tasks
