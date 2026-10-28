"""The five stages end to end: Intake, Design, Build, Verify, Deliver.

`run_pipeline` is what the command line and the REST API call. It never
prints; it reports each stage through the `log` callback and returns one
result object. Build asks the model; when Verify finds problems, up to
`repairs` repair rounds send them back to the model.

Exit codes (used by the command line):
  0  done (or gate passed)
  1  the gate blocked the write
  2  error: bad spec, model failure, unusable answer, write failure
"""

from __future__ import annotations

import datetime as dt
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from generator.tools.analyzer import AnalyzerResult, run_analyzer
from generator.config import DEFAULT_REPAIRS
from generator.pipeline.build import BuildCheck
from generator.pipeline.deliver import DeliverError, DeliverResult, deliver
from generator.pipeline.design import DesignResult, design
from generator.pipeline.generate import GenerateError, generate_code, repair_code
from generator.pipeline.intake import Requirement, requirements_from
from generator.llm import LLMConfig, LLMConfigError, LLMError, chat
from generator.tools.spec import Spec, SpecError, load_spec
from generator.pipeline.textcheck import TextCheckError, check_text
from generator.pipeline.verdict import VerifyResult, apply_build_errors
from generator.pipeline.verify import verify
from generator.tools.baseline import compute_fingerprint
from generator.tools.quality_gate import Gate, QualityGateError, load_quality_gate



@dataclass
class PipelineResult:
    exit_code: int
    error: str = ""
    spec: Spec | None = None
    requirements: tuple[Requirement, ...] = ()
    design: DesignResult | None = None
    files: dict | None = None
    build: BuildCheck | None = None
    verify: VerifyResult | None = None
    deliver: DeliverResult | None = None
    repair_rounds: int = 0
    llm_used: bool = False
    quality_gate: Gate | None = None

    def to_dict(self) -> dict:
        d: dict = {"exit_code": self.exit_code, "error": self.error,
                   "repair_rounds": self.repair_rounds, "llm_used": self.llm_used}
        if self.spec:
            d["spec"] = {"sha256": self.spec.sha256, "updated": self.spec.updated.isoformat()}
        d["requirements"] = [{"id": r.id, "text": r.text, "priority": r.priority}
                             for r in self.requirements]
        if self.design:
            d["design"] = self.design.to_dict()
        if self.build:
            d["build"] = self.build.to_dict()
        if self.verify:
            d["verify"] = self.verify.to_dict()
        if self.deliver:
            d["deliver"] = self.deliver.to_dict()
        return d


def _count(reqs) -> str:
    counts: dict[str, int] = {}
    for r in reqs:
        counts[r.priority] = counts.get(r.priority, 0) + 1
    return ", ".join(f"{n} {p}" for p, n in counts.items())


