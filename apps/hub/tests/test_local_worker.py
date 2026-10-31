"""The hub hands submitted code to a worker container, and never to the host when that fails."""
import os
import shutil

import pytest

from hub import local

FILES = {
    "calc.py": "def add(a, b):\n    return a + b\n",
    "test_calc.py": "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
}
SPEC = {"entry": "calc", "files": list(FILES), "exports": ["add"], "tests": ["test_calc.py"]}


@pytest.fixture(autouse=True)
def _image(monkeypatch):
    monkeypatch.setenv("VISHAP_HUB_WORKER_IMAGE", "vishap-validator:worker")


def _host_must_not_run(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the code was run on the host")
    monkeypatch.setattr("validator.engine.validate", boom)


def test_a_configured_worker_runs_the_check_and_the_result_names_the_isolation(monkeypatch):
    seen = {}

    def fake(root, spec, *, image, timeout, docker):
        seen.update(image=image, spec=spec, timeout=timeout, root_exists=os.path.isdir(root))
        return {"ok": True, "report": {"verdict": "PASS", "checks": []}, "error": "",
                "cleanup_confirmed": True, "name": "vishap-worker-abc"}

    monkeypatch.setattr("validator.container.run_in_container", fake)
    _host_must_not_run(monkeypatch)
    result = local.validate_code(FILES, SPEC)
    assert result["ok"] and result["report"]["verdict"] == "PASS"
    assert result["isolation"] == {"kind": "container", "image": "vishap-validator:worker",
                                   "container": "vishap-worker-abc", "cleanup_confirmed": True}
    assert seen["image"] == "vishap-validator:worker" and seen["spec"]["tests"] == ["test_calc.py"]
    assert seen["root_exists"] is True


def test_a_worker_that_fails_is_an_error_not_a_run_on_the_host(monkeypatch):
    monkeypatch.setattr("validator.container.run_in_container", lambda *a, **k: {
        "ok": False, "report": None, "error": "worker exceeded 120s and was killed",
        "cleanup_confirmed": True, "name": "x"})
    _host_must_not_run(monkeypatch)
    result = local.validate_code(FILES, SPEC)
    assert result["ok"] is False and "killed" in result["error"]


def test_when_every_slot_is_taken_the_hub_says_busy_and_runs_nothing(monkeypatch):
    import threading
    monkeypatch.setattr(local, "_SLOTS", threading.BoundedSemaphore(1))
    monkeypatch.setattr(local, "SLOT_WAIT_SECONDS", 0)
    local._SLOTS.acquire()
    monkeypatch.setattr("validator.container.run_in_container",
                        lambda *a, **k: pytest.fail("a worker was started past the slot limit"))
    _host_must_not_run(monkeypatch)
    result = local.validate_code(FILES, SPEC)
    assert result == {"ok": False, "error": "all validation workers are busy"}


def test_the_slot_is_released_after_a_run_and_after_a_crash(monkeypatch):
    import threading
    monkeypatch.setattr(local, "_SLOTS", threading.BoundedSemaphore(1))

    def crash(*a, **k):
        raise RuntimeError("docker went away")

    monkeypatch.setattr("validator.container.run_in_container", crash)
    with pytest.raises(RuntimeError):
        local._validate_in_worker("x", SPEC, "img")
    assert local._SLOTS.acquire(blocking=False)


def test_without_a_worker_the_in_process_refusal_still_applies(monkeypatch):
    monkeypatch.delenv("VISHAP_HUB_WORKER_IMAGE")
    result = local.validate_code(FILES, SPEC)
    assert result["ok"] is True and result["report"]["verdict"] == "FAIL"
    assert "no network namespace" in result["report"]["reason"]


IMAGE = os.getenv("VISHAP_TEST_WORKER_IMAGE", "")


@pytest.mark.skipif(not (IMAGE and shutil.which("docker")), reason="no Docker or VISHAP_TEST_WORKER_IMAGE")
def test_a_real_worker_container_passes_a_clean_deliverable(monkeypatch):
    monkeypatch.setenv("VISHAP_HUB_WORKER_IMAGE", IMAGE)
    result = local.validate_code(FILES, SPEC)
    assert result["ok"], result.get("error")
    assert result["report"]["verdict"] == "PASS"
    assert result["isolation"]["kind"] == "container" and result["isolation"]["cleanup_confirmed"] is True