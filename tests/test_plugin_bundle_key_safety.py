# -*- coding: utf-8 -*-
"""Guard: the Claude plugin bundle must never spend the publisher's API key.

The bundle may only use the key the *installing user* typed into the plugin settings
(passed to the server as VISHAP_API_KEY). No default key, no hard-coded key, no
fallback to ambient credentials such as ANTHROPIC_API_KEY.
"""
import ast
import importlib.util
import json
import re
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "analyze.py"
MANIFEST = ROOT / ".claude-plugin" / "plugin.json"
PLUGIN_FILES = [SCRIPT, MANIFEST, ROOT / ".claude-plugin" / "marketplace.json", ROOT / "requirements-plugin.txt"]
KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}")


def _load_server(monkeypatch, env):
    """Import analyze.py with stubbed fastmcp/anthropic; return (module, recorded_clients)."""
    clients = []

    class _FastMCP:
        def __init__(self, *a, **k):
            pass

        def tool(self, **kw):
            return lambda fn: fn

        def run(self):
            pass

    class _Block:
        type = "text"
        text = "REPORT"

    class _Resp:
        content = [_Block()]
        stop_reason = "end_turn"

    class _Anthropic:
        def __init__(self, api_key=None):
            clients.append(api_key)
            self.messages = types.SimpleNamespace(create=lambda **kw: _Resp())

    fm = types.ModuleType("fastmcp")
    fm.FastMCP = _FastMCP
    an = types.ModuleType("anthropic")
    an.Anthropic = _Anthropic
    monkeypatch.setitem(sys.modules, "fastmcp", fm)
    monkeypatch.setitem(sys.modules, "anthropic", an)
    for k in ("VISHAP_API_KEY", "VISHAP_MODEL", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    spec = importlib.util.spec_from_file_location("bundle_analyze_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, clients


def test_manifest_requires_user_supplied_secret_key():
    d = json.loads(MANIFEST.read_text(encoding="utf-8"))
    field = d["userConfig"]["API_KEY"]
    assert field.get("sensitive") is True
    assert field.get("required") is True
    assert "default" not in field, "a default key would be shared by every installer"
    env = d["mcpServers"]["vishap-analyze"]["env"]
    assert env["VISHAP_API_KEY"] == "${user_config.API_KEY}"
    assert not any("ANTHROPIC_API_KEY" in k for k in env)


def test_no_key_like_strings_in_plugin_files():
    for f in PLUGIN_FILES:
        assert not KEY_RE.search(f.read_text(encoding="utf-8", errors="replace")), f"key-like string in {f}"


def test_server_reads_only_plugin_scoped_env():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") in {"getenv", "get"}:
            if n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                if n.args[0].value.isupper():
                    names.add(n.args[0].value)
    assert names <= {"VISHAP_API_KEY", "VISHAP_MODEL"}, names


def test_without_user_key_no_client_is_created(monkeypatch):
    mod, clients = _load_server(monkeypatch, {})
    assert "not set" in mod.vishap_analyze("x = 1", "a.py")
    assert clients == []


def test_ambient_anthropic_key_is_ignored(monkeypatch):
    mod, clients = _load_server(monkeypatch, {"ANTHROPIC_API_KEY": "ambient-key"})
    assert "not set" in mod.vishap_analyze("x = 1", "a.py")
    assert clients == []


def test_user_key_is_the_only_key_used(monkeypatch):
    mod, clients = _load_server(monkeypatch, {"VISHAP_API_KEY": "user-key", "ANTHROPIC_API_KEY": "ambient-key"})
    mod.vishap_analyze("x = 1", "a.py")
    assert clients == ["user-key"]
