# -*- coding: utf-8 -*-
"""Contract tests for the Tauri desktop shell (Block 38).

These do not build the Rust binary — that needs a network to fetch crates — but
they pin the parts that silently rot: the window geometry, the dev/build paths,
the icon set referenced by the bundle, and the "spawn Python, kill Python"
contract in `main.rs`/`backend.rs`.

Run: pytest tests/test_tauri_desktop.py -q
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC_TAURI = ROOT / "src-tauri"
CONFIG = SRC_TAURI / "tauri.conf.json"
MAIN_RS = SRC_TAURI / "src" / "main.rs"
BACKEND_RS = SRC_TAURI / "src" / "backend.rs"
CARGO_TOML = SRC_TAURI / "Cargo.toml"
NEXT_CONFIG = ROOT / "ui-next" / "next.config.ts"


def _config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def test_tauri_config_is_valid_json():
    assert CONFIG.is_file(), "src-tauri/tauri.conf.json is missing"
    assert _config()["productName"] == "Vishap"


def test_window_is_1280x800_titled_vishap():
    """The window moved from config into the Rust builder (it needs
    `data_directory` for the per-user WebView2 profile)."""
    assert "windows" not in _config()["app"]
    main = (SRC_TAURI / "src" / "main.rs").read_text(encoding="utf-8")
    assert "WebviewWindowBuilder::new(" in main
    assert '.title("Vishap")' in main
    assert ".inner_size(1280.0, 800.0)" in main
    # main.rs looks the window up by label, so a rename would break the error card.
    assert '"main"' in main


def test_dev_points_at_next_dev_server_and_build_at_static_export():
    build = _config()["build"]
    assert build["devUrl"] == "http://localhost:3000"
    assert build["frontendDist"] == "../ui-next/out"
    assert "dev" in build["beforeDevCommand"]
    assert "build" in build["beforeBuildCommand"]


def test_bundle_icons_all_exist():
    icons = _config()["bundle"]["icon"]
    assert icons, "bundle.icon must list at least the .ico"
    assert any(icon.endswith(".ico") for icon in icons), "Windows bundle needs an .ico"
    for icon in icons:
        assert (SRC_TAURI / icon).is_file(), f"declared icon does not exist: {icon}"


def test_bundle_targets_are_windows_installers():
    targets = _config()["bundle"]["targets"]
    assert "nsis" in targets
    assert "msi" in targets


def test_next_config_can_export_a_static_site():
    """Block 39 made the export conditional: it is the desktop build only.

    The exact gating (`isDesktop`, `cacheComponents`, the Clerk alias) is pinned
    in `tests/test_desktop_mode.py`; here we only need to know the export path
    still exists and stays paired with unoptimized images.
    """
    text = NEXT_CONFIG.read_text(encoding="utf-8")
    assert re.search(r'output:\s*isDesktop\s*\?\s*["\']export["\']', text), (
        "next.config.ts must export a static site for desktop builds"
    )
    assert re.search(r"unoptimized:\s*true", text), "static export needs images.unoptimized"


def test_cargo_uses_tauri_v2():
    text = CARGO_TOML.read_text(encoding="utf-8")
    assert 'tauri = { version = "2"' in text
    assert 'tauri-build = { version = "2"' in text


def test_main_rs_declares_a_gui_subsystem_for_release():
    text = MAIN_RS.read_text(encoding="utf-8")
    assert 'windows_subsystem = "windows"' in text
    assert "mod backend;" in text


def test_backend_spawns_python_module_and_kills_it_on_close():
    backend = BACKEND_RS.read_text(encoding="utf-8")
    main = MAIN_RS.read_text(encoding="utf-8")

    # The exact command the block asks for: python -m src.main
    assert '"src.main"' in backend
    assert '"python"' in backend

    # Close requested -> stop(); process exit -> stop() as a fallback.
    assert "WindowEvent::CloseRequested" in main
    assert "RunEvent::Exit" in main
    assert "fn stop(&self)" in backend
    assert "child.kill()" in backend


def test_backend_reports_a_missing_python_into_the_window():
    backend = BACKEND_RS.read_text(encoding="utf-8")
    main = MAIN_RS.read_text(encoding="utf-8")
    assert "startup_error" in main, "a failed spawn must reach the window"
    assert "fn show_error" in backend
    assert "textContent" in backend, "error text must be injected as text, not HTML"


def test_backend_is_built_without_new_runtime_dependencies():
    text = CARGO_TOML.read_text(encoding="utf-8")
    deps = re.search(r"\[dependencies\](.*?)(\n\[|\Z)", text, re.S)
    assert deps is not None
    names = set(re.findall(r"^([a-zA-Z0-9_-]+)\s*=", deps.group(1), re.M))
    # `serde` is only there because `tauri::command` (the IPC bridge) needs it; it
    # ships with Tauri anyway. Everything else stays dependency-free.
    assert names == {"tauri", "serde", "serde_json"}


def test_capabilities_grant_only_core_default():
    caps = json.loads((SRC_TAURI / "capabilities" / "default.json").read_text(encoding="utf-8"))
    assert caps["windows"] == ["main"]
    assert caps["permissions"] == ["core:default"]


def test_render_target_is_not_committed():
    gitignore = (SRC_TAURI / ".gitignore").read_text(encoding="utf-8")
    assert "/target/" in gitignore


@pytest.mark.parametrize("name", ["32x32.png", "128x128.png", "128x128@2x.png", "icon.ico"])
def test_icon_assets_present(name):
    assert (SRC_TAURI / "icons" / name).is_file()