def run_pipeline(spec_path: str | Path, *, out_dir: str | Path | None = None,
                 gate: bool = False, force: bool = False, dry_run: bool = False,
                 no_llm: bool = False, repairs: int = DEFAULT_REPAIRS,
                 require_coverage: bool = False, text_check: bool = True,
                 quality_gate: Gate | None = None,
                 chat_fn: Callable[..., str] = chat, config: LLMConfig | None = None,
                 analyzer: Callable[[dict], AnalyzerResult] | None = run_analyzer,
                 today: dt.date | None = None, now: dt.datetime | None = None,
                 log: Callable[[str], None] = lambda line: None,
                 allow_write: bool = True) -> PipelineResult:
    """`allow_write=False` never touches the disk (the API uses it): Deliver runs as a dry run."""
    res = PipelineResult(exit_code=0)
    try:
        spec = load_spec(spec_path)
    except SpecError as e:
        res.exit_code, res.error = 2, f"spec: {e}"
        return res
    except OSError as e:
        res.exit_code, res.error = 2, f"spec: {e}"
        return res
    res.spec = spec

    if quality_gate is None:
        try:     # the API (allow_write=False) never reads a config from the server's disk
            quality_gate = load_quality_gate(Path(spec_path).resolve().parent, Path.cwd()) \
                if allow_write else Gate()
        except QualityGateError as e:
            res.exit_code, res.error = 2, f"spec: {e}"
            return res
    if require_coverage:
        quality_gate = replace(quality_gate, require_coverage=True)
    res.quality_gate = quality_gate

    reqs = requirements_from(spec)
    res.requirements = reqs
    log(f"[Intake]    {len(reqs)} requirements ({_count(reqs)})")

    d = design(spec, reqs)
    res.design = d
    log(f"[Design]    {len(d.files)} files, gaps: {len(d.critical_gaps)} critical, "
        f"{len(d.gaps) - len(d.critical_gaps)} other")
    for g in d.gaps:
        log(f"            {g.id} {g.severity}: {g.text}")

    if text_check and not no_llm:
        try:
            d, dropped = check_text(spec, reqs, d, chat_fn=chat_fn, config=config)
        except (LLMConfigError, LLMError, TextCheckError) as e:
            log(f"            text check skipped: {e}")
        else:
            res.design = d
            added = [g for g in d.gaps if g.source and g.source.field == "text"]
            log(f"            text check: {len(added)} statement(s) no requirement covers"
                + (f", {dropped} dropped (not quoted from the text)" if dropped else ""))
            for g in added:
                log(f"            {g.id} {g.severity}: {g.text}")

    if no_llm:
        log("            --no-llm: stopping after Design")
        if gate:
            open_gaps = [g for g in d.critical_gaps
                         if compute_fingerprint(g) not in quality_gate.accepted_gaps]
            if len(open_gaps) > quality_gate.max_critical_gaps:
                res.exit_code = 1
        return res

    # Build
    try:
        gen = generate_code(spec, reqs, d, chat_fn=chat_fn, config=config)
    except (LLMConfigError, LLMError, GenerateError) as e:
        res.exit_code, res.error = 2, f"build: {e}"
        return res
    res.llm_used = True
    files, build = gen.files, gen.check
    tests = sum(len(f.tests_found) for f in build.files)
    log(f"[Build]     {len(files)} files + {tests} tests, check: {'ok' if build.ok else 'errors'}")

    # Verify, with repair rounds
    use_analyzer = analyzer if spec.data.get("check", "analyzer") == "analyzer" else None
    rounds = 0
    while True:
        limits = dict(today=today, coverage_min=quality_gate.coverage_min,
                      stale_days=quality_gate.stale_days)
        v = verify(spec, reqs, d, files, **limits)
        if v.code_verdict == "passed" and build.ok and use_analyzer:
            v = verify(spec, reqs, d, files, analyzer=use_analyzer, **limits)
        done = v.code_verdict == "passed" and build.ok
        log(f"[Verify]    round {rounds}: {v.passed}/{len(v.requirements)} passed, "
            f"verdict {v.code_verdict}")
        if done or rounds >= max(0, repairs):
            break
        rounds += 1
        try:
            gen = repair_code(spec, reqs, d, files, build, v, chat_fn=chat_fn, config=config)
        except (LLMConfigError, LLMError, GenerateError) as e:
            log(f"            repair round {rounds} failed: {e}")
            rounds -= 1
            break
        files, build = gen.files, gen.check
        log(f"[Repair]    round {rounds}: model sent {len(files)} files")
    v = apply_build_errors(v, [*build.errors, *(f"{f.path}: {e}" for f in build.files for e in f.errors)])
    res.files, res.build, res.verify, res.repair_rounds = files, build, v, rounds
    cov = (f"{v.coverage_percent:.0f}% (minimum {quality_gate.coverage_min:.0f}%)" if v.coverage_percent is not None
           else f"{v.coverage_status} ({v.coverage_note})")
    log(f"            coverage: {cov}")
    age = f"{'stale' if v.spec_stale else 'fresh'}, updated {spec.updated} ({v.spec_age_days} days ago)"
    log(f"            spec: {age}")
    if v.analyzer:
        log(f"            analyzer: {v.analyzer.status} ({v.analyzer.note})")
    for n in v.notes:
        log(f"            note: {n}")
    for p in v.problems:
        log(f"            problem: {p}")

    # Deliver
    if out_dir is None and allow_write:
        res.exit_code, res.error = 2, "deliver: no output folder (--out)"
        return res
    try:
        if allow_write:
            out = deliver(spec=spec, requirements=reqs, design=d, files=files, build=build,
                          verify=v, out_root=out_dir, gate=gate, force=force,
                          dry_run=dry_run, quality_gate=quality_gate, now=now)
        else:   # nothing on disk is read or written: an empty folder stands in for the target
            with tempfile.TemporaryDirectory(prefix="vg-dry-") as empty:
                out = deliver(spec=spec, requirements=reqs, design=d, files=files, build=build,
                              verify=v, out_root=Path(empty) / "out", gate=gate, force=force,
                              dry_run=True, quality_gate=quality_gate, now=now)
    except DeliverError as e:
        res.exit_code, res.error = 2, f"deliver: {e}"
        return res
    res.deliver = out
    if out.blocked and not out.written:
        log("[Deliver]   BLOCKED by the gate, nothing written")
        for r in out.gate.reasons:
            log(f"            - {r}")
        res.exit_code = 1
    if out.gate.accepted:
        log("            accepted by the baseline: " + "; ".join(out.gate.accepted))
    elif out.dry_run:
        log("[Deliver]   dry run, nothing written")
    else:
        log(f"[Deliver]   {sum(a.action != 'unchanged' for a in out.actions)} files written"
            + (" (FORCED past the gate)" if out.forced else ""))
        for a in out.actions:
            log(f"            {a.action:<11} {a.path}")
        log(f"            rollback: {out.rollback_hint}")
    return res
