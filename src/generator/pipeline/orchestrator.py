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
from dataclasses import dataclass, field, replace
from pathlib import Path

from generator.tools.analyzer import AnalyzerResult, run_analyzer
from generator.config import CANDIDATE_WORKERS, INJECTION_STOP, REPRO_SEED, STRICT_MISSING_PCT
from generator.pipeline.build import BuildCheck, loss_pct
from generator.pipeline.candidates import generate_all, pick_best, summarize
from generator.pipeline.cove import CoveError, run_cove
from generator.pipeline.effort import EffortError, resolve as resolve_effort
from generator.pipeline.deliver import DeliverError, DeliverResult, deliver
from generator.pipeline.design import DesignResult, design
from generator.pipeline.generate import GenerateError, feedback_text, generate_code, repair_code
from generator.pipeline.intake import Requirement, requirements_from
from generator.llm import LLMConfig, LLMConfigError, LLMError, chat, config_from_env
from generator.llm._observe import observe_llm_result
from generator.observability.logging import bind_run_id, clear_context, get_logger
from generator.tools.spec import Spec, SpecError, load_spec
from generator.pipeline.textcheck import TextCheckError, check_text
from generator.pipeline.verdict import VerifyResult, apply_build_errors
from generator.pipeline.cost import sum_stage_costs
from generator.pipeline.stages import StageClock
from generator.pipeline.verify import verify
from generator.storage.history import add_entry
from generator.tools.injection import scan as scan_injection
from generator.tools.provenance import get_provenance
from generator.tools.strict import strict_message
from generator.tools.stride import with_proof
from generator.tools.redact import redact
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
    stages: list = field(default_factory=list)
    provenance: dict = field(default_factory=dict)
    effort: str = ""
    threats: list = field(default_factory=list)       # STRIDE table with proof (tools/stride.py)
    candidates: list = field(default_factory=list)    # best-of-N rows (pipeline/candidates.py), empty for one
    cove: dict | None = None                          # the COVE check (pipeline/cove.py), None when not run
    loss_pct: float = 0.0
    stopped: str = ""                                 # why the repair loop ended early, if it did

    @property
    def usage(self) -> dict:
        """Totals over the stages: model calls, tokens, and the cost (0.0 unless prices are set)."""
        return {"llm_calls": sum(s["llm_calls"] for s in self.stages),
                "tokens_in": sum(s["tokens_in"] for s in self.stages),
                "tokens_out": sum(s["tokens_out"] for s in self.stages),
                "tokens_reported": any(s["tokens_in"] or s["tokens_out"] for s in self.stages),
                "cost_usd": sum_stage_costs(self.stages),
                "duration_s": round(sum(s["duration_s"] for s in self.stages), 3)}

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
        d["threats"] = self.threats
        if self.candidates:
            d["candidates"] = self.candidates
        if self.cove is not None:
            d["cove"] = self.cove
        if self.build or self.files:
            d["loss_pct"] = self.loss_pct
        if self.stopped:
            d["repair_stopped"] = self.stopped
        d["effort"] = self.effort
        d["stages"] = self.stages
        d["usage"] = self.usage
        if self.provenance:
            d["provenance"] = self.provenance
        return d


def _count(reqs) -> str:
    counts: dict[str, int] = {}
    for r in reqs:
        counts[r.priority] = counts.get(r.priority, 0) + 1
    return ", ".join(f"{n} {p}" for p, n in counts.items())


def _metered(chat_fn: Callable[..., str]) -> Callable[..., str]:
    """The real `chat` counts its own calls; a stand-in (tests, a custom caller) is counted here."""
    if chat_fn is chat:
        return chat_fn

    def counted(messages, config=None, max_tokens=4096):
        answer = chat_fn(messages, config, max_tokens=max_tokens)
        observe_llm_result(messages, answer)
        return answer
    return counted


def _resolve_config(config: LLMConfig | None) -> LLMConfig | None:
    if config is not None:
        return config
    try:
        return config_from_env()
    except LLMConfigError:
        return None


def _redaction_counts(spec: Spec, reqs) -> dict[str, int]:
    """What `tools.redact` takes out of the text and the requirements before they go to the model."""
    counts: dict[str, int] = {}
    for text in (spec.text, *(r.text for r in reqs)):
        for kind, n in redact(text).applied:
            counts[kind] = counts.get(kind, 0) + n
    return counts


