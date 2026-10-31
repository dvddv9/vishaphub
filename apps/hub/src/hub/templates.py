"""Pages the hub serves: one layout, one stylesheet, escaped data.

The report page is the product: a verdict that can be opened, read and forwarded by
someone who was not in the room. The list page answers "what ran lately". Both are
built here, away from the request handler, so a page cannot grow a second set of
headers or a second way to escape a string.
"""
from __future__ import annotations

import html
import re

#: Everything on these pages is data, never markup: escape once, here.
e = html.escape

ARROW = "\u2192"
ARROW_BACK = "\u2190"
DOT = "\u00b7"


def layout(title: str, body: str, description: str = "") -> str:
    desc = f'<meta name="description" content="{e(description)}">' if description else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="theme-color" content="#05070d">
<meta name="color-scheme" content="dark">
{desc}
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/styles.css">
</head><body>
<a class="skip" href="#main">Skip to content</a>
<header class="nav"><div class="nav-in">
<a class="brand" href="/" aria-label="VishapHub"><span class="mark" aria-hidden="true">V</span>Vishap<b>Hub</b></a>
<nav class="nav-links" aria-label="Pages"><a href="/#how">How it works</a><a href="/#work">Try it</a><a href="/runs">Recent runs</a></nav>
<span class="spacer"></span>
<a class="btn ghost sm" href="/#work">New run</a>
</div></header>
<div class="shell"><div class="doc">
<main id="main">{body}</main>
<footer><span class="foot-brand"><span class="mark" aria-hidden="true">V</span>VishapHub</span>
<a href="/">home</a><a href="/runs">recent runs</a>
<span class="right">hub v{_version()}</span></footer>
</div></div>
</body></html>"""


def _version() -> str:
    from .version import __version__
    return e(__version__)


def _block(title: str, body: str) -> str:
    return f'<section class="block"><h2>{e(title)}</h2>{body}</section>'


def _verdict_class(verdict: str) -> str:
    """ok / warn / bad. Anything that is not a clear pass is not painted green."""
    v = (verdict or "").strip().upper()
    if v in ("SAFE", "PASS"):
        return "ok"
    if v in ("EMERGENCY", "FAIL", "ERROR"):
        return "bad"
    return "warn" if v and v != "-" else ""


def _statuses_block(result: dict) -> str:
    """The three results side by side: they answer different questions and are never merged."""
    st = result.get("statuses")
    if not isinstance(st, dict):
        return ""                         # a run stored before the statuses existed
    r, f, v = st.get("risk") or {}, st.get("fix") or {}, st.get("verification") or {}
    basis = r.get("basis") or {}
    stood = ", ".join(f"{k}: {basis[k]}" for k in ("rules", "tests", "model") if basis.get(k)) or "nothing ran"
    guess = " (resting on the model alone: a guess)" if r.get("rests_on_model_alone") else ""
    ran = ", ".join(v.get("ran") or []) or "nothing"
    iso = v.get("isolation") or {}
    where = f" \u00b7 isolation: {iso.get('kind')}, cleanup {'confirmed' if iso.get('cleanup_confirmed') else 'not confirmed'}" if iso else ""
    rows = (
        f"<tr><td>risk verdict</td><td><b>{e(str(r.get('verdict') or '-'))}</b></td><td>{e(stood)}{e(guess)}</td></tr>"
        f"<tr><td>fix status</td><td><b>{e(str(f.get('status') or '-'))}</b></td><td>{e(str(f.get('reason') or ''))}</td></tr>"
        f"<tr><td>verification</td><td><b>{e(str(v.get('status') or '-'))}</b></td><td>ran: {e(ran)}{e(where)}</td></tr>"
    )
    note = ('<p class="meta">Three results, three questions. A fix status never changes the risk verdict; '
            "the model can only raise a verdict, never lower it.</p>")
    return _block("Three results", f'<div class="table-wrap"><table class="statuses"><tr><th>result</th><th>status</th><th>what stands behind it</th></tr>{rows}</table></div>{note}')

def _evidence_block(fp: dict) -> str:
    """What the run rests on, in four separate columns of the truth, plus whether the record is intact."""
    from . import fingerprint, languages

    ev = ((fp or {}).get("body") or {}).get("evidence")
    if not isinstance(ev, dict):
        return ""                         # a run stored before the evidence existed
    ok, why = fingerprint.verify(fp)
    rules = ev.get("rules_found") or {}
    model = ev.get("model") or {}
    ran = [c for c in ev.get("checks_run") or [] if not c.get("skipped")]
    skipped = [c for c in ev.get("checks_run") or [] if c.get("skipped")]
    prof = (ev.get("versions") or {}).get("sandbox_profile") or {}
    clean = (ev.get("cleanup") or {}).get("confirmed")
    clean_text = "not applicable (no container)" if clean is None else ("confirmed" if clean else "NOT confirmed")
    ran_rows = "".join(f"<li>{e(str(c.get('stage')))} \u00b7 {e(str(c.get('name')))}: "
                       f"{'ok' if c.get('ok') else 'FAILED'}, {int(c.get('findings') or 0)} finding(s)</li>"
                       for c in ran) or "<li>no check ran</li>"
    skipped_rows = "".join(f"<li>{e(str(c.get('name')))} (skipped)</li>" for c in skipped)
    unverified = "".join(f"<li>{e(str(x))}</li>" for x in ev.get("not_checked") or []) + skipped_rows or "<li>-</li>"
    model_line = (f"consulted: {e(str(model.get('name') or '?'))}, verdict {e(str(model.get('verdict') or '-'))}, "
                  f"{int(model.get('findings') or 0)} finding(s)") if model.get("consulted") else "not consulted"
    patch = ev.get("patch") or {}
    patch_line = (f"diff <code>{e(str(patch.get('diff_sha256') or '')[:16])}</code> over "
                  f"{len(patch.get('files') or {})} file(s)") if patch.get("proposed") else "no patch"
    profile_hash = (f" \u00b7 profile <code>{e(str(prof.get('sha256') or '')[:16])}</code>" if prof.get('sha256') else "")
    lang_rows = "".join(f"<li>{e(languages.sentence(x))}</li>" for x in ev.get("languages") or []) or "<li>-</li>"
    integrity = ("<span class=\"vchip pass\">record intact</span>" if ok
                 else f"<span class=\"vchip bad\">record NOT intact: {e(why)}</span>")
    body = (
        f"<p class=\"meta\">{integrity} \u00b7 snapshot <code>{e(str((ev.get('snapshot') or {}).get('sha256') or '')[:16])}</code>"
        f" \u00b7 {patch_line} \u00b7 attempts {int(ev.get('attempts') or 0)}: {e(str(ev.get('stop_reason') or ''))}</p>"
        "<div class=\"table-wrap\"><table class=\"statuses\"><tr><th>who</th><th>what it says</th></tr>"
        f"<tr><td>rules found</td><td>analyser {int(rules.get('analyser') or 0)} \u00b7 validator {int(rules.get('validator') or 0)} finding(s)</td></tr>"
        f"<tr><td>model said</td><td>{model_line}</td></tr>"
        f"<tr><td>validator ran on</td><td>{e(str((ev.get('validator_ran_on') or {}).get('what') or 'nothing'))} ({len((ev.get('validator_ran_on') or {}).get('files') or {})} file(s))</td></tr>"
        f"<tr><td>tests that really ran</td><td><ul>{ran_rows}</ul></td></tr>"
        f"<tr><td>left unverified</td><td><ul>{unverified}</ul></td></tr>"
        f"<tr><td>language evidence</td><td><ul>{lang_rows}</ul></td></tr>"
        "</table></div>"
        f"<p class=\"meta\">sandbox: {e(str(prof.get('name') or '-'))}{profile_hash}"
        f" \u00b7 cleanup {clean_text}</p>"
    )
    return _block("Evidence", body)

_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _readers(finding: dict) -> int:
    return len(set(finding.get("seen_by") or []))


def _by_agreement(findings: list) -> list:
    """Findings more than one reader saw come first, then the rest; by severity within each, and in the order
    found within a tie. Nothing is dropped or hidden: only the order of the page changes."""
    return sorted(findings, key=lambda f: (-(_readers(f) > 1), -_SEVERITY_RANK.get(str(f.get("severity") or "").lower(), 0)))


def report_page(record: dict, retention: str = "") -> str:
    """One run: the verdict, every step, every finding with its source, what was not checked."""
    result = record.get("result") or {}
    fp = result.get("fingerprint") or {}
    not_checked = result.get("not_checked") or []
    findings = result.get("findings") or []
    steps = result.get("steps") or []

    verdict_raw = str(result.get("verdict") or record.get("verdict") or "-")
    verdict = e(verdict_raw)
    state = _verdict_class(verdict_raw)
    if not result.get("ok") and state != "bad":
        state = "bad"
    plan = f" {ARROW} ".join((result.get("plan") or {}).get("stages") or [])

    rows = "".join(
        f"<tr><td>{e(str(s.get('stage')))}</td><td>{e(str(s.get('verdict') or '-'))}</td>"
        f"<td><span class=\"st {'ok' if s.get('ok') else 'fail'}\">{'ok' if s.get('ok') else 'fail'}</span></td>"
        f"<td>{e(str(s.get('detail') or ''))}</td></tr>"
        for s in steps
    ) or "<tr><td colspan=4>-</td></tr>"

    def _finding(f: dict) -> str:
        severity = str(f.get("severity") or "")
        sev_class = re.sub(r"[^a-z]", "", severity.lower())
        badge = f'<span class="sev {sev_class}">{e(severity)}</span>' if severity else ""
        line = f" @ {e(str(f.get('line')))}" if f.get("line") else ""
        seen = f.get("seen_by") or []
        by = " + ".join(str(s) for s in seen) if len(seen) > 1 else str(f.get("source") or "")
        source = f" <i>({e(by)})</i>" if by else ""
        fix = f"<br><small>fix: {e(str(f.get('fix')))}</small>" if f.get("fix") else ""
        covered = (f"<br><small>possibly covered by {e(str(f.get('possibly_covered_by')))}</small>"
                   if f.get("possibly_covered_by") else "")
        note = f.get("accepted") if isinstance(f.get("accepted"), dict) else None
        taken = (f"<br><small class=\"accepted\">accepted: {e(str(note.get('reason') or ''))} "
                 f"({e(str(note.get('by') or ''))}, {e(str(note.get('at') or ''))}). "
                 f"The verdict above is the checks', not this note.</small>") if note else ""
        return (f"<li>{badge}{e(str(f.get('rule') or ''))}{line}: {e(str(f.get('message') or ''))}"
                f"{source}{fix}{covered}{taken}</li>")

    own = _by_agreement([f for f in findings if not f.get("in_patch")])
    in_patch = [f for f in findings if f.get("in_patch")]
    many, one = [f for f in own if _readers(f) > 1], [f for f in own if _readers(f) <= 1]
    if many and one:          # a heading only where there are two kinds to tell apart
        found = ("<li class=\"meta\">seen by more than one reader</li>" + "".join(_finding(f) for f in many)
                 + "<li class=\"meta\">seen by one reader</li>" + "".join(_finding(f) for f in one))
    else:
        found = "".join(_finding(f) for f in own)
    found = found or "<li>nothing matched</li>"
    overlap = result.get("agreement") or {}
    if overlap:
        patch_note = f" \u00b7 in the model's patch: {overlap['in_patch']}" if overlap.get("in_patch") else ""
        found = (f"<li class=\"meta\">seen by both readers: {overlap.get('both', 0)} \u00b7 model only: "
                 f"{overlap.get('model_only', 0)} \u00b7 rules only: {overlap.get('rules_only', 0)}{patch_note}</li>") + found
    patch_block = (_block("In the model's patch", "<p class=\"meta\">The rules read the patch the model proposed. "
                          "Line numbers refer to the patch, not to your material.</p><ul>"
                          + "".join(_finding(f) for f in in_patch) + "</ul>") if in_patch else "")
    missed = "".join(f"<li>{e(str(item))}</li>" for item in not_checked) or "<li>-</li>"
    rule_chips = "".join(
        f"<span>{e(str(name))} <code>{e(str(version))}</code></span>"
        for name, version in (fp.get("rules") or {}).items()
    ) or "<span>-</span>"

    summary = str(result.get("summary") or "")
    reason = str(result.get("reason") or "")
    body = f"""
