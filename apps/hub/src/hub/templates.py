"""Pages the hub serves: one layout, one stylesheet, escaped data.

The report page is the product: a verdict that can be opened, read and forwarded by
someone who was not in the room. The list page answers "what ran lately". Both are
built here, away from the request handler, so a page cannot grow a second set of
headers or a second way to escape a string.
"""
from __future__ import annotations

import html
import json

#: Everything on these pages is data, never markup: escape once, here.
e = html.escape


def layout(title: str, body: str, description: str = "") -> str:
    desc = f'<meta name="description" content="{e(description)}">' if description else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="theme-color" content="#020617">
<meta name="color-scheme" content="dark">
{desc}
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/styles.css">
</head><body>
<a class="skip" href="#main">Skip to content</a>
<div class="shell"><div class="doc">
<main id="main">{body}</main>
<footer><a href="/">VishapHub</a> | <a href="/runs">recent runs</a>
<span class="right">hub v{_version()}</span></footer>
</div></div>
</body></html>"""


def _version() -> str:
    from .version import __version__
    return e(__version__)


def _block(title: str, body: str) -> str:
    return f'<section><h2>{e(title)}</h2>{body}</section>'


def report_page(record: dict) -> str:
    """One run: the verdict, every step, every finding with its source, what was not checked."""
    result = record.get("result") or {}
    fp = result.get("fingerprint") or {}
    not_checked = result.get("not_checked") or []
    findings = result.get("findings") or []
    steps = result.get("steps") or []

    verdict = e(str(result.get("verdict") or record.get("verdict") or "-"))
    state = "ok" if result.get("ok") else "bad"
    plan = " → ".join((result.get("plan") or {}).get("stages") or [])

    rows = "".join(
        f"<tr><td>{e(str(s.get('stage')))}</td><td>{e(str(s.get('verdict') or '-'))}</td>"
        f"<td>{'ok' if s.get('ok') else 'fail'}</td><td>{e(str(s.get('detail') or ''))}</td></tr>"
        for s in steps
    ) or "<tr><td colspan=4>-</td></tr>"
    found = "".join(
        f"<li><b>{e(str(f.get('severity') or ''))}</b> {e(str(f.get('rule') or ''))}"
        f"{' @ ' + e(str(f.get('line'))) if f.get('line') else ''}: {e(str(f.get('message') or ''))}"
        f"{' <i>(' + e(str(f.get('source'))) + ')</i>' if f.get('source') else ''}</li>"
        for f in findings
    ) or "<li>nothing matched</li>"
    missed = "".join(f"<li>{e(str(item))}</li>" for item in not_checked) or "<li>-</li>"
    rules = e(json.dumps(fp.get("rules") or {}, ensure_ascii=False))

    body = f"""
<h1>Run {e(str(record.get('id') or ''))}</h1>
<p class="meta-row">at <code>{e(str(record.get('at') or ''))}</code> · plan <code>{e(plan)}</code> ·
fingerprint <code>{e(str(fp.get('digest') or ''))[:32]}</code></p>
<p><span class="badge-verdict {state}">{verdict}</span>
<span class="dim">{e(str(result.get('reason') or ''))}</span></p>
<p>{e(str(result.get('summary') or ''))}</p>
{_block("Steps", f"<table><tr><th>stage</th><th>verdict</th><th>state</th><th>detail</th></tr>{rows}</table>")}
{_block("Findings", f"<ul>{found}</ul>")}
{_block("Not checked", f"<ul>{missed}</ul>")}
{_block("Rules that judged", f"<p><code>{rules}</code></p>")}
"""
    return layout(f"Run {record.get('id', '')} · VishapHub", body,
                  description=f"A reproducible VishapHub run: verdict {result.get('verdict', '')}.")


def runs_page(runs: list[dict]) -> str:
    if not runs:
        body = "<h1>Recent runs</h1><p>Nothing has been run yet.</p>"
        return layout("Recent runs · VishapHub", body, description="Runs kept by this VishapHub.")

    items = "".join(
        f'<li><div class="line"><b>{e(str(r.get("verdict") or "-"))}</b>'
        f'<a href="/r/{e(str(r.get("id") or ""))}">{e(str(r.get("id") or ""))}</a>'
        f'<span class="dim">{e(str(r.get("at") or ""))}</span>'
        f'<span class="dim">{" → ".join((r.get("plan") or {}).get("stages") or [])}</span></div>'
        + (f'<div class="sum">{e(str(r.get("summary") or ""))}</div>' if r.get("summary") else "")
        + "</li>"
        for r in runs
    )
    body = f"<h1>Recent runs</h1><ul class=\"runs-list\">{items}</ul>"
    return layout("Recent runs · VishapHub", body,
                  description="The runs this VishapHub remembers, newest first.")


def message_page(title: str, message: str) -> str:
    return layout(title, f"<h1>{e(title)}</h1><p>{e(message)}</p>")
