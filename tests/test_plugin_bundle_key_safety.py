# -*- coding: utf-8 -*-
"""Guard: the Claude plugin bundle must never spend the publisher's API key.

The bundle may only use the key the *installing user* typed into the plugin settings
(passed to the server as VISHAP_API_KEY). No default key, no hard-coded key, no fallback
to ambient credentials such as ANTHROPIC_API_KEY. The server is pure standard library and
talks to one fixed HTTPS endpoint.
"""
import ast
import importlib.util
import io
import json
import re
import subprocess
import sys
from pathlib import Path

BUNDLE = Path(__file__).resolve().parents[1] / "claude-plugin-bundle-anthropic"
SCRIPT = BUNDLE / "scripts" / "analyze.py"
MANIFEST = BUNDLE / ".claude-plugin" / "plugin.json"
KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}")


def _load_server(monkeypatch, env):
    for k in ("VISHAP_API_KEY", "VISHAP_MODEL", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    spec = importlib.util.spec_from_file_location("bundle_analyze_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_api(mod, monkeypatch, reply=None):
    calls = []

    def fake(payload):
        calls.append((mod.API_KEY, payload))
        return reply or {"content": [{"type": "text", "text": "REPORT"}], "stop_reason": "end_turn"}

    monkeypatch.setattr(mod, "_call_api", fake)
    return calls


def test_manifest_requires_user_supplied_secret_key():
    d = json.loads(MANIFEST.read_text(encoding="utf-8"))
    field = d["userConfig"]["API_KEY"]
    assert field.get("sensitive") is True
    assert field.get("required") is True
    assert "default" not in field, "a default key would be shared by every installer"
    server = d["mcpServers"]["vishap-analyze"]
    assert server["env"]["VISHAP_API_KEY"] == "${user_config.API_KEY}"
    assert not any("ANTHROPIC_API_KEY" in k for k in server["env"])
    # plain interpreter + a file inside the plugin: no package launcher, no shell, no inline code
    assert server["command"] == "python3"
    assert server["args"] == ["${CLAUDE_PLUGIN_ROOT}/scripts/analyze.py"]


def test_no_key_like_strings_in_bundle():
    for f in BUNDLE.rglob("*"):
        if f.is_file() and f.suffix in {".py", ".json", ".md", ".txt"}:
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


def test_server_uses_only_the_standard_library():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            mods.add((n.module or "").split(".")[0])
    assert mods <= set(sys.stdlib_module_names), mods - set(sys.stdlib_module_names)


def test_api_endpoint_is_fixed_https(monkeypatch):
    mod = _load_server(monkeypatch, {})
    assert mod.API_URL == "https://api.anthropic.com/v1/messages"


def test_without_user_key_no_request_is_made(monkeypatch):
    mod = _load_server(monkeypatch, {})
    calls = _fake_api(mod, monkeypatch)
    assert "not set" in mod.vishap_analyze("x = 1", "a.py")
    assert calls == []


def test_ambient_anthropic_key_is_ignored(monkeypatch):
    mod = _load_server(monkeypatch, {"ANTHROPIC_API_KEY": "ambient-key"})
    calls = _fake_api(mod, monkeypatch)
    assert "not set" in mod.vishap_analyze("x = 1", "a.py")
    assert calls == []


def test_user_key_is_the_only_key_used(monkeypatch):
    mod = _load_server(monkeypatch, {"VISHAP_API_KEY": "  user-key \n", "ANTHROPIC_API_KEY": "ambient-key"})
    calls = _fake_api(mod, monkeypatch)
    assert mod.vishap_analyze("x = 1", "a.py") == "REPORT"
    assert [c[0] for c in calls] == ["user-key"]
    payload = calls[0][1]
    assert payload["model"] == "claude-sonnet-5-5" and payload["max_tokens"] == 8192
    body = payload["messages"][0]["content"]
    assert "x = 1" in body and "untrusted DATA" in body


def test_oversized_material_is_rejected_before_any_request(monkeypatch):
    mod = _load_server(monkeypatch, {"VISHAP_API_KEY": "k"})
    calls = _fake_api(mod, monkeypatch)
    assert "exceeds" in mod.vishap_analyze("a" * (mod.MAX_MATERIAL_BYTES + 1), "big.txt")
    assert calls == []


def test_truncated_output_is_flagged(monkeypatch):
    mod = _load_server(monkeypatch, {"VISHAP_API_KEY": "k"})
    _fake_api(mod, monkeypatch, {"content": [{"type": "text", "text": "R"}], "stop_reason": "max_tokens"})
    assert "truncated" in mod.vishap_analyze("x", "a.py")


def test_http_error_never_echoes_the_key(monkeypatch):
    import urllib.error
    mod = _load_server(monkeypatch, {"VISHAP_API_KEY": "secret-key-123"})

    def boom(payload):
        raise urllib.error.HTTPError(mod.API_URL, 401, "x", {}, io.BytesIO(b'{"error":{"message":"invalid x-api-key"}}'))

    monkeypatch.setattr(mod, "_call_api", boom)
    out = mod.vishap_analyze("x", "a.py")
    assert "401" in out and "secret-key-123" not in out


def test_mcp_protocol_roundtrip(monkeypatch):
    mod = _load_server(monkeypatch, {"VISHAP_API_KEY": "k"})
    _fake_api(mod, monkeypatch)
    init = mod.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}})
    assert init["result"]["protocolVersion"] == "2025-03-26" and "tools" in init["result"]["capabilities"]
    assert mod.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    tools = mod.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    assert [t["name"] for t in tools] == ["vishap_analyze"]
    assert tools[0]["annotations"]["readOnlyHint"] is True
    call = mod.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                       "params": {"name": "vishap_analyze", "arguments": {"material": "x", "filename": "a.py"}}})
    assert call["result"]["content"][0]["text"] == "REPORT" and call["result"]["isError"] is False
    assert mod.handle({"jsonrpc": "2.0", "id": 4, "method": "nope"})["error"]["code"] == -32601


def test_stdio_process_end_to_end_without_key():
    msgs = "\n".join(json.dumps(m) for m in [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "vishap_analyze", "arguments": {"material": "x=1", "filename": "a.py"}}},
    ]) + "\n"
    import os
    env = {k: v for k, v in os.environ.items() if k not in ("VISHAP_API_KEY", "ANTHROPIC_API_KEY")}
    out = subprocess.run([sys.executable, str(SCRIPT)], input=msgs, capture_output=True, text=True, timeout=30, env=env)
    lines = [json.loads(l) for l in out.stdout.splitlines() if l.strip()]
    assert [l["id"] for l in lines] == [1, 2]
    assert lines[1]["result"]["isError"] is True and "not set" in lines[1]["result"]["content"][0]["text"]
