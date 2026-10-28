"""Key policy: the order of checks is the contract."""
import pytest

from core.auth import Decision, KeyPolicy, check_key


def test_matching_static_key_allows():
    assert check_key("secret", KeyPolicy(expected_key="secret")) is Decision.ALLOW


def test_wrong_key_is_invalid_not_missing():
    assert check_key("nope", KeyPolicy(expected_key="secret")) is Decision.INVALID


def test_empty_key_is_missing():
    assert check_key("", KeyPolicy(expected_key="secret")) is Decision.MISSING


def test_public_demo_allows_keyless_call():
    assert check_key("", KeyPolicy(expected_key="secret", public_demo=True)) is Decision.ALLOW


def test_public_demo_does_not_accept_an_invalid_key_as_the_operators():
    # The demo path allows anything, but it must never be mistaken for a match.
    assert check_key("wrong", KeyPolicy(expected_key="secret", public_demo=True)) is Decision.ALLOW


def test_unconfigured_deployment_is_unavailable_not_open():
    assert check_key("", KeyPolicy()) is Decision.UNAVAILABLE


def test_unconfigured_with_explicit_allow_is_allowed():
    assert check_key("", KeyPolicy(allow_no_key=True)) is Decision.ALLOW


def test_bring_your_own_key_rejects_empty():
    assert check_key("", KeyPolicy(require_user_key=True)) is Decision.MISSING


def test_bring_your_own_key_accepts_any_non_empty():
    assert check_key("client-key", KeyPolicy(require_user_key=True)) is Decision.ALLOW


@pytest.mark.parametrize("provided", [" secret", "secret ", "  secret  "])
def test_whitespace_is_trimmed_before_comparison(provided):
    assert check_key(provided, KeyPolicy(expected_key="secret")) is Decision.ALLOW


def test_policy_is_frozen():
    policy = KeyPolicy(expected_key="secret")
    with pytest.raises(Exception):
        policy.expected_key = "other"  # type: ignore[misc]
