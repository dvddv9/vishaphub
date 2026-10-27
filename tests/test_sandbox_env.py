# -*- coding: utf-8 -*-
"""The test/fixer sandbox must not hand the server's secrets to LLM-written code."""
import os

from src.pipeline import sandbox

SECRETS = {
    "CUSTOM_LLM_KEY": "sk-test-secret",
    "CONVEYOR_API_KEY": "conveyor-secret",
    "DATABASE_URL": "postgresql://user:pw@host/db",
    "CLERK_SECRET_KEY": "clerk-secret",
    "FERNET_KEY": "fernet-secret",
    "GITHUB_WEBHOOK_SECRET": "webhook-secret",
}


def _with_secrets(monkeypatch):
    for name, value in SECRETS.items():
        monkeypatch.setenv(name, value)


def test_child_env_has_no_secrets(monkeypatch):
    _with_secrets(monkeypatch)
    env = sandbox._sandbox_env("/tmp/x")
    for name in SECRETS:
        assert name not in env
    assert all(value not in SECRETS.values() for value in env.values())


def test_child_env_keeps_what_python_needs_and_marks_the_sandbox(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    env = sandbox._sandbox_env("/tmp/x")
    assert env["PATH"] == "/usr/bin"
    assert env["VISHAP_SANDBOX"] == "1"
    assert env["TMPDIR"] == "/tmp/x"


def test_only_allowlisted_server_variables_pass(monkeypatch):
    monkeypatch.setenv("SOME_RANDOM_VARIABLE", "value")
    env = sandbox._sandbox_env("/tmp/x")
    assert "SOME_RANDOM_VARIABLE" not in env


def test_generated_test_cannot_read_server_secrets(monkeypatch):
    _with_secrets(monkeypatch)
    code = (
        "import os\n\n"
        "def test_env():\n"
        "    for name in %r:\n"
        "        assert name not in os.environ, name\n" % sorted(SECRETS)
    )
    result = sandbox.run_pytest_in_sandbox(code, timeout=60)
    assert result["ok"], result
