"""Run generated code in a child process. This is NOT isolation.

The child gets a cleaned environment (no API keys), a temporary folder, a timeout and
`-X utf8`. It still runs with the user's rights: a hostile model could harm the machine.
Use Docker or a similar jail before trusting specs from other people (see SECURITY.md).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

DEFAULT_TIMEOUT = 60
RUNNER = Path(__file__).with_name("_sandbox_runner.py")
ENV_KEEP = {"PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT",
            "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "LANG", "LC_ALL"}


def clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k.upper() in ENV_KEEP}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run_sandbox(files: dict[str, str], mode: str, plan: dict,
                 timeout: float, python: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="vg-verify-") as tmp:
        root = Path(tmp).resolve()
        for rel, content in files.items():
            target = (root / rel).resolve()
            if root not in target.parents:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        runner = root / "_vg_runner.py"
        runner.write_text(RUNNER.read_text(encoding="utf-8"), encoding="utf-8")
        plan_path, out_path = root / "_vg_plan.json", root / "_vg_out.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        try:
            proc = subprocess.run(
                [python, "-X", "utf8", str(runner), mode, str(plan_path), str(out_path)],
                cwd=tmp, env=clean_env(), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"status": f"timeout after {timeout:g}s"}
        if not out_path.exists():
            tail = (proc.stderr or proc.stdout or "").strip()[-600:]
            return {"status": f"crashed (exit {proc.returncode}): {tail}"}
        data = json.loads(out_path.read_text(encoding="utf-8"))
        data["status"] = "ok"
        return data
