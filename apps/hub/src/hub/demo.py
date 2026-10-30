"""The only runs a stranger may open without owning them: the page's own example.

A run belongs to the browser that made it. The one exception is the example the page
offers under "Try with an example": its material is written here, not typed by a
visitor, so a report of it holds nothing that belongs to anyone. The server decides
that a run is a demo by comparing what arrived with what is written here - never by a
flag in the request, which anyone could set on their own code.

`tests/test_service.py` checks that these strings are the ones `web/app.js` sends.
"""
from __future__ import annotations

EXAMPLE_MATERIAL = "cur.execute(\"select * from users where name = '\" + name + \"'\")"
#: the questions the page puts next to the example, one per language; an empty one is the API default
EXAMPLE_QUESTIONS = frozenset({
    "",
    "is this safe?",
    "\u044d\u0442\u043e \u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e?",
})


def is_demo(args: dict) -> bool:
    """True only for the page's example, with nothing else attached to it."""
    return (
        str(args.get("material") or "").strip() == EXAMPLE_MATERIAL
        and str(args.get("question") or "").strip() in EXAMPLE_QUESTIONS
        and not args.get("files")
        and not args.get("spec")
    )
