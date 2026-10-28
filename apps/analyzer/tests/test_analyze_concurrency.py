# -*- coding: utf-8 -*-
"""Tests for analyze.py --mode concurrency (v6.1)."""
from src.tools.analyze import analyze_concurrency


def test_detects_asyncio_lock():
    code = "import asyncio\nlock = asyncio.Lock()\n"
    result = analyze_concurrency(code)
    assert result["locks"] == ["asyncio.Lock"]


def test_detects_threading_lock():
    code = "import threading\nlock = threading.Lock()\n"
    result = analyze_concurrency(code)
    assert result["locks"] == ["threading.Lock"]


def test_detects_shared_global():
    code = "counter = 0\n\ndef inc():\n    global counter\n    counter += 1\n"
    result = analyze_concurrency(code)
    assert "counter" in result["shared_state"]


def test_detects_await():
    code = "async def f():\n    await foo()\n"
    result = analyze_concurrency(code)
    assert "await" in result["async_constructs"]


def test_clean_no_concurrency():
    code = "def add(a, b):\n    return a + b\n"
    result = analyze_concurrency(code)
    assert result["locks"] == []
    assert result["shared_state"] == []
    assert result["async_constructs"] == []
