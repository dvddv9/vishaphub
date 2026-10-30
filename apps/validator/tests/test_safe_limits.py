"""What the code under test may see, take, and reach.

Three guards live in `safe.py` and each of them can disappear silently in a refactor:
the clean environment, the resource caps, and the network prefix. These tests name them,
so removing one turns a test red instead of turning the validator into a host for
somebody else's code.
"""
import os

import pytest

from validator import safe


def test_the_host_environment_is_not_handed_to_the_code(monkeypatch):
    """A test that prints os.environ must not print the host's keys."""
    monkeypatch.setenv("VISHAP_HUB_LLM_KEY", "sk-ant-not-a-real-key")
    monkeypatch.setenv("VISHAP_VALIDATOR_TOKEN", "x" * 32)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/db")

    env = safe.clean_env()

    assert "VISHAP_HUB_LLM_KEY" not in env
    assert "VISHAP_VALIDATOR_TOKEN" not in env
    assert "DATABASE_URL" not in env
    assert "PATH" in env


def test_network_prefix_is_a_list_and_cached():
    """`[]` means this platform cannot isolate; a list means it can. Both are answers."""
    first = safe.network_off()
    assert isinstance(first, list)
    assert safe.network_off() == first          # probed once, not per run


@pytest.mark.skipif(os.name != "posix", reason="rlimits are POSIX only")
def test_rlimits_returns_a_hook_on_posix():
    assert callable(safe.rlimits())


def test_rlimits_are_absent_where_the_platform_has_none():
    if os.name == "posix":
        pytest.skip("POSIX has rlimits")
    assert safe.rlimits() is None
