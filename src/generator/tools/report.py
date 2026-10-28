"""A run as a Markdown report: the analog of Vishap's `static_scan.render_markdown` / `api/reports`.

What a person reads after a run, or attaches to a pull request: the verdict, the requirements with their
evidence, the gaps, the gate, and what the run used. It is built from the result object only, so the same
run gives the same text (no times, no paths).
"""

from __future__ import annotations


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def render_markdown(res, spec_name: str = "spec.yaml") -> str:
    out = [f"# Vishap Generator report: {spec_name}", ""]
    if res.error:
        out += [f"**Error:** {res.error}", ""]
    v = res.verify
    if v:
        out += [f"**Verdict:** {v.code_verdict.upper()}  ", f"**Requirements:** {v.passed}/{len(v.requirements)} passed  "]
        cov = (f"{v.coverage_percent:.0f}%" if v.coverage_percent is not None
               else f"{v.coverage_status} ({v.coverage_note})")
        out += [f"**Coverage:** {cov}  ", f"**Spec:** {'stale' if v.spec_stale else 'fresh'}, {v.spec_age_days} days old", ""]
        out += ["## Requirements", "", "| ID | Priority | Status | Requirement |", "|---|---|---|---|"]
        text = {r.id: r.text for r in res.requirements}
        prio = {r.id: r.priority for r in res.requirements}
        for r in v.requirements:
            out.append(f"| {r.id} | {prio.get(r.id, '')} | {r.status} | {_cell(text.get(r.id, ''))} |")
        out.append("")
        if v.problems:
            out += ["## Problems", ""] + [f"- {_cell(p)}" for p in v.problems] + [""]
        if v.analyzer:
            out += ["## Analyzer", "", f"{v.analyzer.status}: {_cell(v.analyzer.note)}", ""]
    if res.threats:
        out += ["## STRIDE", "", "What the spec says about each threat category, and whether Verify proved it. "
                "This reads the spec, not the code.", "",
                "| | Category | Status | Proof | Requirements | Why |", "|---|---|---|---|---|---|"]
        out += [f"| {t['letter']} | {t['name']} | {t['status'].replace('_', ' ')} | {t.get('proof', '-')} | "
                f"{', '.join(t['requirements']) or '-'} | {_cell(t['reason'])} |" for t in res.threats]
        out.append("")
    if res.candidates:
        out += ["## Candidates", "", "| # | Verdict | Passed | Build | |", "|---|---|---|---|---|"]
        out += [f"| {c['index'] + 1} | {c.get('verdict', 'failed')} | {c.get('passed', 0)}/{c.get('requirements', 0)} | "
                f"{'ok' if c.get('build_ok') else 'errors'} | {'chosen' if c['chosen'] else _cell(c.get('error', ''))} |"
                for c in res.candidates]
        out.append("")
    if res.cove and res.cove.get("status") == "ok":
        cv = res.cove
        out += ["## COVE", "", f"{len(cv['probes'])} values; the spec's reading compared with what the code answers: "
                f"{len(cv['mismatches'])} mismatch(es), {len(cv['unclear'])} left undecided by the spec.", "",
                "| Probe | Input | Value | Spec reading | Code |", "|---|---|---|---|---|"]
        out += [f"| {p['id']} | {_cell(p['input'])} ({_cell(p['label'])}) | `{_cell(p['value'])}` | "
                f"{p['spec_reading']} | {p['code']}{'' if p['match'] else ' **mismatch**'} |" for p in cv["probes"]]
        out.append("")
    if res.design and res.design.gaps:
        out += ["## Gaps", "", "| ID | Severity | Gap |", "|---|---|---|"]
        out += [f"| {g.id} | {g.severity} | {_cell(g.text)} |" for g in res.design.gaps]
        out.append("")
    if res.deliver:
        g = res.deliver.gate
        out += ["## Gate", ""]
        out.append("BLOCKED" if g.blocked else "passed")
        out += [f"- {_cell(r)}" for r in g.reasons]
        out += [f"- accepted by the baseline: {_cell(r)}" for r in g.accepted]
        out.append("")
    if res.stages:
        if res.stopped:
            out += [f"Repair stopped early: {_cell(res.stopped)}", ""]
        out += ["## Stages", "", "| Stage | Runs | Model calls | Tokens in | Tokens out |", "|---|---|---|---|---|"]
        out += [f"| {s['title']} | {s['runs']} | {s['llm_calls']} | {s['tokens_in']} | {s['tokens_out']} |"
                for s in res.stages]
        out.append("")
    if res.provenance:
        p = res.provenance
        model = p.get("model")
        out += ["## Provenance", "", f"- generator {p['generator']}, spec sha256 {p['spec']['sha256'][:12]}",
                f"- model: {model['name'] + ' at ' + model['host'] if model else 'not resolved'}"]
        if p.get("redaction"):
            out.append("- redacted before the model: " + ", ".join(f"{n} {k}" for k, n in sorted(p["redaction"].items())))
        out.append("")
    return "\n".join(out).rstrip() + "\n"
