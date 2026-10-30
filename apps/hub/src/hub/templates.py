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
        source = f" <i>({e(str(f.get('source')))})</i>" if f.get("source") else ""
        return f"<li>{badge}{e(str(f.get('rule') or ''))}{line}: {e(str(f.get('message') or ''))}{source}</li>"

    found = "".join(_finding(f) for f in findings) or "<li>nothing matched</li>"
    missed = "".join(f"<li>{e(str(item))}</li>" for item in not_checked) or "<li>-</li>"
    rule_chips = "".join(
        f"<span>{e(str(name))} <code>{e(str(version))}</code></span>"
        for name, version in (fp.get("rules") or {}).items()
    ) or "<span>-</span>"

    summary = str(result.get("summary") or "")
    reason = str(result.get("reason") or "")
    body = f"""
<p class="crumb"><a href="/runs">{ARROW_BACK} recent runs</a></p>
<section class="rep-hero">
<div class="rep-verdict {state}"><span class="label">verdict</span><b>{verdict}</b></div>
<div class="rep-head">
<h1>Run <code>{e(str(record.get('id') or ''))}</code></h1>
<div class="meta-row"><span>at {e(str(record.get('at') or ''))}</span><span>plan {e(plan)}</span><span>fingerprint <code>{e(str(fp.get('digest') or ''))[:32]}</code></span></div>
{f'<p class="rep-sum">{e(summary)}</p>' if summary else ''}
{f'<p class="rep-reason">{e(reason)}</p>' if reason else ''}
{f'<p class="meta">{e(retention)}</p>' if retention else ''}
</div>
</section>
{_block("Steps", f'<div class="table-wrap"><table><tr><th>stage</th><th>verdict</th><th>state</th><th>detail</th></tr>{rows}</table></div>')}
{_block("Findings", f"<ul>{found}</ul>")}
{_block("Not checked", f"<ul>{missed}</ul>")}
{_block("Rules that judged", f'<div class="meta-row">{rule_chips}</div>')}
"""
    return layout(f"Run {record.get('id', '')} {DOT} VishapHub", body,
                  description=f"A reproducible VishapHub run: verdict {result.get('verdict', '')}.")


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
        f'<span>{e(f" {ARROW} ".join((r.get("plan") or {}).get("stages") or []))}</span></div>'
        + (f'<div class="sum">{e(str(r.get("summary") or ""))}</div>' if r.get("summary") else "")
        + "</li>"
        for r in runs
    )
    body = f'{head}<ul class="runs-list">{items}</ul>'
    return layout(f"Recent runs {DOT} VishapHub", body,
                  description="The runs this VishapHub remembers, newest first.")


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