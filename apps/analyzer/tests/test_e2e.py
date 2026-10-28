# -*- coding: utf-8 -*-
"""
End-to-end tests — real LLM via FastAPI.

Requires FastAPI running on http://localhost:5001.

Run:
    python run_tests.py --all

These tests are SLOW (~90 sec) and use real LLM credits.
They are skipped by default (marker: e2e).
"""
import time
import uuid

import pytest
import requests


API_URL = "http://localhost:5001"
TIMEOUT = 300

# v6.1-e2e-fix: X-API-Key for /analyze (required since v5.10.5)
import os
API_KEY = os.environ.get("CONVEYOR_API_KEY", "test-key-12345")
HEADERS = {"X-API-Key": API_KEY}

def _unique_material(prefix: str = "e2e") -> str:
    return f"def {prefix}_{uuid.uuid4().hex[:8]}(): pass"


E2E_FILENAME = "e2e_a.py"


def _api_available() -> bool:
    try:
        r = requests.get(f"{API_URL}/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _api_available(),
    reason="FastAPI not running on localhost:5001",
)


# === Test 1: health ===

def test_e2e_health():
    r = requests.get(f"{API_URL}/health", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"
    assert "timestamp" in data


# === Test 2: full pipeline ===

def test_e2e_full_pipeline():
    material = _unique_material("full")
    payload = {"material": material, "filename": E2E_FILENAME, "verbose": False}

    t0 = time.time()
    r = requests.post(f"{API_URL}/analyze", json=payload, headers=HEADERS, timeout=TIMEOUT)
    elapsed = time.time() - t0

    assert r.status_code == 200, f"API error: {r.text[:500]}"
    data = r.json()

    # session_id
    assert "session_id" in data
    assert data["session_id"].startswith("sess-")

    # level
    assert data.get("level") in ("D0", "D1", "D2", "D3", "D4")

    # markdown — обязательные блоки
    md = data.get("final_markdown", "")
    assert "[CONCLUSION]" in md
    assert "[AUDIT_TRAIL]" in md
    assert "[COMPLETENESS]" in md

    # cost
    assert data.get("cost_usd", 0) > 0, "cost_usd должен быть > 0"
    assert data.get("tokens_in", 0) > 0
    assert data.get("tokens_out", 0) > 0

    # не кэш (первый раз)
    assert data.get("cached") is False

    # время
    assert elapsed < TIMEOUT, f"Pipeline слишком долго: {elapsed:.1f} сек"


# === Test 3: idempotency (cached) ===

def test_e2e_idempotency_cache_hit():
    material = _unique_material("idem")
    payload = {"material": material, "filename": E2E_FILENAME, "verbose": False}

    # Первый запрос (может быть из предыдущего теста, но не зависим)
    r1 = requests.post(f"{API_URL}/analyze", json=payload, headers=HEADERS, timeout=TIMEOUT)
    assert r1.status_code == 200
    data1 = r1.json()
    session1 = data1["session_id"]

    # Второй запрос — должен вернуть кэш
    t0 = time.time()
    r2 = requests.post(f"{API_URL}/analyze", json=payload, headers=HEADERS, timeout=TIMEOUT)
    elapsed2 = time.time() - t0
    assert r2.status_code == 200
    data2 = r2.json()

    # Кэш
    assert data2.get("cached") is True, "Второй запрос должен быть cached"

    # Тот же session_id
    assert data2["session_id"] == session1, "session_id должен совпадать"

    # Мгновенно (< 5 сек, не 90)
    assert elapsed2 < 5, f"Кэш должен быть мгновенным, но занял {elapsed2:.1f} сек"

    # Тот же markdown
    assert data2.get("final_markdown") == data1.get("final_markdown")
