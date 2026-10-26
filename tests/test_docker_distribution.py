# -*- coding: utf-8 -*-
"""The Docker distribution must stay consistent with the app.

Docker support was removed in v7 and then restored by request, so these tests
pin the parts that silently rot: the image must run the API (not the removed
container, and CI must build without publishing.
"""
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCKERFILE = ROOT / "Dockerfile"
COMPOSE = ROOT / "docker-compose.yml"
WORKFLOW = ROOT / ".github" / "workflows" / "docker-build.yml"


def test_image_runs_the_api_only():
    text = DOCKERFILE.read_text(encoding="utf-8")
    # The CMD runs migrations first, then the API; pin the API part, not the
    # exact CMD spelling (which changed when alembic was added).
    assert "uvicorn src.main:app" in text
    assert "EXPOSE 5001" in text
    assert "8501" not in text, "the Streamlit UI was removed in v7"
    assert "streamlit" not in text.lower()
    assert "HEALTHCHECK" in text and "/health" in text
    assert "USER vishap" in text, "the container must not run as root"



def test_compose_has_no_removed_services():
    text = COMPOSE.read_text(encoding="utf-8").lower()
    for removed in ("ollama", "streamlit", "grafana", "tempo"):
        assert removed not in text, f"{removed} was removed in v7"


def test_ci_builds_without_publishing():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    step = workflow["jobs"]["build"]["steps"][1]
    assert step["with"]["push"] is False, (
        "publishing needs a deliberate decision (and Docker Hub secrets)"
    )
    assert step["with"]["file"] == "./Dockerfile"
