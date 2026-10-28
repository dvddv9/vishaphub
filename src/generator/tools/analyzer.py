"""Run the Vishap Analyzer on the generated code (spec: check: analyzer).

The Analyzer is an external program, not a dependency: this module runs
`vishap analyze FILE --quiet --sarif OUT` as a subprocess and reads the
SARIF it writes. The command can be changed with VISHAP_ANALYZER_CMD
(for example `python -m src.cli` or a full path).

Unlike model-written code, the Analyzer is a trusted tool, so it gets
the normal environment (it needs its own LLM key from there or from its
.env). Note that the Analyzer sends the code it reads to its LLM.

Result status:
  passed    ran, no finding at level error
  failed    ran, at least one finding at level error
  skipped   command not found or not asked for; says so, never silent
  error     ran but gave no usable result (crash, timeout, bad SARIF)
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_COMMAND = "vishap"
DEFAULT_TIMEOUT = 600


@dataclass(frozen=True)
class AnalyzerFinding:
    file: str
    level: str      # error | warning | note
    rule: str
    message: str

    def to_dict(self) -> dict:
        return {"file": self.file, "level": self.level, "rule": self.rule,
                "message": self.message}


@dataclass(frozen=True)
class AnalyzerResult:
    status: str     # passed | failed | skipped | error
    findings: tuple[AnalyzerFinding, ...] = ()
    note: str = ""

    def to_dict(self) -> dict:
        return {"status": self.status, "note": self.note,
                "findings": [f.to_dict() for f in self.findings]}


def parse_sarif(data: dict, file: str) -> list[AnalyzerFinding]:
    out = []
    for run in data.get("runs", []):
        for r in run.get("results", []):
            msg = r.get("message", {})
            text = msg.get("text", "") if isinstance(msg, dict) else str(msg)
            out.append(AnalyzerFinding(file, str(r.get("level", "warning")),
                                       str(r.get("ruleId", "")), text.strip()[:300]))
    return out


def run_analyzer(files: dict[str, str], *, command: str | None = None,
                 timeout: float = DEFAULT_TIMEOUT) -> AnalyzerResult:
    """Analyze each file in `files` (the code files, not the tests)."""
    cmd = shlex.split(command or os.environ.get("VISHAP_ANALYZER_CMD") or DEFAULT_COMMAND)
    if not cmd or shutil.which(cmd[0]) is None:
        return AnalyzerResult("skipped", note=f"command not found: {cmd[0] if cmd else '(empty)'}")
    if not files:
        return AnalyzerResult("skipped", note="no code files to analyze")
    findings: list[AnalyzerFinding] = []
    with tempfile.TemporaryDirectory(prefix="vg-analyzer-") as tmp:
        root = Path(tmp).resolve()
        for rel, content in files.items():
            target = (root / Path(rel).name).resolve()   # flat copy, name kept
            target.write_text(content, encoding="utf-8")
            sarif = root / (target.name + ".sarif")
            try:
                proc = subprocess.run(
                    [*cmd, "analyze", str(target), "--quiet", "--sarif", str(sarif)],
                    cwd=tmp, capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=timeout)
            except subprocess.TimeoutExpired:
                return AnalyzerResult("error", tuple(findings), f"{rel}: timeout after {timeout:g}s")
            except OSError as e:
                return AnalyzerResult("error", tuple(findings), f"{rel}: {e}")
            if not sarif.exists():
                tail = (proc.stderr or proc.stdout or "").strip()[-300:]
                return AnalyzerResult("error", tuple(findings),
                                      f"{rel}: no SARIF (exit {proc.returncode}) {tail}")
            try:
                findings += parse_sarif(json.loads(sarif.read_text(encoding="utf-8")), rel)
            except (ValueError, OSError) as e:
                return AnalyzerResult("error", tuple(findings), f"{rel}: bad SARIF: {e}")
    bad = [f for f in findings if f.level == "error"]
    return AnalyzerResult("failed" if bad else "passed", tuple(findings),
                          f"{len(bad)} error, {len(findings) - len(bad)} other" if findings else "no findings")
