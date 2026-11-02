"""A validator that had nowhere safe to run must say so: its FAIL is about the host, not the code."""
from hub.pipeline import _validator_could_not_run


def test_an_isolation_failure_is_recognised_as_a_validator_that_ran_nothing():
    checks = {"validator": {"verdict": "FAIL", "checks": [{"name": "isolation", "ok": False, "skipped": False}]}}
    assert _validator_could_not_run(checks)


def test_a_real_validator_failure_is_not_blamed_on_the_host():
    checks = {"validator": {"verdict": "FAIL", "checks": [{"name": "static", "ok": False, "skipped": False},
                                                          {"name": "isolation", "ok": True, "skipped": False}]}}
    assert not _validator_could_not_run(checks)
    assert not _validator_could_not_run({"validator": None})
    assert not _validator_could_not_run({})