"""Pipeline: execute a plan, keep the session, stop when nothing improves.

One path, one verdict. The model proposes (``proposal.py``), the rules decide
(``local.py``: the validator's six stages, the analyser's patterns), and this module
merges what came back. Everything runs in this process: one URL means one deployment,
and calling our own services over the network would add a cold start and a second
place where a key can be wrong.

The rules that make the loop honest:

* **nothing ran is not a pass.** An empty plan, a plan without stages, a stage that
  returned no verdict, or a stage that crashed all end in ERROR. `ok` is true only
  when the verdict is explicitly safe.
* **a crash stops the run.** A stage that cannot produce a verdict is not a stage that
  passed; later stages would be measuring a vacuum.
* **a FAIL verdict does not stop the run.** Failing tests and a security finding are
  different questions, and dangerous code must still reach the analyser. The verdict is
  the strictest seen, never the last one.
* **the model may only make it stricter.** Its own verdict is a recommendation: merged
  with the rules by rank, so «looks safe» can never soften a failing test, while a
  model that smells danger can raise it.
* **generated code is checked like any other code.** Whatever the model proposes as a
  patch goes through the validator and the analyser — the hub does not take the
  author's word for its own output.
* **iterations stop early** when no stage changes its answer: the same words twice mean
  the next pass spends the same tokens for the same result. The generator runs once;
  later passes re-check the same patch instead of paying the model again.
* **verdicts are normalised** by ``verdicts.py`` — one ranking for the whole hub.
* every hop is appended to the trace, so the client can replay the run.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import evidence as evidence_mod
from . import findings as findings_mod
from . import fingerprint, fixloop, languages, local, patchcheck, proposal, statuses
from .envelope import Envelope, Kind
from .router import Plan, Stage
from .verdicts import BLOCKING_VERDICTS, normalise, rank, strictest

log = logging.getLogger(__name__)

#: Bounds. The router also caps iterations; this is the last line before a run starts.
MAX_MATERIAL = 200_000
MAX_FILES = 200
MAX_ITERATIONS = 3

#: Text shown to the client when an internal call fails. The real message goes to the log.
INTERNAL_ERROR = "an internal check failed; the run is not a pass"


@dataclass
class Step:
    stage: str
    ok: bool
    verdict: str = ""
    detail: str = ""

    def as_dict(self) -> dict:
        return {"stage": self.stage, "ok": self.ok, "verdict": self.verdict, "detail": self.detail}


@dataclass
class RunResult:
    ok: bool
    verdict: str
    steps: list[Step] = field(default_factory=list)
    session_id: str = ""
    trace: list[str] = field(default_factory=list)
    reason: str = ""
    plan: dict = field(default_factory=dict)
    checks: dict = field(default_factory=dict)
    summary: str = ""
    findings: list = field(default_factory=list)
    patch: dict = field(default_factory=dict)
    questions: list = field(default_factory=list)
    proof: list = field(default_factory=list)
    model: str = ""
    model_verdict: str = ""
    rules_verdict: str = ""
    mode: str = "plan"
    not_checked: list = field(default_factory=list)
    fingerprint: dict = field(default_factory=dict)
    #: How the model's findings and the rules' findings overlapped; empty unless both read the material.
    agreement: dict = field(default_factory=dict)
    #: The result of a real patch check, when one ran; empty means none did (fix status FIX_UNVERIFIED).
    patch_check: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "schema": "vishap.run/1",          # the stable contract, see docs/ci.md
            "ok": self.ok,
            "mode": self.mode,
            "verdict": self.verdict,
            "reason": self.reason,
            "session_id": self.session_id,
            "plan": self.plan,
            "steps": [s.as_dict() for s in self.steps],
            "checks": self.checks,
            "summary": self.summary,
            "findings": self.findings,
            "patch": self.patch,
            "questions": self.questions,
            "proof": self.proof,
            "model": self.model,
            "model_verdict": self.model_verdict,
            "rules_verdict": self.rules_verdict,
            "trace": self.trace,
            "not_checked": self.not_checked,
            "agreement": self.agreement,
            "fingerprint": self.fingerprint,
            "statuses": statuses.compute(ok=self.ok, verdict=self.verdict, checks=self.checks, plan=self.plan,
                                         patch=self.patch, model_verdict=self.model_verdict,
                                         not_checked=self.not_checked, patch_check=self.patch_check or None),
        }


def _error(steps: list[Step], session_id: str, trace: list[str], reason: str,
           plan: dict | None = None) -> RunResult:
    return RunResult(False, "ERROR", steps, session_id, trace, reason, plan or {})


def _spec_for_validator(spec: object, files: dict) -> dict:
    """The validator wants a dict; a spec written for the generator is a YAML string.

    Passing a string through would raise inside the validator and turn an honest
    «cannot compare» into a crash, so a spec that is not already a dict becomes the
    one thing we do know: the file list of the deliverable.
    """
    if isinstance(spec, dict) and spec:
        return spec
    return {"files": list(files)}


def _analysis_pieces(material: str, patch: dict) -> list[tuple[str, str]]:
    """Everything that must pass the analyser: the material and the proposed code."""
    pieces: list[tuple[str, str]] = []
    if material.strip():
        pieces.append(("material", material))
    for name, text in sorted(patch.items()):
        if text.strip():
            pieces.append((f"patch:{name}", text))
    return pieces


def _model_trouble(reason: str) -> str:
    """The model's failure in words a person can act on; the raw text goes to the log, not to a page."""
    text = str(reason or "")
    if "HTTP 401" in text or "HTTP 403" in text:
        return "your model key was rejected by Anthropic"
    if "no model key" in text:
        return "no model key was sent"
    if "HTTP 429" in text:
        return "the model's rate limit was reached"
    return "the model did not answer"


