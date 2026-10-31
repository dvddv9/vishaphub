"""The container counts as isolation only when it confirms it from the inside."""
import pytest

from validator import safe
from validator.engine import validate
from validator.models import Spec, Verdict


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(safe, "_NET_OFF", [])          # no namespace on this host
    monkeypatch.delenv("VISHAP_VALIDATOR_REQUIRE_NETNS", raising=False)
    monkeypatch.delenv("VISHAP_VALIDATOR_NO_NETWORK", raising=False)
    monkeypatch.setattr(safe, "_CONTAINER", None)


def confirmed(**over):
    ev = {"declared": True, "ok": True, "interfaces": ["lo"], "only_loopback": True,
          "outbound_refused": True, "root_read_only": True, "env_clean": True, "secret_env_names": []}
    ev.update(over)
    ev["ok"] = all(ev[k] for k in ("only_loopback", "outbound_refused", "root_read_only", "env_clean"))
    return ev


def test_a_confirmed_container_is_isolation(monkeypatch):
    monkeypatch.setattr(safe, "_CONTAINER", confirmed())
    assert safe.isolation() == "container"
    assert safe.refusal(require_netns=True) == ""
    assert "container" in safe.isolation_note()


def test_an_undeclared_host_is_not_a_container(monkeypatch):
    monkeypatch.delenv("VISHAP_VALIDATOR_ISOLATION", raising=False)
    assert safe.container_evidence()["declared"] is False
    assert safe.isolation() == "guard"
    assert "no network namespace" in safe.refusal(require_netns=True)


@pytest.mark.parametrize("failing", ["only_loopback", "outbound_refused", "root_read_only", "env_clean"])
def test_a_declared_container_that_fails_one_check_runs_nothing(monkeypatch, failing):
    monkeypatch.setattr(safe, "_CONTAINER", confirmed(**{failing: False}))
    assert safe.isolation() == "guard"
    why = safe.refusal(require_netns=True)
    assert "did not confirm" in why
    assert (failing in why) or (failing == "env_clean" and "secrets in the worker environment" in why)


def test_the_refusal_stops_the_run_before_any_code(tmp_path, monkeypatch):
    monkeypatch.setattr(safe, "_CONTAINER", confirmed(outbound_refused=False))
    marker = tmp_path / "ran.txt"
    (tmp_path / "test_x.py").write_text(f"open({str(marker)!r}, 'w').write('x')\n\ndef test_x():\n    pass\n")
    report = validate(str(tmp_path), Spec(tests=["test_x.py"]), require_netns=True)
    assert report.verdict is Verdict.FAIL
    assert not marker.exists()


def test_switching_the_network_guard_off_is_never_isolation(monkeypatch):
    monkeypatch.setenv("VISHAP_VALIDATOR_NO_NETWORK", "0")
    monkeypatch.setattr(safe, "_CONTAINER", confirmed())
    assert safe.isolation() == "none"
    assert safe.refusal(require_netns=True) != ""

def test_a_secret_in_the_worker_environment_is_named_and_refused(monkeypatch):
    monkeypatch.setattr(safe, "_CONTAINER", confirmed(env_clean=False, secret_env_names=["STRIPE_API_KEY"]))
    why = safe.refusal(require_netns=True)
    assert "STRIPE_API_KEY" in why and "nothing was run" in why
    assert "sk_" not in why   # names only, never values