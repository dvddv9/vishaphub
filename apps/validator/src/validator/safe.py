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
    guard = network_guard_dir()
    if guard:
        env["PYTHONPATH"] = guard
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


# --- the network guard ---------------------------------------------------------------------------
# `unshare -n` needs a privilege a non-root user in a container does not have (checked in the hub
# image: "Operation not permitted", with and without -r). There `network_off()` is `[]` and the code
# under test would keep the whole network. The guard needs no privilege: `_netguard.py` is loaded as
# `sitecustomize` by the child Python and refuses every non-UNIX socket. It stops the ordinary ways
# out (requests, urllib, sockets, DNS), not ctypes / raw `_socket` / a `curl` subprocess; only a
# network namespace or `docker run --network none` stops those. `isolation()` says which one a run had.

_GUARD_DIR: str | None = None


def _off() -> bool:
    return os.getenv("VISHAP_VALIDATOR_NO_NETWORK", "1") == "0"


def network_guard_dir() -> str:
    """Directory whose `sitecustomize.py` is the guard, or "" when the guard is switched off."""
    global _GUARD_DIR
    if _off():
        return ""
    if _GUARD_DIR is None or not os.path.isfile(os.path.join(_GUARD_DIR, "sitecustomize.py")):
        import atexit
        import tempfile

        _GUARD_DIR = tempfile.mkdtemp(prefix="vishap-guard-")
        shutil.copyfile(os.path.join(os.path.dirname(__file__), "_netguard.py"),
                        os.path.join(_GUARD_DIR, "sitecustomize.py"))
        atexit.register(shutil.rmtree, _GUARD_DIR, True)
    return _GUARD_DIR


# --- a worker container that is itself the network cut-off -----------------------------------------
# `docker run --network none --read-only` cuts the network off by construction, but the validator inside
# cannot take that on faith: a runner that forgot the flag would otherwise be believed. So the container
# is only trusted when the runner declares it (VISHAP_VALIDATOR_ISOLATION=container) AND the process
# confirms it from inside: nothing but loopback, outbound connections refused, the root filesystem
# mounted read-only, no credential-looking variables in its own environment. The evidence goes into the report; a failed check means no code is run.

_CONTAINER: dict | None = None
_PROBE_HOSTS = ("1.1.1.1", "9.9.9.9")


def _outbound_refused() -> bool:
    import socket

    for host in _PROBE_HOSTS:
        try:
            socket.create_connection((host, 443), timeout=2).close()
        except OSError:
            continue
        return False
    return True


def _root_read_only() -> bool:
    try:
        with open("/proc/mounts", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) > 3 and parts[1] == "/":
                    return "ro" in parts[3].split(",")
    except OSError:
        return False
    return False


#: Names that look like a credential. The code under test can read the worker's own start-up
#: environment from /proc/<ppid>/environ, and no filtering inside the process hides that: the only
#: control is that the worker is started without secrets. This is a tripwire on names, not a scanner of
#: values. GPG_KEY is the public key id the python base image ships.
_SECRET_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL", "OIDC", "AUTH")
_PUBLIC_ENV = frozenset({"GPG_KEY"})


def _secret_env_names() -> list[str]:
    try:
        with open("/proc/self/environ", "rb") as fh:
            raw = fh.read()
    except OSError:
        return ["<environment unreadable>"]
    names = [item.split(b"=", 1)[0].decode("utf-8", "replace") for item in raw.split(b"\0") if item]
    return sorted(n for n in names if n not in _PUBLIC_ENV and any(h in n.upper() for h in _SECRET_HINTS))

def container_evidence() -> dict:
    """What this process could confirm about being the inside of an isolated worker container."""
    global _CONTAINER
    if _CONTAINER is not None:
        return _CONTAINER
    ev: dict = {"declared": os.getenv("VISHAP_VALIDATOR_ISOLATION") == "container", "ok": False}
    if ev["declared"] and os.name == "posix":
        try:
            ev["interfaces"] = sorted(os.listdir("/sys/class/net"))
        except OSError:
            ev["interfaces"] = None
        ev["only_loopback"] = ev["interfaces"] == ["lo"]
        ev["outbound_refused"] = _outbound_refused()
        ev["root_read_only"] = _root_read_only()
        ev["secret_env_names"] = _secret_env_names()
        ev["env_clean"] = not ev["secret_env_names"]
        ev["ok"] = bool(ev["only_loopback"] and ev["outbound_refused"] and ev["root_read_only"] and ev["env_clean"])
    _CONTAINER = ev
    return ev


def isolation() -> str:
    """How the network is kept from the code under test: "netns", "container", "guard" or "none"."""
    if _off():
        return "none"
    if network_off():
        return "netns"
    return "container" if container_evidence()["ok"] else "guard"


def isolation_note() -> str:
    """The line a check puts in the report, with the evidence when a container was what held."""
    if isolation() != "container":
        return f"network: {isolation()}"
    return "network: container (loopback only, outbound refused, root read-only, no secrets in env)"


def refusal(require_netns: bool = False, host_ok: bool = False) -> str:
    """Why submitted code must not be run on this host at all, or "".

    VISHAP_VALIDATOR_REQUIRE_NETNS=1 is for a host that serves other people: without a real network
    namespace, or a worker container that confirmed its own isolation, nothing submitted is run.
    `host_ok` is the installer's own decision to run on this machine (the hub's VISHAP_HUB_ISOLATION=host):
    it overrides both the argument and the variable, and the caller records that the run was not isolated.
    """
    if host_ok:
        return ""
    require = require_netns or os.getenv("VISHAP_VALIDATOR_REQUIRE_NETNS") == "1"
    if require and isolation() not in ("netns", "container"):
        ev = container_evidence()
        if ev["declared"]:
            failed = [k for k in ("only_loopback", "outbound_refused", "root_read_only", "env_clean") if not ev.get(k)]
            if "env_clean" in failed:
                failed[failed.index("env_clean")] = "secrets in the worker environment: " + ", ".join(ev.get("secret_env_names", []))
            return ("the worker container was declared isolated but did not confirm it "
                    f"({', '.join(failed) or 'not a POSIX host'}); nothing was run")
        return ("this host cannot cut the network off from submitted code (no network namespace) "
                "and strict network isolation is required; nothing was run")
    return ""