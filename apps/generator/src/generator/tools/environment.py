"""What the machine that runs Verify has: the Python version and the libraries the design names.

The build prompt used to learn that Flask was missing only from the first failed round. Now the model is told
before it writes, and the run records what it was told, so a framework swap is visible in the result.
"""

from __future__ import annotations

import importlib.util
import platform

# library_check name -> importable module. A name that is not here is not a Python library (spring-boot) and
# is left out: this machine cannot say anything about it.
IMPORT_NAMES = {"flask": "flask"}


def library_status(names) -> dict[str, str]:
    """{name: "installed" | "missing"} for the names that are Python libraries."""
    out: dict[str, str] = {}
    for name in names:
        module = IMPORT_NAMES.get(name)
        if module is None:
            continue
        try:
            found = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            found = False
        out[name] = "installed" if found else "missing"
    return out


def environment_for(design) -> dict:
    """The facts the build prompt and the report carry: Python version and the status of the planned libraries."""
    names = sorted({lib for f in design.files for lib in f.library_check})
    return {"python": platform.python_version(), "libraries": library_status(names)}


def environment_lines(env: dict) -> list[str]:
    """The ENVIRONMENT section of the build message. Empty when there is nothing to say."""
    libs = env.get("libraries") or {}
    if not libs:
        return []
    lines = ["ENVIRONMENT:", f"- python: {env.get('python', '?')}"]
    for name, state in sorted(libs.items()):
        if state == "installed":
            lines.append(f"- {name}: installed")
        else:
            lines.append(f"- {name}: NOT installed on the machine that runs Verify. Do not import it. "
                         "Use only the standard library; an HTTP endpoint is a WSGI callable `app(environ, start_response)`.")
    return lines


def fallbacks(env: dict) -> list[str]:
    """Libraries the design planned that this machine lacks: the model had to write something else."""
    return sorted(n for n, s in (env.get("libraries") or {}).items() if s == "missing")
