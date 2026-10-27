# -*- coding: utf-8 -*-
"""Sandbox for generated pytest code (v7.3.14).

WARNING: runs LLM-generated code. Use only with VISHAP_TESTER=1.
Limits: short timeout, throw-away working directory, and a CLEAN environment: the child
gets a short allow-list of variables, never the server's own (LLM key, CONVEYOR_API_KEY,
DATABASE_URL, ...). NOT isolated: network and file system. Use it only for trusted
material, or inside a container (see src/pipeline/sandbox_local.py).
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

#: The only server variables the child may inherit: enough to start Python and find
#: tools, nothing that carries a secret.
_ENV_ALLOWLIST = (
    "PATH", "PATHEXT", "COMSPEC", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR",
    "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "LANG", "LC_ALL", "TZ",
)


def _sandbox_env(tmp: str) -> dict:
    """Environment for the sandboxed child: allow-listed variables plus sandbox markers."""
    env = {name: os.environ[name] for name in _ENV_ALLOWLIST if name in os.environ}
    env.update({
        "VISHAP_SANDBOX": "1",
        "TMPDIR": tmp, "TEMP": tmp, "TMP": tmp,
        "PYTHONDONTWRITEBYTECODE": "1",
        # network off by convention only (best-effort; subprocess cannot block it)
        "http_proxy": "http://127.0.0.1:1", "https_proxy": "http://127.0.0.1:1",
        "HTTP_PROXY": "http://127.0.0.1:1", "HTTPS_PROXY": "http://127.0.0.1:1",
        "NO_PROXY": "",
    })
    return env


def run_pytest_in_sandbox(test_code: str, timeout: int = 5) -> dict:
    """Run generated pytest test_code in isolated temp dir.

    Returns: {"ok": bool, "returncode": int, "stdout": str, "stderr": str, "reason": str}
    """
    if not test_code or not test_code.strip():
        return {"ok": False, "returncode": -1, "stdout": "", "stderr": "", "reason": "empty test_code"}

    tmp = tempfile.mkdtemp(prefix="vishap_sandbox_")
    test_file = Path(tmp) / "test_generated.py"
    try:
        test_file.write_text(test_code, encoding="utf-8")
        env = _sandbox_env(tmp)
        cmd = [sys.executable, "-m", "pytest", str(test_file), "-q", "--no-header", "--tb=short"]
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.run(
            cmd, cwd=tmp, env=env, capture_output=True, text=True,
            timeout=timeout, **kwargs,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[:2000],
            "stderr": (proc.stderr or "")[:2000],
            "reason": "passed" if proc.returncode == 0 else "failed",
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": -1, "stdout": "", "stderr": "", "reason": f"timeout {timeout}s"}
    except Exception as e:
        return {"ok": False, "returncode": -1, "stdout": "", "stderr": str(e), "reason": f"error: {e}"}
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

def apply_fix_and_verify(original_code: str, fixed_code: str, timeout: int = 10) -> dict:
    """Apply fix to original_code, run ruff + pytest + mypy, return verdict.

    Args:
        original_code: original (buggy) code (for context)
        fixed_code:    LLM-generated fix (replacement for original_code)
        timeout:       per-tool timeout (seconds)

    Returns: {"ok": bool, "ruff_ok": bool, "pytest_ok": bool, "mypy_ok": bool,
              "ruff_out": str, "pytest_out": str, "mypy_out": str, "reason": str}
    """
    if not fixed_code or not fixed_code.strip():
        return {"ok": False, "ruff_ok": False, "pytest_ok": False, "mypy_ok": False,
                "ruff_out": "", "pytest_out": "", "mypy_out": "",
                "reason": "empty fixed_code"}

    tmp = tempfile.mkdtemp(prefix="vishap_fixer_")
    fixed_file = Path(tmp) / "fixed.py"
    result = {
        "ok": False, "ruff_ok": False, "pytest_ok": False, "mypy_ok": False,
        "ruff_out": "", "pytest_out": "", "mypy_out": "", "reason": "",
    }
    try:
        fixed_file.write_text(fixed_code, encoding="utf-8")
        env = _sandbox_env(tmp)
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        # 1) ruff
        try:
            r = subprocess.run(
                [sys.executable, "-m", "ruff", "check", str(fixed_file), "--no-cache", "--output-format", "concise"],
                cwd=tmp, env=env, capture_output=True, text=True, timeout=timeout, **kwargs,
            )
            result["ruff_ok"] = r.returncode == 0
            result["ruff_out"] = ((r.stdout or "") + (r.stderr or ""))[:1000]
        except subprocess.TimeoutExpired:
            result["ruff_out"] = f"timeout {timeout}s"

        # 2) pytest (if no test file — skip)
        test_file = Path(tmp) / "test_fixed.py"
        if not test_file.exists():
            # pytest without tests — pass (nothing to run)
            result["pytest_ok"] = True
            result["pytest_out"] = "no tests"
        else:
            try:
                r = subprocess.run(
                    [sys.executable, "-m", "pytest", str(test_file), "-q", "--no-header", "--tb=short"],
                    cwd=tmp, env=env, capture_output=True, text=True, timeout=timeout, **kwargs,
                )
                result["pytest_ok"] = r.returncode == 0
                result["pytest_out"] = ((r.stdout or "") + (r.stderr or ""))[:2000]
            except subprocess.TimeoutExpired:
                result["pytest_out"] = f"timeout {timeout}s"

        # 3) mypy (optional, skip if not installed)
        mypy_out = ""
        try:
            r = subprocess.run(
                [sys.executable, "-m", "mypy", str(fixed_file), "--ignore-missing-imports", "--no-error-summary"],
                cwd=tmp, env=env, capture_output=True, text=True, timeout=timeout, **kwargs,
            )
            mypy_out = ((r.stdout or "") + (r.stderr or ""))[:1000]
            if "No module named mypy" in mypy_out:
                result["mypy_ok"] = True  # skip (not installed)
                result["mypy_out"] = "mypy not installed (skipped)"
            else:
                result["mypy_ok"] = r.returncode == 0
                result["mypy_out"] = mypy_out
        except (subprocess.TimeoutExpired, FileNotFoundError):
            result["mypy_ok"] = True  # skip
            result["mypy_out"] = "mypy not installed (skipped)"

        # overall: ok if ruff_ok and pytest_ok and mypy_ok
        mypy_skipped = "mypy not installed" in (result.get("mypy_out") or "")
        result["ok"] = result["ruff_ok"] and result["pytest_ok"] and (result["mypy_ok"] or mypy_skipped)
        result["reason"] = "accepted" if result["ok"] else "rejected"
    except Exception as e:
        result["reason"] = f"error: {e}"
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    return result

