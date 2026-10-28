"""Quality gate: when does a run not get written?

The analog of Vishap's `tools/quality_gate.py`: thresholds in a small YAML file, one function that
evaluates a result against them and returns pass/fail with the reasons. CI uses the exit code.

Config file `.vishap-generator.yml` (next to the spec, else in the current folder):

    quality_gate:
      fail_on: [critical, high]   # requirement priorities that must be `passed`
      coverage_min: 80            # percent of lines the tests must run
      stale_days: 90              # a spec not updated for longer than this blocks
      max_critical_gaps: 0        # open critical gaps tolerated
      fail_on_analyzer: true      # analyzer errors block
      require_coverage: false     # coverage that could not be measured blocks
      baseline: .vishap/baseline.json   # accepted gaps (see tools/baseline.py)

Without a file the defaults above apply. An unknown key is an error, not silently ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from generator.config import COVERAGE_MIN, STALE_DAYS
from generator.tools.baseline import DEFAULT_PATH, compute_fingerprint, load_baseline

CONFIG_NAME = ".vishap-generator.yml"
PRIORITIES = ("critical", "high", "medium")


class QualityGateError(ValueError):
    """The gate config is not usable."""


@dataclass(frozen=True)
class Gate:
    fail_on: tuple[str, ...] = ("critical", "high")
    coverage_min: float = COVERAGE_MIN
    stale_days: int = STALE_DAYS
    max_critical_gaps: int = 0
    fail_on_analyzer: bool = True
    require_coverage: bool = False
    accepted_gaps: frozenset[str] = frozenset()

    def to_dict(self) -> dict:
        return {"fail_on": list(self.fail_on), "coverage_min": self.coverage_min,
                "stale_days": self.stale_days, "max_critical_gaps": self.max_critical_gaps,
                "fail_on_analyzer": self.fail_on_analyzer,
                "require_coverage": self.require_coverage,
                "accepted_gaps": sorted(self.accepted_gaps)}


@dataclass(frozen=True)
class GateResult:
    blocked: bool
    reasons: tuple[str, ...]
    accepted: tuple[str, ...] = ()      # gaps the baseline lets through, for the report

    def to_dict(self) -> dict:
        return {"blocked": self.blocked, "reasons": list(self.reasons),
                "accepted": list(self.accepted)}


KNOWN = {"fail_on", "coverage_min", "stale_days", "max_critical_gaps", "fail_on_analyzer",
         "require_coverage", "baseline"}


def _number(cfg: dict, key: str, kind, low, default):
    value = cfg.get(key, default)
    if isinstance(value, bool) or not isinstance(value, kind) or value < low:
        raise QualityGateError(f"quality_gate.{key} must be a number of at least {low}")
    return value


def parse_gate(cfg: dict, base_dir: Path | None = None) -> Gate:
    unknown = sorted(set(cfg) - KNOWN)
    if unknown:
        raise QualityGateError(f"unknown quality_gate key(s): {', '.join(unknown)}. "
                               f"Known: {', '.join(sorted(KNOWN))}")
    fail_on = cfg.get("fail_on", list(Gate().fail_on))
    if (not isinstance(fail_on, list) or not fail_on
            or any(p not in PRIORITIES for p in fail_on)):
        raise QualityGateError(f"quality_gate.fail_on must be a list of {', '.join(PRIORITIES)}")
    for key in ("fail_on_analyzer", "require_coverage"):
        if key in cfg and not isinstance(cfg[key], bool):
            raise QualityGateError(f"quality_gate.{key} must be true or false")
    cov = _number(cfg, "coverage_min", (int, float), 0, COVERAGE_MIN)
    if cov > 100:
        raise QualityGateError("quality_gate.coverage_min must be at most 100")
    base = base_dir or Path.cwd()
    baseline_path = Path(cfg["baseline"]) if cfg.get("baseline") else base / DEFAULT_PATH
    if not baseline_path.is_absolute():
        baseline_path = base / baseline_path
    return Gate(
        fail_on=tuple(fail_on), coverage_min=float(cov),
        stale_days=int(_number(cfg, "stale_days", int, 0, STALE_DAYS)),
        max_critical_gaps=int(_number(cfg, "max_critical_gaps", int, 0, 0)),
        fail_on_analyzer=cfg.get("fail_on_analyzer", True),
        require_coverage=cfg.get("require_coverage", False),
        accepted_gaps=load_baseline(baseline_path))


def load_quality_gate(*dirs: Path | str) -> Gate:
    """The gate from the first `.vishap-generator.yml` found in `dirs`; defaults if none.

    The API passes no folder, so a server never reads a config from its own disk.
    """
    for d in dirs:
        path = Path(d) / CONFIG_NAME
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, OSError, UnicodeDecodeError) as e:
            raise QualityGateError(f"{path}: {e}") from None
        if not isinstance(data, dict) or not isinstance(data.get("quality_gate", {}), dict):
            raise QualityGateError(f"{path}: expected a `quality_gate:` mapping")
        return parse_gate(data.get("quality_gate", {}), Path(d))
    base = Path(dirs[0]) if dirs else None
    return Gate(accepted_gaps=load_baseline(base / DEFAULT_PATH)) if base else Gate()


def evaluate_gate(design, build, verify, gate: Gate | None = None) -> GateResult:
    """The reasons a gated run would not write. No reasons: it may.

    Coverage that could not be measured (`skipped`) blocks only when `gate.require_coverage` is set.
    """
    gate = gate or Gate()
    reasons: list[str] = []
    for e in build.errors:
        reasons.append(f"build: {e}")
    for f in build.files:
        for e in f.errors:
            reasons.append(f"build: {f.path}: {e}")
    for r in verify.requirements:
        if r.priority in gate.fail_on and r.status != "passed":
            reasons.append(f"{r.id} ({r.priority}) is {r.status}")
    if gate.fail_on_analyzer and verify.analyzer and verify.analyzer.status == "failed":
        reasons.append("analyzer reported errors")
    if verify.coverage_status == "below":
        reasons.append(f"coverage {verify.coverage_percent:.0f}% is under {gate.coverage_min:.0f}%")
    if gate.require_coverage and verify.coverage_status == "skipped":
        reasons.append(f"coverage was not measured ({verify.coverage_note or 'no reason given'})")
    open_gaps, accepted = [], []
    for g in design.critical_gaps:
        (accepted if compute_fingerprint(g) in gate.accepted_gaps else open_gaps).append(g)
    if len(open_gaps) > gate.max_critical_gaps:
        for g in open_gaps:
            reasons.append(f"open critical gap {g.id}: {g.text}")
    if verify.spec_age_days > gate.stale_days:
        reasons.append(f"spec is stale ({verify.spec_age_days} days since update)")
    for p in verify.problems:
        reasons.append(f"verify: {p}")
    return GateResult(bool(reasons), tuple(reasons),
                      tuple(f"{g.id}: {g.text}" for g in accepted))
