"""What the code under test may see and reach.

The validator runs the deliverable's own tests and imports its entry point. That is executing someone
else's code, so two things are decided here and nowhere else: the environment it gets, and which paths a
spec may name.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess

#: The only variables the code under test inherits. Nothing else: the host's keys, database URLs and
#: tokens live in its environment, and a test that prints `os.environ` would otherwise print them.
_KEEP = ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL")

#: A dotted Python name. Anything else (a path, a `;`, a space) is not an entry point.
ENTRY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


def clean_env() -> dict[str, str]:
    env = {key: os.environ[key] for key in _KEEP if key in os.environ}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def escapes(root: str, rel: object) -> bool:
    """True if `rel` is not a path that stays inside `root` (absolute, `..`, NUL, empty, not a string)."""
    if not isinstance(rel, str) or not rel or "\x00" in rel:
        return True
    if os.path.isabs(rel) or rel.startswith(("/", "\\")):
        return True
    base = os.path.realpath(root)
    try:
        return os.path.commonpath([base, os.path.realpath(os.path.join(base, rel))]) != base
    except ValueError:  # another drive on Windows
        return True


def spec_problems(root: str, spec) -> list[str]:
    """What in the spec points outside the deliverable. Empty means the spec may be used."""
    problems = [f"{field} path is outside the deliverable: {rel!r}"
                for field in ("files", "tests") for rel in getattr(spec, field)
                if escapes(root, rel)]
    entry = spec.entry
    if entry and not (isinstance(entry, str) and ENTRY.fullmatch(entry)):
        problems.append(f"entry is not a dotted module name: {entry!r}")
    return problems


#: Probing `unshare -n` on every run would cost more than the run: ask once.
_NET_OFF: list[str] | None = None


def network_off() -> list[str]:
    """Prefix that runs a command without a network, or ``[]`` where the platform cannot.

    `unshare -n` needs Linux and the privilege to create a network namespace. Inside the
    container that holds; in CI without root it does not, and on Windows it does not exist.
    Probed once, and a failed probe is not an error — it is "this platform cannot".
    """
    global _NET_OFF
    if _NET_OFF is not None:
        return _NET_OFF
    _NET_OFF = []
    if os.name == "posix" and os.getenv("VISHAP_VALIDATOR_NO_NETWORK", "1") != "0":
        exe = shutil.which("unshare")
        if exe:
            try:
                probe = subprocess.run([exe, "-n", "--", "true"], capture_output=True, timeout=10, check=False)
            except (OSError, subprocess.SubprocessError):
                probe = None
            if probe is not None and probe.returncode == 0:
                _NET_OFF = [exe, "-n", "--"]
    return _NET_OFF


def rlimits():
    """A ``preexec_fn`` that caps what the code under test may take, or ``None`` off POSIX.

    Without them one line of submitted code (`while True: os.fork()`) costs the container.
    The caps are ceilings, not guarantees: the hard limit is never raised here.
    """
    if os.name != "posix":
        return None
    import resource

    cpu = int(os.getenv("VISHAP_VALIDATOR_CPU_SECONDS", "30"))
    mem = int(os.getenv("VISHAP_VALIDATOR_MEMORY_MB", "1024")) * 1024 * 1024
    fsize = int(os.getenv("VISHAP_VALIDATOR_FSIZE_MB", "64")) * 1024 * 1024
    procs = int(os.getenv("VISHAP_VALIDATOR_MAX_PROCS", "64"))

    def apply() -> None:
        for what, value in ((resource.RLIMIT_CPU, cpu), (resource.RLIMIT_AS, mem),
                            (resource.RLIMIT_FSIZE, fsize), (resource.RLIMIT_NPROC, procs)):
            try:
                _soft, hard = resource.getrlimit(what)
                limit = value if hard in (-1, resource.RLIM_INFINITY) else min(value, hard)
                resource.setrlimit(what, (limit, hard))
            except (ValueError, OSError):
                continue

    return apply