def _not_checked(plan: Plan, checks: dict, has_proof: bool, model_trouble: str = "") -> list[str]:
    """Everything this run did not answer — said before the client asks."""
    missing: list[str] = []
    stages = tuple(getattr(plan, "stages", ()) or ())
    if Stage.VALIDATOR not in stages:
        missing.append("the code was not compared with a spec: no validator stage in this plan")
    if Stage.ANALYSER not in stages:
        missing.append("security was not checked: no analyser stage in this plan")
    if Stage.GENERATOR not in stages:
        missing.append("nothing was generated: no generator stage in this plan")
    if not (checks.get("validator") or {}).get("checks"):
        missing.append("the validator's stage-by-stage detail is not in this answer")
    if has_proof:
        missing.append("the proof lines are the model's promise, not the output of a run")
    if model_trouble:
        missing.append(f"the model's reading is missing: {model_trouble}")
    return missing


def run_plan(plan: Plan, material: str = "", files: dict | None = None,
             spec: object = None, filename: str = "input.txt",
             question: str = "", api_key: str = "", model: str = "",
             on_step=None, check_patch: bool = False, fix_loop: bool = False) -> RunResult:
    """Execute the plan and return one honest verdict.

    ``on_step`` is called with ``(stage, payload)`` after every stage that produced a
    verdict, so a streaming client can show progress instead of waiting for the whole
    run in silence.

    ``check_patch`` applies the model's patch to a copy of the files the client sent and re-checks it
    (`patchcheck`), so the fix status can be more than FIX_UNVERIFIED. Off by default: it runs the
    deliverable's tests, which only happens where the isolation is confirmed.

    ``fix_loop`` goes further (`fixloop`): a patch that is rejected or only partly verified goes back to the
    model with the reason, up to three attempts in all. The status always comes from the check, never from
    the model, and the risk verdict is untouched.
    """

    def emit(stage: str, payload: dict) -> None:
        if on_step is None:
            return
        try:
            on_step(stage, payload)
        except Exception:  # a broken listener must not break the run
            log.warning("on_step listener failed", exc_info=True)

    envelope = Envelope.build("hub", "analyser", Kind.QUESTION, {"filename": filename})
    steps: list[Step] = []
    trace = list(envelope.trace)
    plan_dict = plan.as_dict() if hasattr(plan, "as_dict") else {}
    files = dict(files or {})
    question = str(question or "")

    # ---- gates: nothing to do is not a pass -------------------------------
    if not getattr(plan, "stages", None):
        return _error(steps, envelope.session_id, trace, "the plan has no stages; nothing would be checked", plan_dict)
    if int(getattr(plan, "iterations", 0) or 0) <= 0:
        return _error(steps, envelope.session_id, trace, "iterations must be at least 1", plan_dict)
    if int(plan.iterations) > MAX_ITERATIONS:
        return _error(steps, envelope.session_id, trace, f"iterations above {MAX_ITERATIONS} are refused", plan_dict)
    if len(material) > MAX_MATERIAL:
        return _error(steps, envelope.session_id, trace,
                      f"material above {MAX_MATERIAL} characters is refused", plan_dict)
    if len(files) > MAX_FILES:
        return _error(steps, envelope.session_id, trace, f"more than {MAX_FILES} files is refused", plan_dict)

    strictest_verdict: str | None = None
    model_verdict = ""
    rules_verdict = ""
    checks: dict = {"generator": None, "validator": None, "analyser": None}
    answer: dict = {}
    model_trouble = ""
    previous: dict[str, str] = {}
    supplied_files = dict(files)
    passes_run = 0
    stop_reason = ""

    def merge(verdict: str) -> None:
        nonlocal strictest_verdict
        strictest_verdict = verdict if strictest_verdict is None else strictest(strictest_verdict, verdict)

    for pass_no in range(1, int(plan.iterations) + 1):
        passes_run = pass_no
        current: dict[str, str] = {}

        for stage in plan.stages:
            if stage is Stage.GENERATOR:
                if pass_no > 1:
                    trace.append(f"pass {pass_no} generator -> reused the pass 1 proposal")
                    if "generator" in current:
                        merge(current["generator"])
                    continue
                if not (material.strip() or str(spec or "").strip() or question.strip()):
                    steps.append(Step("generator", False, detail="no spec, no material, no question"))
                    return _error(steps, envelope.session_id, trace,
                                  "generation needs a spec, material or a question; nothing was sent", plan_dict)

                result = proposal.propose(material=material, spec=str(spec or "") if not isinstance(spec, dict) else "",
                                          question=question, api_key=api_key, model=model)
                if not result.get("ok"):
                    reason = result.get("error") or "the model did not answer"
                    log.warning("generator failed: %s", reason)
                    steps.append(Step("generator", False, detail=reason))
                    if getattr(plan, "model_optional", False) and material.strip():
                        # a review without its model is still the rules' review: say so, do not hide it
                        model_trouble = _model_trouble(reason)
                        trace.append(f"pass {pass_no} generator -> no answer ({model_trouble}); the rules go on")
                        continue
                    return _error(steps, envelope.session_id, trace,
                                  f"no proposal: {reason}", plan_dict)

                answer = result
                model_verdict = result["verdict"]
                patch = result.get("patch") or {}
                if patch and not files:
                    files = dict(patch)
                checks["generator"] = {
                    "model": result.get("model", ""),
                    "verdict": model_verdict,
                    "files": len(patch),
                    "summary_findings": len(result.get("findings") or []),
                }
                current["generator"] = model_verdict
                steps.append(Step("generator", True, model_verdict,
                                  detail=f"{len(patch)} file(s) proposed · model recommendation"))
                trace.append(f"pass {pass_no} generator -> {model_verdict} ({len(patch)} file(s))")
                emit("generator", {"stage": "generator", "verdict": model_verdict, "ok": True,
                                   "files": len(patch), "pass": pass_no})
                continue

            if stage is Stage.VALIDATOR:
                if not files:
                    steps.append(Step("validator", False, detail="no files supplied"))
                    return _error(steps, envelope.session_id, trace,
                                  "validation needs files; nothing was sent", plan_dict)
                result = local.validate_code(files, _spec_for_validator(spec, files))
                if not result.get("ok"):
                    log.warning("validator failed: %s", result.get("error"))
                    steps.append(Step("validator", False, detail=INTERNAL_ERROR))
                    return _error(steps, envelope.session_id, trace,
                                  "validator failed; the deliverable is unverified", plan_dict)
                report = result.get("report") or {}
                try:
                    verdict = normalise(report.get("verdict"))
                except ValueError:
                    log.warning("validator returned an unusable verdict: %r", report.get("verdict"))
                    steps.append(Step("validator", False, verdict="",
                                      detail="the report carried no usable verdict"))
                    return _error(steps, envelope.session_id, trace,
                                  "validator returned no verdict; nothing was verified", plan_dict)
                checks["validator"] = {"verdict": verdict, "checks": report.get("checks", [])}
                if result.get("isolation"):
                    checks["validator"]["isolation"] = result["isolation"]
                current["validator"] = verdict
                steps.append(Step("validator", verdict not in BLOCKING_VERDICTS, verdict,
                                  detail=f"{report.get('finding_count', 0)} findings"))
                trace.append(f"pass {pass_no} validator -> {verdict}")
                emit("validator", {"stage": "validator", "verdict": verdict,
                                   "ok": verdict not in BLOCKING_VERDICTS,
                                   "findings": report.get("finding_count", 0), "pass": pass_no})
                merge(verdict)
                continue

            if stage is Stage.ANALYSER:
                pieces = _analysis_pieces(material, files if checks["generator"] else {})
                if not pieces:
                    steps.append(Step("analyser", False, detail="no material supplied"))
                    return _error(steps, envelope.session_id, trace,
                                  "analysis needs material; nothing was sent", plan_dict)

                worst = "SAFE"
                found: list[dict] = []
                reasons: list[str] = []
                meaning = ""
                seen_langs: list[str] = []
                for source, text in pieces:
                    result = local.analyse_static(text, model_verdict=model_verdict)
                    if not result.get("ok"):
                        log.warning("analyser failed on %s: %s", source, result.get("error"))
                        steps.append(Step("analyser", False, detail=INTERNAL_ERROR))
                        return _error(steps, envelope.session_id, trace,
                                      "analyser failed; no security verdict available", plan_dict)
                    try:
                        piece_verdict = normalise(result.get("verdict"))
                    except ValueError:
                        log.warning("analyser returned an unusable verdict: %r", result.get("verdict"))
                        steps.append(Step("analyser", False, verdict="",
                                          detail="the result carried no usable verdict"))
                        return _error(steps, envelope.session_id, trace,
                                      "analyser returned no verdict; no security answer available", plan_dict)
                    worst = strictest(worst, piece_verdict)
                    meaning = meaning or str(result.get("meaning") or "")
                    lang = str((result.get("coverage") or {}).get("language") or "unknown")
                    if lang not in seen_langs:
                        seen_langs.append(lang)
                    reasons.append(f"{source}: {result.get('reason') or piece_verdict}")
                    for item in result.get("findings") or []:
                        found.append({**item, "source": source})

                checks["analyser"] = {"verdict": worst, "findings": found, "mode": "rules_only",
                                      "reasons": reasons, "meaning": meaning,
                                      "languages": [languages.evidence_for(lang) for lang in seen_langs]}
                current["analyser"] = worst
                why = "" if worst == "SAFE" else (reasons[0] if len(reasons) == 1 else "see the reasons")
                steps.append(Step("analyser", True, worst,
                                  detail=f"{len(found)} findings · {len(pieces)} piece(s) · rules only" + (f" - {why}" if why else "")))
                trace.append(f"pass {pass_no} analyser -> {worst} ({len(pieces)} piece(s))")
                emit("analyser", {"stage": "analyser", "verdict": worst, "ok": True,
                                  "findings": len(found), "pieces": len(pieces), "pass": pass_no})
                merge(worst)
                continue

        if int(plan.iterations) > 1 and previous and current == previous:
            trace.append(f"stop after pass {pass_no}: no stage changed its verdict")
            stop_reason = f"no stage changed its verdict after pass {pass_no}"
            break
        previous = current

    # ---- nothing produced a verdict: this is a failure, not a pass --------
    rules_parts = [check["verdict"] for check in (checks["validator"], checks["analyser"])
                   if check and check.get("verdict")]
    rules_verdict = strictest(*rules_parts) if rules_parts else ""

    # The model is a recommendation, so it is merged last and only upwards: on a tie
    # the rules keep their own word (PASS from the validator, not SAFE from a model),
    # and a model that says «looks safe» cannot lift a FAIL.
    if rules_verdict:
        final = rules_verdict if not model_verdict or rank(model_verdict) <= rank(rules_verdict) else model_verdict
    else:
        final = model_verdict or strictest_verdict or ""

    if not final:
        return _error(steps, envelope.session_id, trace,
                      "no stage produced a verdict; an empty run is not a pass", plan_dict)

    # `ok` answers «did the run survive its own gates», not «is the material clean»:
    # REQUIRES_REVIEW is a successful run that found something.
    ok = final not in BLOCKING_VERDICTS
    reason = plan.note or ""
    if model_trouble:
        reason = (reason + " · " if reason else "") + f"the model did not answer: {model_trouble}"
    if final == "EMERGENCY":
        reason = (reason + " · " if reason else "") + "an emergency-level security signal is present"
    if model_verdict and rules_verdict and rank(model_verdict) > rank(rules_verdict):
        reason = (reason + " · " if reason else "") + "the model saw danger the rules did not"

    merged, overlap = findings_mod.merge(answer.get("findings") or [], (checks["analyser"] or {}).get("findings") or [])
    if not (checks["generator"] and checks["analyser"]):
        overlap = {}                  # one reader only: there is nothing to agree with

    patch_check: dict = {}
    final_patch = answer.get("patch") or {}
    fix_rows: list[dict] = []
    fix_stop = ""
    if final_patch and supplied_files and fix_loop:
        check_spec = _spec_for_validator(spec, supplied_files)
        spec_text = str(spec or "") if not isinstance(spec, dict) else ""
        loop = fixloop.run(
            supplied_files, check_spec, final_patch,
            lambda more: proposal.propose(material=material, spec=spec_text, question=question + more,
                                          api_key=api_key, model=model))
        patch_check, fix_rows, final_patch, fix_stop = (loop["patch_check"], loop["attempts"], loop["patch"],
                                                        loop["stop_reason"])
    elif check_patch and final_patch and supplied_files:
        patch_check = patchcheck.check(supplied_files, files=final_patch,
                                       spec=_spec_for_validator(spec, supplied_files))

    result = RunResult(
        ok=ok,
        verdict=final,
        steps=steps,
        session_id=envelope.session_id,
        trace=trace,
        reason=reason,
        plan=plan_dict,
        checks=checks,
        summary=answer.get("summary", ""),
        findings=merged,
        agreement=overlap,
        patch=final_patch,
        questions=answer.get("questions") or [],
        proof=answer.get("proof") or [],
        model=answer.get("model", ""),
        model_verdict=model_verdict,
        rules_verdict=rules_verdict,
        not_checked=_not_checked(plan, checks, bool(answer.get("proof")), model_trouble),
        patch_check=patch_check,
    )
    result.fingerprint = fingerprint.of(
        material=material,
        spec=spec,
        files=files,
        plan=plan_dict,
        verdict=final,
        steps=[s.as_dict() for s in steps],
        evidence=evidence_mod.build(
            supplied_files=supplied_files, checked_files=files, patch=result.patch, checks=checks, answer=answer,
            model_verdict=model_verdict, rules=fingerprint.rules_version(), attempts=passes_run,
            stop_reason=(stop_reason or f"the plan ran to its end ({passes_run} pass(es))")
            + (f"; fix loop: {fix_stop}" if fix_stop else ""),
            fix_attempts=fix_rows,
            not_checked=result.not_checked, patch_check=patch_check),
    )
    return result
