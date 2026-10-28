# -*- coding: utf-8 -*-
"""'Analysis without LLM': X-LLM-Provider: rules runs the built-in rule engine only."""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src import main
from src.config import CONVEYOR_API_KEY as _KEY

_AUTH = {"X-API-Key": _KEY} if _KEY else {}


@pytest.fixture
def server_key_only(monkeypatch):
    monkeypatch.setenv("VISHAP_SERVER_KEY_ONLY", "1")
    monkeypatch.setenv("CUSTOM_LLM_KEY", "sk-server-key")


def test_rules_is_static_even_when_the_server_has_its_own_key(server_key_only):
    assert main._is_static_only(None) is False
    assert main._is_static_only(None, "rules") is True
    assert main._is_static_only(None, " RULES ") is True
    assert main._is_static_only(None, "anthropic") is False


def test_rules_binds_no_key_and_no_target(server_key_only):
    assert main._apply_llm_request(None, "rules", None) == (None, None)


def test_batch_refuses_rules_mode(server_key_only):
    with pytest.raises(HTTPException) as err:
        main._apply_llm_request(None, "rules", None, allow_static=False)
    assert err.value.status_code == 400


def test_analyze_with_rules_never_calls_the_llm(server_key_only, monkeypatch):
    from src.llm import client

    def boom(*a, **k):
        raise AssertionError("LLM was called in rules-only mode")

    monkeypatch.setattr(client, "_chat_custom", boom)
    body = {"material": "import os\nos.system(user_input)\npassword = 'hunter2hunter2'\n", "filename": "x.py"}
    r = TestClient(main.app).post("/analyze", json=body, headers={**_AUTH, "X-LLM-Provider": "rules"})
    assert r.status_code == 200, r.text
    assert r.json()["level"] == "STATIC"
