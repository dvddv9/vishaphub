# -*- coding: utf-8 -*-
"""Tenant key generation tests (v6.5) — the store is mocked, no Postgres.

``scripts/generate_key.py`` is a CLI: it parses ``sys.argv`` and returns an exit
code, so the tests drive it through ``monkeypatch.setattr(sys, "argv", ...)``.
"""
import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.api import tenants

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "generate_key.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("generate_key_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generate_api_key_format():
    key = tenants.generate_api_key()

    assert key.startswith(tenants.API_KEY_PREFIX)
    assert len(key) > len(tenants.API_KEY_PREFIX) + 32
    assert tenants.generate_api_key() != key  # no accidental constant


def test_main_creates_tenant(monkeypatch, capsys):
    script = _load_script()
    created: dict = {}

    async def fake_create(**kwargs):
        created.update(kwargs)
        return {"tenant_id": kwargs["tenant_id"], "email": kwargs["email"]}

    monkeypatch.setattr(sys, "argv", ["generate_key.py", "client@example.com"])

    before = datetime.now(UTC)
    with patch.object(script, "create_tenant", AsyncMock(side_effect=fake_create)):
        exit_code = script.main()

    assert exit_code == 0
    assert created["email"] == "client@example.com"
    assert created["plan"] == "pro"
    assert created["api_key"].startswith(tenants.API_KEY_PREFIX)
    assert created["tenant_id"].startswith("tenant_")

    expected = before + timedelta(days=365)
    assert abs((created["expires_at"] - expected).total_seconds()) < 120

    # The key is shown exactly once — it must reach stdout.
    assert created["api_key"] in capsys.readouterr().out


def test_main_rejects_unknown_plan(monkeypatch):
    script = _load_script()
    monkeypatch.setattr(
        sys, "argv", ["generate_key.py", "client@example.com", "--plan", "gold"]
    )

    # argparse rejects the value via `choices` and exits with status 2.
    with pytest.raises(SystemExit) as excinfo:
        script.main()

    assert excinfo.value.code == 2
