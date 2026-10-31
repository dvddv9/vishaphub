"""A run as Markdown: something to forward, attach to a ticket, or keep next to the code.

Only what the stored record holds: the verdict and the three results, the findings, what was not checked, the
evidence the fingerprint carries and whether the record is intact. Never the material or the files: the hub
does not keep them, and an export must not become the place that does.
"""
from __future__ import annotations

from . import fingerprint, languages


def _cell(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")[:300]


def markdown(record: dict) -> str:
    result = record.get("result") if isinstance(record.get("result"), dict) else record
    st = result.get("statuses") or {}
    fp = result.get("fingerprint") or {}
    ev = (fp.get("body") or {}).get("evidence") or {}
    run_id = record.get("id") or fp.get("id") or ""
    out = [f"# VishapHub run {run_id}", ""]
    out.append(f"- **Risk verdict:** {result.get('verdict') or record.get('verdict') or '-'}")
    fix = st.get("fix") or {}
    ver = st.get("verification") or {}
    risk = st.get("risk") or {}
    basis = risk.get("basis") or {}
    stood = ", ".join(f"{k}: {basis[k]}" for k in ("rules", "tests", "model") if basis.get(k)) or "nothing ran"
    out.append(f"  - stands on: {stood}" + (" (the model alone: a guess)" if risk.get("rests_on_model_alone") else ""))
    out.append(f"- **Fix status:** {fix.get('status') or '-'}" + (f" - {fix.get('reason')}" if fix.get("reason") else ""))
    out.append(f"- **Verification:** {ver.get('status') or '-'}; ran: {', '.join(ver.get('ran') or []) or 'nothing'}"
               + (f"; not run: {', '.join(ver.get('not_run') or [])}" if ver.get("not_run") else ""))
    if record.get("at"):
        out.append(f"- **At:** {record['at']}")
    plan = (result.get("plan") or {}).get("stages") or []
    if plan:
        out.append(f"- **Plan:** {' -> '.join(plan)}")
    if result.get("reason"):
        out.append(f"- **Reason:** {result['reason']}")
    out.append("")
    if result.get("summary"):
        out += ["## Model summary", "", str(result["summary"]), ""]
    findings = result.get("findings") or []
    out += ["## Findings", ""]
    if findings:
        out += ["| severity | rule | line | source | message |", "|---|---|---|---|---|"]
        for f in findings:
            source = "rules + model" if len(f.get("seen_by") or []) > 1 else (f.get("source") or "")
            out.append(f"| {_cell(f.get('severity'))} | {_cell(f.get('rule'))} | {_cell(f.get('line'))} | "
                       f"{_cell(source)} | {_cell(f.get('message'))} |")
    else:
        out.append("Nothing matched.")
    out.append("")
    patch = result.get("patch") or {}
    if patch:
        out += ["## Proposed patch", "", "Files: " + ", ".join(f"`{name}`" for name in sorted(patch))
                + ". The contents are on the report page, not in this export.", ""]
    out += ["## Not checked", ""]
    missed = result.get("not_checked") or []
    out += [f"- {m}" for m in missed] if missed else ["Everything this plan covers was checked."]
    out.append("")
    if ev:
        ok, why = fingerprint.verify(fp)
        rules = ev.get("rules_found") or {}
        model = ev.get("model") or {}
        ran = [c for c in ev.get("checks_run") or [] if not c.get("skipped")]
        prof = (ev.get("versions") or {}).get("sandbox_profile") or {}
        clean = (ev.get("cleanup") or {}).get("confirmed")
        out += ["## Evidence", "",
                f"- Record: {'intact' if ok else 'NOT intact (' + why + ')'}; digest `{(fp.get('digest') or '')[:32]}`",
                (f"- Snapshot: `{((ev.get('snapshot') or {}).get('sha256') or '')[:16]}`; attempts {ev.get('attempts')}: "
                 f"{ev.get('stop_reason') or ''}"),
                f"- Rules found: analyser {rules.get('analyser', 0)}, validator {rules.get('validator', 0)}",
                "- Model: " + (f"{model.get('name') or '?'} said {model.get('verdict') or '-'}, "
                                f"{model.get('findings', 0)} finding(s)" if model.get("consulted") else "not consulted"),
                "- Checks that ran: " + (", ".join(f"{c.get('stage')}/{c.get('name')} "
                                                   f"({'ok' if c.get('ok') else 'FAILED'})" for c in ran) or "none"),
                *[f"- Language evidence: {languages.sentence(x)}" for x in ev.get("languages") or []],
                f"- Sandbox: {prof.get('name') or '-'}; cleanup "
                + ("not applicable" if clean is None else "confirmed" if clean else "NOT confirmed"), ""]
    rules_v = fp.get("rules") or {}
    if rules_v:
        out += ["Rules that judged: " + ", ".join(f"{k} {v}" for k, v in rules_v.items()), ""]
    return "\n".join(out)