# -*- coding: utf-8 -*-
"""Desktop mode contract (Block 39).

The desktop build is the same Next.js app with `NEXT_PUBLIC_DESKTOP=1`, a static
export, and Clerk replaced by local stubs. These tests pin the switches that make
that work РІР‚вЂќ every one of them was needed to get `next build` to exit 0:

* `output: 'export'` and `images.unoptimized` only in desktop mode;
* `cacheComponents` off in desktop mode (PPR cannot be enabled in export mode);
* `@clerk/nextjs` aliased to a stub (Clerk's barrel registers server actions,
  which a static export refuses);
* no dynamic `/report/[id]` route РІР‚вЂќ the id travels in `?id=`;
* Clerk hooks only reachable behind the `IS_DESKTOP` gate.

None of this executes Next or a browser; it asserts on source text, so it runs in
the normal pytest suite.

Run: pytest tests/test_desktop_mode.py -q
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "ui-next"
SRC = UI / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# next.config.ts
# ---------------------------------------------------------------------------

def test_next_config_switches_output_on_the_desktop_flag():
    text = _read(UI / "next.config.ts")
    assert 'process.env.NEXT_PUBLIC_DESKTOP === "1"' in text
    assert re.search(r'output:\s*isDesktop\s*\?\s*"export"', text), "output must be gated"
    assert re.search(r"unoptimized:\s*true", text)
    assert re.search(r"images:\s*isDesktop", text), "images.unoptimized must be desktop-only"


def test_cache_components_is_disabled_for_the_export():
    """PPR cannot be enabled in export mode РІР‚вЂќ the build fails with an invariant."""
    text = _read(UI / "next.config.ts")
    assert re.search(r"cacheComponents:\s*!isDesktop", text)
    assert re.search(r"partialPrefetching:\s*!isDesktop", text)


def test_clerk_is_aliased_to_a_stub_in_desktop_mode():
    text = _read(UI / "next.config.ts")
    assert '"@clerk/nextjs":' in text
    assert '"@clerk/nextjs/server":' in text
    assert "resolveAlias" in text
    # Turbopack rejects absolute Windows paths in resolveAlias.
    assert '"@clerk/nextjs": clerkDesktopRequest' in text
    assert re.search(r'clerkDesktopRequest\s*=\s*"\./src/lib/clerk-desktop\.tsx"', text)


def test_clerk_stubs_exist_and_export_what_the_app_imports():
    client = _read(SRC / "lib" / "clerk-desktop.tsx")
    for name in ("ClerkProvider", "SignInButton", "UserButton", "useUser"):
        assert f"export function {name}" in client, f"stub is missing {name}"

    server = _read(SRC / "lib" / "clerk-server-desktop.ts")
    assert "export function clerkMiddleware" in server
    assert "export function createRouteMatcher" in server


def test_desktop_flag_module_reads_the_public_env():
    text = _read(SRC / "lib" / "desktop.ts")
    assert 'process.env.NEXT_PUBLIC_DESKTOP === "1"' in text
    assert "export const IS_DESKTOP" in text


# ---------------------------------------------------------------------------
# Clerk gating
# ---------------------------------------------------------------------------

def test_layout_has_no_clerk_provider():
    text = _read(SRC / "app" / "layout.tsx")
    assert "<ClerkProvider" not in text, "Clerk is removed from layout (dev/desktop use stubs)"
    assert "return page;" in text

def test_proxy_is_a_pass_through():
    text = _read(SRC / "proxy.ts")
    assert "NextResponse.next()" in text
    assert "clerkMiddleware" not in text, "Clerk middleware is removed"
    assert "IS_DESKTOP" not in text, "proxy is now a plain pass-through"

def test_clerk_hooks_only_run_behind_the_gate():
    """`useUser` must never execute when no provider is mounted."""
    for rel in ("components/Navbar.tsx", "app/page.tsx"):
        text = _read(SRC / rel)
        assert "if (IS_DESKTOP)" in text, f"{rel} must gate before touching Clerk"
        # The hook lives in its own web-only component, rendered after the gate.
        assert "function Web" in text, f"{rel} needs a web-only wrapper for Clerk hooks"


# ---------------------------------------------------------------------------
# Report routing: ?id= instead of /report/[id]
# ---------------------------------------------------------------------------

def test_report_page_reads_the_id_from_the_query_string():
    text = _read(SRC / "app" / "report" / "page.tsx")
    assert "useSearchParams()" in text
    assert 'searchParams.get("id")' in text
    assert "useParams" not in text


def test_dynamic_report_route_is_gone():
    assert not (SRC / "app" / "report" / "[id]").exists(), (
        "a dynamic [id] route cannot be part of a static export"
    )


def test_links_point_at_the_query_string_route():
    job_card = _read(SRC / "components" / "JobCard.tsx")
    analyze = _read(SRC / "app" / "analyze" / "page.tsx")

    for text, label in ((job_card, "JobCard.tsx"), (analyze, "analyze/page.tsx")):
        assert "/report/${job.job_id}" not in text, f"{label} still builds the dynamic route"
        assert "/report?id=${encodeURIComponent(job.job_id)}" in text, f"{label} must use ?id="


# ---------------------------------------------------------------------------
# Build wiring
# ---------------------------------------------------------------------------

def test_desktop_build_script_and_tauri_command_agree():
    pkg = json.loads(_read(UI / "package.json"))
    assert pkg["scripts"]["build:desktop"] == "node ./scripts/build-desktop.mjs"
    assert pkg["scripts"]["build"] == "next build", "the web build must stay untouched"

    conf = json.loads(_read(ROOT / "src-tauri" / "tauri.conf.json"))
    hook = conf["build"]["beforeBuildCommand"]
    # Tauri runs the hook from an unpredictable directory (root, docs-site or
    # src-tauri), so it must resolve ui-next from any of them.
    assert "npm --prefix ui-next run build:desktop" in hook
    assert "npm --prefix ..\\ui-next run build:desktop" in hook
    assert "if exist ui-next\\package.json" in hook


def test_desktop_build_script_sets_the_flag():
    text = _read(UI / "scripts" / "build-desktop.mjs")
    assert 'NEXT_PUBLIC_DESKTOP: "1"' in text
    assert "stdio: \"inherit\"" in text


def test_api_fetch_falls_back_to_tauri_ipc_on_cors_block():
    """WebView2 can surface a CORS/PNA block as a Response with status 0 instead
    of throwing; the UI must detect that and use the Rust IPC bridge."""
    text = _read(UI / "src" / "lib" / "api.ts")
    assert 'response.status === 0 || response.type === "opaque"' in text
    assert 'invoke!("api_request"' in text
    assert "window.__TAURI__" in text
    assert "withGlobalTauri" in _read(ROOT / "src-tauri" / "tauri.conf.json")