def run_pipeline(spec_path: str | Path, *, out_dir: str | Path | None = None,
                 gate: bool = False, force: bool = False, dry_run: bool = False,
                 no_llm: bool = False, repairs: int | None = None,
                 require_coverage: bool = False, text_check: bool | None = None,
                 quality_gate: Gate | None = None,
                 chat_fn: Callable[..., str] = chat, config: LLMConfig | None = None,
                 analyzer: Callable[[dict], AnalyzerResult] | None = run_analyzer,
                 today: dt.date | None = None, now: dt.datetime | None = None,
                 log: Callable[[str], None] = lambda line: None,
                 allow_write: bool = True, effort: str | None = None,
                 candidates: int | None = None, cove: bool | None = None,
                 strict: bool = False, repro: bool = False,
                 candidate_workers: int | None = None) -> PipelineResult:
    """`allow_write=False` never touches the disk (the API uses it): Deliver runs as a dry run.

    `effort` (quick, standard, deep) sets repairs, candidates, text check, analyzer and COVE together; a knob given
    on its own (`repairs`, `candidates`, `text_check`, `cove`) wins over it. `strict` refuses a spec that lacks too
    much of the key data. `repro` asks the model for temperature 0 and a fixed seed.

    Every stage is timed and its model calls counted (`PipelineResult.stages`, `.usage`).
    """
    res = PipelineResult(exit_code=0)
    clock = StageClock()
    try:
        try:
            eff = resolve_effort(effort, repairs=repairs, candidates=candidates, text_check=text_check, cove=cove)
        except EffortError as e:
            res.exit_code, res.error = 2, f"effort: {e}"
            return res
        if repro and eff.candidates > 1:
            res.exit_code, res.error = 2, "repro: temperature 0 gives the same answer every time, so candidates would be identical"
            return res
        if not eff.analyzer and analyzer is run_analyzer:
            analyzer = None
        res.effort = eff.name
        _run(res, clock, spec_path, eff, out_dir=out_dir, gate=gate, force=force, dry_run=dry_run,
             no_llm=no_llm, require_coverage=require_coverage, strict=strict, repro=repro,
             quality_gate=quality_gate, chat_fn=_metered(chat_fn), config=config, analyzer=analyzer,
             today=today, now=now, log=log, allow_write=allow_write, candidate_workers=candidate_workers)
    finally:
        res.stages = clock.records()
        clear_context()
    return res


