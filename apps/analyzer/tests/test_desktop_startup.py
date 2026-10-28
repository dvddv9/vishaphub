# -*- coding: utf-8 -*-
"""Startup resilience of the desktop shell (Block 40).

The packaged app used to open a black window and die with `0xc0000409`, because
Tauri creates the window before the WebView2 webview and turns a webview failure
into a panic. These tests pin the three defences that make such a failure
visible and recoverable, plus the two configuration fixes it needed.

Source-level assertions only: no Rust toolchain, no Windows GUI.

Run: pytest tests/test_desktop_startup.py -q
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC_TAURI = ROOT / "src-tauri"
MAIN_RS = SRC_TAURI / "src" / "main.rs"
STARTUP_RS = SRC_TAURI / "src" / "startup.rs"
BACKEND_RS = SRC_TAURI / "src" / "backend.rs"
CARGO_TOML = SRC_TAURI / "Cargo.toml"
CONFIG = SRC_TAURI / "tauri.conf.json"
RESET_SCRIPT = ROOT / "scripts" / "reset_desktop_profile.ps1"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# DevTools: the feature, not just the config key
# ---------------------------------------------------------------------------

def test_devtools_feature_is_compiled_in():
    """`"devtools": true` in the window config is inert without this feature."""
    text = _read(CARGO_TOML)
    assert re.search(r'tauri\s*=\s*\{[^}]*features\s*=\s*\[[^\]]*"devtools"', text), (
        "release builds need the devtools feature, otherwise F12 does nothing"
    )


def test_devtools_are_enabled_in_the_rust_window_builder():
    """The window is built in Rust now, so the flag moved with it."""
    text = _read(MAIN_RS)
    assert ".devtools(true)" in text


# ---------------------------------------------------------------------------
# A failed start must explain itself instead of vanishing
# ---------------------------------------------------------------------------

def test_main_wires_the_startup_guards_first():
    text = _read(MAIN_RS)
    assert "mod startup;" in text
    # Order matters: the hook must be installed before anything can panic, and the
    # profile repair must run before the app is built.
    hook_at = text.index("startup::install_panic_hook()")
    repair_at = text.index("startup::recover_profile_if_needed()")
    builder_at = text.index("tauri::Builder::default()")
    assert hook_at < builder_at
    assert repair_at < builder_at


def test_startup_is_marked_healthy_only_after_the_webview_exists():
    text = _read(MAIN_RS)
    setup_at = text.index(".setup(move |app| {")
    build_at = text.index(".data_directory(profile.clone())")
    build_end = text.index(".build()?;")
    mark_at = text.index("startup::mark_started()")
    assert setup_at < build_at < build_end < mark_at, (
        "the marker may only be cleared after the webview was built, or a "
        "failed start would look healthy"
    )


def test_build_failure_is_handled_not_expect_panicked():
    # Only production code: the `#[cfg(test)]` module is allowed to use `.expect()`.
    text = _read(MAIN_RS).split("#[cfg(test)]")[0]
    assert ".expect(" not in text, (
        "no .expect() on the builder: a panic there is invisible in a GUI binary"
    )
    assert "startup::fatal(" in text


def test_panic_hook_logs_and_shows_a_native_dialog():
    text = _read(STARTUP_RS)
    assert "set_hook" in text
    assert "webview-startup-failed.txt" in text
    assert "startup-error.log" in text
    assert "MessageBoxW" in text, "a GUI subsystem binary needs a dialog, not stderr"
    assert "std::process::exit(1)" in text, "exit before the abort/WER dump"


def test_startup_error_log_records_the_previous_failure():
    text = _read(STARTUP_RS)
    assert "fn append_log" in text
    assert "recovering from a failed start" in text


# ---------------------------------------------------------------------------
# WebView2 profile repair
# ---------------------------------------------------------------------------

def test_repair_moves_the_wedged_profile_aside():
    text = _read(STARTUP_RS)
    assert 'const PROFILE_DIR: &str = "webview2";' in text
    assert 'const BROKEN_PROFILE_DIR: &str = "webview2.broken";' in text
    assert "std::fs::rename" in text, "the profile is moved, not deleted"


def test_identifier_matches_the_bundle_so_the_profile_path_is_right():
    config_identifier = json.loads(_read(CONFIG))["identifier"]
    match = re.search(r'pub const IDENTIFIER: &str = "([^"]+)";', _read(STARTUP_RS))
    assert match, "startup.rs must declare the bundle identifier"
    assert match.group(1) == config_identifier, (
        "startup.rs and tauri.conf.json must agree, or the repair targets the wrong folder"
    )


def test_reset_script_repairs_the_same_paths():
    text = _read(RESET_SCRIPT)
    assert "$env:LOCALAPPDATA" in text
    assert "webview2.broken" in text
    assert "msedgewebview2" in text, "leftover WebView2 processes hold the profile"


# ---------------------------------------------------------------------------
# Backend interpreter: the virtualenv, not the system Python
# ---------------------------------------------------------------------------

def test_backend_prefers_the_project_virtualenv():
    text = _read(BACKEND_RS)
    assert "fn venv_python(" in text
    assert 'for venv in [".venv", "venv"]' in text

    # ...and only then falls back to the bare interpreter name.
    venv_at = text.index('for venv in [".venv", "venv"]')
    python_at = text.index('"python".to_string()')
    assert venv_at < python_at, "the venv must be tried before `python` on PATH"


def test_embedded_frontend_is_covered_by_a_rust_test():
    """The white-window class of bugs: assets are only embedded with the
    `tauri/custom-protocol` feature, so the build mode must be asserted."""
    text = _read(MAIN_RS)
    assert "fn the_exported_frontend_is_embedded" in text
    assert "index.txt" in text, "the Next 16 RSC payload belongs in the bundle"
    assert "_next/static/chunks/" in text
    assert "tauri/custom-protocol" in text, (
        "without the feature a plain `cargo build --release` embeds nothing"
    )
    assert "assets.iter().next().is_none()" in text, "skip when nothing is embedded"


def test_troubleshooting_docs_describe_the_build_mode_trap():
    docs = _read(ROOT / "docs" / "TAURI.md")
    assert "custom-protocol" in docs
    assert "0xc0000409" in docs, "the crash signature must be documented"
    assert "0x800700AA" in docs


# ---------------------------------------------------------------------------
# Elevation (UAC) and the backend lifecycle -- Block 41 / 41.1
# ---------------------------------------------------------------------------

MANIFEST = SRC_TAURI / "app.manifest"
BUILD_RS = SRC_TAURI / "build.rs"
NET_RS = SRC_TAURI / "src" / "net.rs"


def test_the_app_runs_without_elevation():
    """v7 removed the `requireAdministrator` manifest.

    Elevation was a workaround for a WebView2 profile created by an elevated run.
    The real fix is a per-user profile (`startup::prepare_webview_profile`), so
    the shipped manifest is tauri-build's default `asInvoker`.
    """
    assert not MANIFEST.exists(), "no custom application manifest is embedded"
    build = _read(BUILD_RS)
    # Only the call site matters: comments still explain the history.
    assert "WindowsAttributes" not in build
    assert "app_manifest" not in build


def test_the_webview_gets_its_own_per_user_profile():
    startup = _read(STARTUP_RS)
    assert "pub fn prepare_webview_profile" in startup
    assert "data_directory" in _read(MAIN_RS), (
        "only the Rust window builder can point WebView2 at the per-user profile"
    )
    assert "startup::prepare_webview_profile()" in _read(MAIN_RS)


def test_no_elevation_escape_hatch_is_left_behind():
    build = _read(BUILD_RS)
    assert "VISHAP_SKIP_ADMIN_MANIFEST" not in build, (
        "the escape hatch existed only for the admin manifest; if it is back, the "
        "manifest is back too"
    )
    # tauri-build owns the resource section; winres/embed-resource would clash.
    cargo = _read(CARGO_TOML)
    assert "winres" not in cargo
    assert "embed-resource" not in cargo


def test_installer_is_per_user():
    """A non-elevated app installs per user; perMachine would ask for admin."""
    bundle = json.loads(_read(CONFIG))["bundle"]
    assert bundle["windows"]["nsis"]["installMode"] == "currentUser"


def test_window_is_built_in_rust_and_starts_hidden():
    config = json.loads(_read(CONFIG))
    assert "windows" not in config["app"], (
        "the window is created with WebviewWindowBuilder so it can carry "
        "data_directory; keeping a config window would create it twice"
    )
    main = _read(MAIN_RS)
    assert "WebviewWindowBuilder::new" in main
    assert ".visible(false)" in main, (
        "the UI must not render its 'Cannot reach the API' state during startup"
    )
    assert "backend::reveal(&handle)" in main, "a failed spawn must reveal the window"
    backend = _read(BACKEND_RS)
    assert "fn reveal(app: &AppHandle)" in backend


def test_backend_kills_a_stale_port_owner_before_spawning():
    text = _read(BACKEND_RS)
    assert "crate::net::kill_port(BACKEND_PORT)" in text
    kill_at = text.index("crate::net::kill_port(BACKEND_PORT)")
    spawn_at = text.index("for (program, args) in python_candidates")
    assert kill_at < spawn_at, "the port must be freed before python starts"


def test_readiness_uses_the_health_endpoint_not_a_bare_tcp_connect():
    text = _read(BACKEND_RS)
    assert "crate::net::http_health_ok" in text
    assert "port_open" not in text, "an open socket is not a ready backend"


def test_net_module_asks_the_loopback_ipv4_address():
    text = _read(NET_RS)
    assert "127, 0, 0, 1" in text
    assert "GET /health HTTP/1.1" in text
    assert "GetExtendedTcpTable" in text, "port owners come from the OS, not netstat"
    assert "never terminate its own process" in _read(
        ROOT / "src-tauri" / "src" / "net.rs"
    ), "kill_port must not kill the app itself"


# ---------------------------------------------------------------------------
# PowerShell scripts must stay ASCII
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("script", sorted(p.name for p in (ROOT / "scripts").glob("*.ps1")))
def test_powershell_scripts_are_ascii_only(script):
    """PowerShell 5.1 reads BOM-less files as ANSI: a UTF-8 em dash becomes a
    smart quote, which terminates a string and breaks the whole script."""
    path = ROOT / "scripts" / script
    raw = path.read_bytes()
    offenders = [(i, b) for i, b in enumerate(raw) if b > 0x7F]
    assert not offenders, (
        f"{script} has non-ASCII bytes at offset {offenders[0][0]}; "
        "PowerShell 5.1 will misparse it"
    )