<p class="crumb"><a href="/runs">{ARROW_BACK} recent runs</a><span class="exports"> {DOT} export:
<a href="/api/runs/{e(str(record.get('id') or ''))}.json">JSON</a> {DOT}
<a href="/api/runs/{e(str(record.get('id') or ''))}.sarif">SARIF</a> {DOT}
<a href="/api/runs/{e(str(record.get('id') or ''))}.md">Markdown</a> {DOT}
<a href="/api/verify/{e(str(record.get('id') or ''))}">check integrity</a> {DOT}
<a href="/r/{e(str(record.get('id') or ''))}/delete">delete this run</a></span></p>
<form class="cmp" action="/compare" method="get"><input type="hidden" name="a" value="{e(str(record.get('id') or ''))}">
<label>compare with another run <input name="b" placeholder="run id" pattern="[0-9a-f]{{16}}" required></label>
<button type="submit">compare</button></form>
<section class="rep-hero">
<div class="rep-verdict {state}"><span class="label">verdict</span><b>{verdict}</b></div>
<div class="rep-head">
<h1>Run <code>{e(str(record.get('id') or ''))}</code></h1>
<div class="meta-row"><span>at {e(str(record.get('at') or ''))}</span><span>plan {e(plan)}</span><span>fingerprint <code>{e(str(fp.get('digest') or ''))[:32]}</code></span></div>
{f'<p class="rep-sum"><b>model summary</b>{" (the hub did not run the patch)" if result.get("patch") else ""}: {e(summary)}</p>' if summary else ''}
{f'<p class="rep-reason">{e(reason)}</p>' if reason else ''}
{f'<p class="meta">{e(retention)}</p>' if retention else ''}
</div>
</section>
{_statuses_block(result)}
{_evidence_block(fp)}
{_block("Steps", f'<div class="table-wrap"><table><tr><th>stage</th><th>verdict</th><th>state</th><th>detail</th></tr>{rows}</table></div>')}
{_block("Findings", f"<ul>{found}</ul>")}
{patch_block}
{_block("Not checked", f"<ul>{missed}</ul>")}
{_block("Rules that judged", f'<div class="meta-row">{rule_chips}</div>')}
"""
    return layout(f"Run {record.get('id', '')} {DOT} VishapHub", body,
                  description=f"A reproducible VishapHub run: verdict {result.get('verdict', '')}.")


def _status_chips(r: dict) -> str:
    """A run that did not check everything says so in the list: an empty or partial run must not look green."""
    out = ""
    ver = str(r.get("verification") or "")
    if ver and ver != "COMPLETE":
        out += ('<span class="vchip warn" title="not everything the plan covers was checked">'
                f'{e(ver.replace("_", " ").lower())}</span>')
    fix = str(r.get("fix") or "")
    if fix and fix != "NO_PATCH":
        out += f'<span class="vchip">{e(fix.lower().replace("_", " "))}</span>'
    return out


def runs_page(runs: list[dict]) -> str:
    head = ('<h1 class="page-title">Recent runs</h1>'
            '<p class="page-lead">The runs this hub remembers, newest first. Open one to read it, or send the link.</p>')
    if not runs:
        body = head + '<div class="empty">Nothing has been run yet. <a href="/#work">Run something</a>.</div>'
        return layout(f"Recent runs {DOT} VishapHub", body, description="Runs kept by this VishapHub.")

    items = "".join(
        f'<li class="run-item"><div class="line">'
        f'<span class="vchip {_verdict_class(str(r.get("verdict") or ""))}">{e(str(r.get("verdict") or "-"))}</span>'
        f'<a href="/r/{e(str(r.get("id") or ""))}">{e(str(r.get("id") or ""))}</a>'
        f'<span>{e(str(r.get("at") or ""))}</span>'
        f'<span>{e(f" {ARROW} ".join((r.get("plan") or {}).get("stages") or []))}</span>'
        + _status_chips(r) + "</div>"
        + (f'<div class="sum">{e(str(r.get("summary") or ""))}</div>' if r.get("summary") else "")
        + "</li>"
        for r in runs
    )
    body = f'{head}<ul class="runs-list">{items}</ul>'
    return layout(f"Recent runs {DOT} VishapHub", body,
                  description="The runs this VishapHub remembers, newest first.")


def _change(label: str, pair: dict) -> str:
    if not pair.get("changed"):
        return f"<tr><td>{e(label)}</td><td>{e(str(pair.get('a') or '-'))}</td><td>unchanged</td></tr>"
    return (f"<tr><td>{e(label)}</td><td>{e(str(pair.get('a') or '-'))}</td>"
            f"<td><b>{e(str(pair.get('b') or '-'))}</b></td></tr>")


def _finding_rows(items: list[dict]) -> str:
    return "".join(f"<li><code>{e(str(i['rule']))}</code> {e(str(i['severity']))}: {e(str(i['message']))}"
                   + (f" (x{i['count']})" if i["count"] > 1 else "") + "</li>" for i in items) or "<li>-</li>"


def compare_page(d: dict) -> str:
    """Two runs side by side: what is different, and whether the same judge looked at the same thing."""
    a, b = d["a"], d["b"]
    link = lambda x: f'<a href="/r/{e(str(x["id"]))}"><code>{e(str(x["id"]))}</code></a> {e(str(x.get("at") or ""))}'
    top = ('<p class="rep-reason">These two are the same run: same fingerprint.</p>' if d["identical"] else "")
    rules = "".join(f"<li>{e(name)}: <code>{e(str(v['a']))}</code> {ARROW} <code>{e(str(v['b']))}</code></li>"
                    for name, v in d["rules"].items()) or "<li>the same rules judged both</li>"
    ev = d["evidence"]
    table = "".join((
        _change("risk verdict" + (f" ({d['verdict']['direction']})" if d["verdict"]["changed"] else ""), d["verdict"]),
        _change("fix status", d["fix"]), _change("verification", d["verification"]),
        _change("snapshot", ev["snapshot"]), _change("proposed patch", ev["patch"]),
        _change("sandbox profile", ev["sandbox_profile"]), _change("attempts", ev["attempts"]),
    ))
    body = (
        f'<p class="crumb"><a href="/runs">{ARROW_BACK} recent runs</a></p>'
        '<h1 class="page-title">Two runs compared</h1>'
        f'<p class="page-lead">{e(d["summary"])}.</p>{top}'
        f'<p class="meta">A: {link(a)} {DOT} B: {link(b)}</p>'
        + _block("What changed", f'<div class="table-wrap"><table><tr><th></th><th>A</th><th>B</th></tr>{table}</table></div>')
        + _block("Findings", f'<p class="meta">{d["findings"]["unchanged"]} finding(s) in both. Compared by rule, severity '
                 'and message, not by line.</p><h3>Only in B (added)</h3><ul>'
                 f'{_finding_rows(d["findings"]["added"])}</ul><h3>Only in A (gone in B)</h3><ul>'
                 f'{_finding_rows(d["findings"]["removed"])}</ul>')
        + _block("Who judged", f"<ul>{rules}</ul>")
    )
    return layout(f"Compare {DOT} VishapHub", body, description="Two VishapHub runs compared.")


def delete_page(record: dict, retention: str = "", team: bool = False) -> str:
    """The confirmation before a run is deleted: what goes, what stays, and that it cannot be undone."""
    run_id = e(str(record.get("id") or ""))
    if team:
        goes = ("the run row with its result, findings and patch. The audit row stays: who deleted it, when, and "
                "the run id, with no content. Usage counters keep their numbers and let go of the id.")
    else:
        goes = ("the run with its findings, patch, fingerprint and record, and your claim on it. If someone else "
                "ran exactly the same material, their copy stays for them.")
    body = (
        f'<p class="crumb"><a href="/r/{run_id}">{ARROW_BACK} back to the run</a></p>'
        f'<h1 class="page-title">Delete run <code>{run_id}</code>?</h1>'
        f'<p class="page-lead">This cannot be undone.</p>'
        f'<section class="block"><h2>What goes</h2><p>{e(goes)}</p></section>'
        '<section class="block"><h2>What does not go</h2><p>Copies you made yourself (an exported file, a link you '
        'sent, an issue you opened) are yours to remove. Running exactly the same material again makes a new run '
        'with the same id.</p></section>'
        + (f'<p class="meta">{e(retention)}</p>' if retention else "")
        + f'<form method="post" action="/r/{run_id}/delete" class="confirm">'
        '<button type="submit" class="btn danger">Delete this run</button> '
        f'<a href="/r/{run_id}">Keep it</a></form>'
    )
    return layout(f"Delete run {record.get('id', '')} {DOT} VishapHub", body, description="Delete a VishapHub run.")


def login_page(error: str = "") -> str:
    """Team members sign in with the API key an operator gave them; the key goes into an HttpOnly cookie."""
    problem = f'<p class="rep-reason" role="alert">{e(error)}</p>' if error else ""
    body = (
        '<div class="empty"><h1 class="page-title">Sign in</h1>'
        '<p>Paste the API key your team\'s operator gave you. It is kept in a cookie this site can read and '
        'scripts cannot, and it is never shown again.</p>' + problem +
        '<form method="post" action="/login">'
        '<p><label for="key">API key</label><br>'
        '<input id="key" name="key" type="password" autocomplete="off" required style="width:100%;max-width:32rem"></p>'
        '<p><button class="btn" type="submit">Sign in</button></p></form></div>')
    return layout("Sign in " + DOT + " VishapHub", body, description="Sign in to a VishapHub team.")


def message_page(title: str, message: str) -> str:
    return layout(title, f'<div class="empty"><h1 class="page-title">{e(title)}</h1><p>{e(message)}</p>'
                         f'<p><a class="btn ghost sm" href="/runs">recent runs</a></p></div>')