def _run(res: PipelineResult, clock: StageClock, spec_path, eff, *, out_dir, gate, force, dry_run, no_llm,
         require_coverage, strict, repro, quality_gate, chat_fn, config, analyzer, today, now,
         log, allow_write, candidate_workers) -> None:
    repairs, text_check = eff.repairs, eff.text_check
    logger = get_logger("pipeline")
    try:
        spec = load_spec(spec_path)
    except (SpecError, OSError) as e:
        res.exit_code, res.error = 2, f"spec: {e}"
        return
    res.spec = spec
    bind_run_id(spec.sha256[:12])
    hits = scan_injection(spec)
    if len(hits) >= INJECTION_STOP:
        res.exit_code = 2
        res.error = (f"spec: {len(hits)} phrases aimed at the model (limit {INJECTION_STOP}), "
                     f"for example \"{hits[0].phrase}\" in {hits[0].field}; the run is stopped")
        logger.error("spec stopped: %d injection-like phrases", len(hits))
        return
    logger.info("run started", extra={"fields": {"spec": Path(spec_path).name, "gate": gate}})

    if quality_gate is None:
        try:     # the API (allow_write=False) never reads a config from the server's disk
            quality_gate = load_quality_gate(Path(spec_path).resolve().parent, Path.cwd()) \
                if allow_write else Gate()
        except QualityGateError as e:
            res.exit_code, res.error = 2, f"spec: {e}"
            return
    if require_coverage:
        quality_gate = replace(quality_gate, require_coverage=True)
    res.quality_gate = quality_gate

    # 1 Intake
    with clock.stage("intake"):
        reqs = requirements_from(spec)
    res.requirements = reqs
    log(f"[Intake]    {len(reqs)} requirements ({_count(reqs)})")

    # 2 Design (and the text check, the one model call of this stage)
    with clock.stage("design"):
        d = design(spec, reqs)
    res.design = d
    log(f"[Design]    {len(d.files)} files, gaps: {len(d.critical_gaps)} critical, "
        f"{len(d.gaps) - len(d.critical_gaps)} other")
    for g in d.gaps:
        log(f"            {g.id} {g.severity}: {g.text}")
    mark = {"covered": "ok", "partial": "~", "not_covered": "NO", "not_applicable": "-"}
    log("            STRIDE      " + "  ".join(f"{t.letter} {mark[t.status]}" for t in d.threats))
    res.threats = with_proof(d.threats, None)
    limit = quality_gate.strict_missing_pct if quality_gate.strict_missing_pct is not None \
        else (STRICT_MISSING_PCT if strict else None)
    refusal = strict_message(spec, limit)
    if refusal:
        res.exit_code, res.error = 2, f"spec: {refusal}"
        return

    if repro and not no_llm:        # every model call of the run, the text check included
        try:
            config = replace(config or config_from_env(), temperature=0.0, seed=REPRO_SEED)
        except LLMConfigError as e:
            res.exit_code, res.error = 2, f"build: {e}"
            return

    if text_check and not no_llm:
        try:
            with clock.stage("design"):
                d, dropped = check_text(spec, reqs, d, chat_fn=chat_fn, config=config)
        except (LLMConfigError, LLMError, TextCheckError) as e:
            log(f"            text check skipped: {e}")
            logger.warning("text check skipped: %s", e)
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
        return

    redaction = _redaction_counts(spec, reqs)
    if redaction:
        log("            redacted before the model: " + ", ".join(f"{n} {k}" for k, n in sorted(redaction.items())))
    res.provenance = get_provenance(spec, spec_path, _resolve_config(config), redaction)

    # 3 Build
    limits = dict(today=today, coverage_min=quality_gate.coverage_min, stale_days=quality_gate.stale_days)
    use_analyzer = analyzer if spec.data.get("check", "analyzer") == "analyzer" else None
    n_cand = eff.candidates
    if n_cand == 1:
        try:
            with clock.stage("build"):
                gen = generate_code(spec, reqs, d, chat_fn=chat_fn, config=config)
        except (LLMConfigError, LLMError, GenerateError) as e:
            res.exit_code, res.error = 2, f"build: {e}"
            logger.error("build failed: %s", e)
            return
        files, build = gen.files, gen.check
    else:
        def make(i: int):
            g = generate_code(spec, reqs, d, chat_fn=chat_fn, config=config)
            return g.files, g.check
        with clock.stage("build"):
            cands = generate_all(n_cand, make, candidate_workers or min(n_cand, CANDIDATE_WORKERS))
        for c in cands:
            if c.files is not None:
                with clock.stage("verify"):
                    c.verify = verify(spec, reqs, d, c.files, **limits)
        best = pick_best(cands)
        if best is None:
            res.exit_code, res.error = 2, f"build: all {n_cand} candidates failed: {cands[0].error}"
            logger.error("build failed: every candidate")
            return
        res.candidates = summarize(cands, best)
        for row in res.candidates:
            what = (f"{row['verdict']}, {row['passed']}/{row['requirements']} passed, build "
                    f"{'ok' if row['build_ok'] else 'errors'}") if "verdict" in row else f"failed: {row['error']}"
            log(f"[Build]     candidate {row['index'] + 1}/{n_cand}: {what}{'  <- chosen' if row['chosen'] else ''}")
        files, build = best.files, best.check
    res.llm_used = True
    tests = sum(len(f.tests_found) for f in build.files)
    log(f"[Build]     {len(files)} files + {tests} tests, check: {'ok' if build.ok else 'errors'}")

    # 4 Verify, with repair rounds (a repair round is Build again)
    rounds = 0
    seen: list[frozenset] = []          # the problems of each finished round: a repeat means no progress
    earlier: list[str] = []
    stopped = ""
    while True:
        with clock.stage("verify"):
            v = verify(spec, reqs, d, files, **limits)
            if v.code_verdict == "passed" and build.ok and use_analyzer:
                v = verify(spec, reqs, d, files, analyzer=use_analyzer, **limits)
        done = v.code_verdict == "passed" and build.ok
        log(f"[Verify]    round {rounds}: {v.passed}/{len(v.requirements)} passed, "
            f"verdict {v.code_verdict}")
        if done or rounds >= max(0, repairs):
            break
        problems_now = feedback_text(build, v)
        signature = frozenset(problems_now.splitlines())
        if signature in seen:
            stopped = f"round {rounds} has the same problems as round {seen.index(signature)}; another repair would not help"
            log(f"            repair stopped: {stopped}")
            break
        seen.append(signature)
        earlier.append(problems_now)
        rounds += 1
        try:
            with clock.stage("build"):
                gen = repair_code(spec, reqs, d, files, build, v, chat_fn=chat_fn, config=config,
                                  earlier=tuple(earlier[:-1]))
        except (LLMConfigError, LLMError, GenerateError) as e:
            log(f"            repair round {rounds} failed: {e}")
            logger.warning("repair round %d failed: %s", rounds, e)
            rounds -= 1
            break
        files, build = gen.files, gen.check
        log(f"[Repair]    round {rounds}: model sent {len(files)} files")
    v = apply_build_errors(v, [*build.errors, *(f"{f.path}: {e}" for f in build.files for e in f.errors)])
    loss, missing = loss_pct(d, files)
    res.loss_pct = loss
    if loss > quality_gate.max_loss_pct:
        v = replace(v, problems=v.problems + (
            f"incomplete: the model left out {loss:g}% of the planned code and test files ({', '.join(missing)})",))
    if stopped:
        v = replace(v, notes=v.notes + (f"repair stopped early: {stopped}",))
        res.stopped = stopped

    # COVE: what the spec says against what the code does (optional, one more model call)
    if eff.cove and not build.errors:
        try:
            with clock.stage("verify"):
                cv = run_cove(spec, reqs, d, files, chat_fn=chat_fn, config=config)
        except (LLMConfigError, LLMError, CoveError) as e:
            log(f"            COVE skipped: {e}")
            logger.warning("COVE skipped: %s", e)
        else:
            res.cove = cv.to_dict()
            if cv.status == "ok":
                v = replace(v, cove_mismatches=tuple(cv.mismatches),
                            notes=v.notes + tuple(f"COVE mismatch: {m}" for m in cv.mismatches)
                            + ((f"COVE: {len(cv.unclear)} value(s) the spec does not decide, see the report",)
                               if cv.unclear else ()))
                log(f"            COVE: {len(cv.probes)} values, {len(cv.mismatches)} mismatch(es), "
                    f"{len(cv.unclear)} undecided by the spec")
            else:
                log(f"            COVE skipped: {cv.note}")
    res.files, res.build, res.verify, res.repair_rounds = files, build, v, rounds
    res.threats = with_proof(d.threats, v)
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

    # 5 Deliver
    if out_dir is None and allow_write:
        res.exit_code, res.error = 2, "deliver: no output folder (--out)"
        return
    try:
        with clock.stage("deliver"):
            if allow_write:
                out = deliver(spec=spec, requirements=reqs, design=d, files=files, build=build,
                              verify=v, out_root=out_dir, gate=gate, force=force,
                              dry_run=dry_run, quality_gate=quality_gate, now=now,
                              provenance=res.provenance, extra=_trace_extra(res))
            else:   # nothing on disk is read or written: an empty folder stands in for the target
                with tempfile.TemporaryDirectory(prefix="vg-dry-") as empty:
                    out = deliver(spec=spec, requirements=reqs, design=d, files=files, build=build,
                                  verify=v, out_root=Path(empty) / "out", gate=gate, force=force,
                                  dry_run=True, quality_gate=quality_gate, now=now,
                                  provenance=res.provenance, extra=_trace_extra(res))
    except DeliverError as e:
        res.exit_code, res.error = 2, f"deliver: {e}"
        logger.error("deliver failed: %s", e)
        return
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
    if allow_write and out_dir is not None and out.written:    # a blocked run writes nothing, history included
        res.stages = clock.records()                            # the history entry carries the usage so far
        _record_history(out_dir, res, spec, out)
    logger.info("run finished", extra={"fields": {"verdict": v.code_verdict, "exit": res.exit_code}})


def _trace_extra(res: PipelineResult) -> dict:
    """What a run adds to the trace besides Verify's evidence: no times, nothing that varies between runs of the same inputs."""
    extra: dict = {"effort": res.effort, "threats": res.threats, "loss_pct": res.loss_pct}
    if res.candidates:
        extra["candidates"] = res.candidates
    if res.cove is not None:
        extra["cove"] = res.cove
    if res.stopped:
        extra["repair_stopped"] = res.stopped
    return extra


def _record_history(out_dir, res: PipelineResult, spec: Spec, out: DeliverResult) -> None:
    """One line in `<out>/.vishap/history.json`; a history that cannot be written never fails a run."""
    try:
        add_entry(out_dir, {
            "run_id": out.run_id, "spec": Path(spec.path).name, "spec_sha256": spec.sha256,
            "verdict": res.verify.code_verdict, "written": out.written, "blocked": out.blocked,
            "forced": out.forced, "repair_rounds": res.repair_rounds, "effort": res.effort,
            "candidates": len(res.candidates) or 1,
            "files": [a.path for a in out.actions], "usage": res.usage,
            "model": (res.provenance.get("model") or {}).get("name", "")})
    except OSError as e:
        get_logger("pipeline").warning("history not written: %s", e)
