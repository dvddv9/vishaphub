"""Host side of the worker: one throw-away container per run, no network, nothing of the host's.

`run_in_container` starts the image with `--network none`, a read-only root, a small noexec tmpfs,
all capabilities dropped, no new privileges, and caps on processes, memory, CPU and time. The
deliverable is mounted read-only. The container is removed after the run (or killed on timeout) and
the removal is confirmed: a result says whether the environment was really cleaned up.
Only the two variables the worker needs are passed in; the host's environment never is.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid

REPORT_PREFIX = "VISHAP_REPORT:"
EXPLOITS_PREFIX = "VISHAP_EXPLOITS:"

DEFAULT_LIMITS = {"memory": "256m", "cpus": "1", "pids": "64", "tmpfs": "32m"}


PROFILE_NAME = "worker-v1"


def profile(limits: dict | None = None) -> dict:
    """The sandbox profile a run used, as data: the flags and caps `run_in_container` applies.

    Deterministic on purpose (no container name, no time): it goes into the run's fingerprint, and
    another run with the same profile must produce the same bytes.
    """
    lim = {**DEFAULT_LIMITS, **(limits or {})}
    return {"name": PROFILE_NAME, "network": "none", "root": "read-only", "cap_drop": "ALL",
            "no_new_privileges": True, "tmpfs": f"{lim['tmpfs']},noexec,nosuid", "pids": lim["pids"],
            "memory": lim["memory"], "cpus": lim["cpus"], "deliverable": "read-only snapshot copy"}

def _docker(docker: str, *args: str, timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run([docker, *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, check=False)


def _gone(docker: str, name: str) -> bool:
    try:
        out = _docker(docker, "ps", "-a", "-q", "--filter", f"name=^{name}$", timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and not out.stdout.strip()


def _readable_copy(src: str, dest: str) -> str:
    """Snapshot of the deliverable that the container's user (uid 1000, not the host's) can read.

    A host directory made by mkdtemp is 0700 and owned by the caller; bind-mounted, it is unreadable
    inside the container on Linux. Copying also fixes what was run: later edits to `src` do not change it.
    """
    target = os.path.join(dest, "in")
    shutil.copytree(src, target, symlinks=False)
    for base, dirs, files in os.walk(target):
        for name in dirs:
            os.chmod(os.path.join(base, name), 0o755)
        for name in files:
            os.chmod(os.path.join(base, name), 0o644)
    os.chmod(target, 0o755)
    os.chmod(dest, 0o755)
    return target

def run_in_container(root: str, spec: dict, *, image: str, timeout: int = 120, docker: str = "docker",
                     limits: dict | None = None, extra_env: dict | None = None, mode: str = "validate") -> dict:
    """Validate `root` inside a fresh worker container. Never runs the code on the host.

    `mode="exploits"` runs the trusted exploit probes for `spec["exploit_targets"]` instead of the checks;
    the answer is then {"refused": "", "exploits": [...]} in `report`.
    Returns {"ok", "report", "error", "cleanup_confirmed", "name"}. `ok` is true only when the worker
    produced a report; a refusal by the worker (isolation not confirmed) is a report with FAIL.
    """
    lim = {**DEFAULT_LIMITS, **(limits or {})}
    name = f"vishap-worker-{uuid.uuid4().hex[:12]}"
    with tempfile.TemporaryDirectory(prefix="vishap-spec-") as tmp:
        spec_path = os.path.join(tmp, "spec.json")
        with open(spec_path, "w", encoding="utf-8") as fh:
            json.dump(spec, fh)
        os.chmod(spec_path, 0o644)
        staged = _readable_copy(root, tmp)
        cmd = [
            "run", "--rm", "--name", name,
            "--network", "none", "--read-only",
            "--tmpfs", f"/tmp:size={lim['tmpfs']},noexec,nosuid",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", lim["pids"], "--memory", lim["memory"], "--memory-swap", lim["memory"],
            "--cpus", lim["cpus"],
            "--mount", f"type=bind,source={staged},target=/in,readonly",
            "--mount", f"type=bind,source={spec_path},target=/spec.json,readonly",
            "-e", "VISHAP_VALIDATOR_ISOLATION=container", "-e", "VISHAP_VALIDATOR_REQUIRE_NETNS=1",
        ]
        for key, value in (extra_env or {}).items():
            cmd += ["-e", f"{key}={value}"]
        cmd += ["--entrypoint", "python", image, "-m", "validator.worker", "/in", "/spec.json"]
        if mode == "exploits":
            cmd.append("--exploits")
        prefix = EXPLOITS_PREFIX if mode == "exploits" else REPORT_PREFIX
        error = ""
        report = None
        try:
            done = _docker(docker, *cmd, timeout=timeout + 15)
            for line in reversed(done.stdout.splitlines()):
                if line.startswith(prefix):
                    report = json.loads(line[len(prefix):])
                    break
            if report is None:
                error = f"worker produced no report (exit {done.returncode}): {done.stderr.strip()[-300:]}"
        except subprocess.TimeoutExpired:
            error = f"worker exceeded {timeout}s and was killed"
            _docker(docker, "rm", "-f", name, timeout=30)
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            error = f"worker could not be run: {type(exc).__name__}"
            try:
                _docker(docker, "rm", "-f", name, timeout=30)
            except (OSError, subprocess.SubprocessError):
                pass
    return {"ok": report is not None, "report": report, "error": error,
            "cleanup_confirmed": _gone(docker, name), "name": name}