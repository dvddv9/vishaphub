# Vishap desktop shell (Tauri 2)

`src-tauri/` wraps the Next.js UI in a native Windows window and owns the local
FastAPI backend. This document is the decision record for Block 38.

## What the shell does

1. On startup, resolves the Python project root and spawns `python -m src.main`
   in that directory (stdout/stderr go to `<app log dir>/backend.log`, no console
   window).
2. Polls `127.0.0.1:5001` for up to 45 s. If the process dies or never answers,
   an error card is painted over the window with the failure reason and the tail
   of the backend log.
3. Loads the UI: `http://localhost:3000` in dev, the exported static site in a
   release build.
4. On window close (and on process exit as a fallback) it kills the Python child,
   so nothing keeps port 5001 or the CPU after the window is gone.

The interpreter is looked up in this order, first hit wins:

| # | Candidate | When |
|---|-----------|------|
| 1 | `%VISHAP_PYTHON%` | explicit override, e.g. `.venv\Scripts\python.exe` |
| 2 | `<home>\python\python.exe` | interpreter bundled next to the app (future sidecar) |
| 3 | `python` on `PATH` | normal developer machine |
| 4 | `py -3` | Windows launcher, no `python` on `PATH` |

`<home>` is the first of: `%VISHAP_HOME%`, the Cargo manifest's parent (dev), the
bundle's resource dir, the executable's directory and its four ancestors — chosen
by "contains `src\main.py`".

## Commands

```powershell
# dev: Next dev server on :3000 + Python backend spawned by the shell
cargo tauri dev

# release: static export into ui-next/out, then .exe (+ installers with bundling)
cargo tauri build
```

Run it **from the repository root**. Artifacts:

- `src-tauri/target/release/vishap-desktop.exe`
- `src-tauri/target/release/bundle/nsis/*.exe` (per-user installer)
- `src-tauri/target/release/bundle/msi/*.msi`

`scripts/build_desktop.ps1` wraps both with precondition checks.

> **`beforeBuildCommand` and its cwd.** Tauri runs the hook from whichever
> directory the CLI resolves as the frontend project — in this repo that can be the
> root, `docs-site/` or `src-tauri/`, depending on where the command was started.
> A plain `npm --prefix ../ui-next ...` therefore worked from one directory and
> failed from the others (`C:\AI\ui-next\package.json: ENOENT`). The hook is now a
> `cmd` conditional:
>
> ```
> if exist ui-next\package.json (npm --prefix ui-next run build:desktop)
> else (npm --prefix ..\ui-next run build:desktop)
> ```
>
> which resolves from all three. If you change the layout, re-check the hook from
> the root **and** from `src-tauri` — otherwise `cargo tauri build` silently ships
> an exe with a stale UI export.

## Desktop mode (Block 39)

The desktop build is the same app with `NEXT_PUBLIC_DESKTOP=1`. Everything that
needs a server is switched off at build time:

```powershell
npm --prefix ui-next run build:desktop   # or: cargo tauri build
```

`npm run build:desktop` runs `ui-next/scripts/build-desktop.mjs`, which sets the
flag and calls `next build`; `tauri.conf.json` uses it as `beforeBuildCommand`, so
`cargo tauri build` is never one flag away from building the wrong variant.

What the flag changes:

| Setting | Web | Desktop |
|---|---|---|
| `output` | (server) | `export` → `ui-next/out` |
| `images.unoptimized` | off | on (no image server) |
| `cacheComponents` / `partialPrefetching` | on | off |
| `@clerk/nextjs`, `@clerk/nextjs/server` | real package | local stubs |
| `src/proxy.ts` | `clerkMiddleware` | pass-through |
| `/report` | `?id=<jobId>` | `?id=<jobId>` |

Three of those were forced by the build, not by taste:

1. **PPR cannot be enabled in export mode.** `cacheComponents: true` switches on
   Partial Prerendering, which streams per request; the export then dies with
   `Invariant: PPR cannot be enabled in export mode`. Nothing in `ui-next/src`
   uses `use cache` / `cacheLife` / `cacheTag`, so turning it off loses nothing.
2. **Clerk's barrel registers server actions.** `@clerk/nextjs` exports
   `invalidateCacheAction` and `deleteKeylessAction`; a static export refuses to
   build any server action, so merely *importing* Clerk fails the export even when
   `ClerkProvider` is never rendered. Aliasing the package to
   `src/lib/clerk-desktop.tsx` / `clerk-server-desktop.ts` keeps it out of the
   module graph (and out of the binary — the exported HTML contains no Clerk
   script and no sign-in UI).
3. **Turbopack `resolveAlias` wants request strings**, not absolute paths: a
   `C:\...` value fails with `Module not found ... windows imports are not
   implemented yet`. The config therefore uses `./src/lib/...` for Turbopack and
   absolute paths for the webpack alias.

Rendering is gated too (`IS_DESKTOP` in `src/lib/desktop.ts`): `layout.tsx` skips
`ClerkProvider`, `Navbar` and the dashboard render a `Local` badge instead of the
sign-in slot, and the Clerk hooks live in web-only wrapper components so they can
never run without a provider.

`/report/[id]` became `/report?id=<jobId>` — a dynamic route without
`generateStaticParams()` cannot be exported. `JobCard` and the analyze redirect
build the query-string URL.

## Two constraints worth knowing

**Tauri 2 key names.** `devPath` / `distDir` are Tauri 1 names; Tauri 2 uses
`build.devUrl` / `build.frontendDist`. The installed CLI is 2.x, so the config
uses the v2 names and is validated against the v2 schema.

## Files

| Path | Purpose |
|---|---|
| `src-tauri/Cargo.toml` | Tauri 2 deps (`tauri`, `tauri-build`), release profile tuned for size |
| `src-tauri/build.rs` | `tauri_build::build()` |
| `src-tauri/tauri.conf.json` | window 1280×800 "Vishap", dev/build paths, bundle, icons |
| `src-tauri/capabilities/default.json` | grants `core:default` to the main window; no plugins |
| `src-tauri/src/main.rs` | app wiring: setup, close handler, exit handler |
| `src-tauri/src/backend.rs` | Python discovery, spawn, readiness probe, error card |
| `src-tauri/src/startup.rs` | panic hook, native error dialog, WebView2 profile repair |
| `src-tauri/icons/` | generated by `scripts/make_tauri_icons.py` |

## Troubleshooting: black window, app exits at once

Symptom: `vishap-desktop.exe` opens a dark window, then the process disappears;
F12 does nothing.

**What it actually is** (Block 40 diagnosis, from the Windows event log and the
binary's own stderr):

```text
Application Error 1000: vishap-desktop.exe, exception code 0xc0000409
Windows Error Reporting 1001: BEX64, P7=0x1b15f5, P9=0x7   <- __fastfail(7) = abort()

thread 'main' panicked at tauri-2.12.4/src/app.rs:1444:
Failed to setup app: runtime error: failed to create webview: WebView2 error:
  WindowsError(Error { code: HRESULT(0x800700AA), message: "The requested resource is in use." })
```

`0x800700AA` is `ERROR_BUSY`: the WebView2 user-data folder is held by an
`msedgewebview2.exe` left behind by an earlier crash. Creating the window can fail
before the webview exists, so the failure leaves a black frame; the error then
becomes a `panic!`, and a release build (`panic = "abort"`, GUI subsystem) dies
silently with `0xc0000409`. Each crash can leave another locked process behind —
that is why it never recovers on its own.

F12 cannot help there: the webview never exists. And DevTools in a packaged app
need the `devtools` Cargo feature (now enabled), not just `"devtools": true` in
the window config — without the feature Tauri disables WebView2's DevTools.

**What the app does now** (`src-tauri/src/startup.rs`):

1. a panic hook writes `<app data>\logs\startup-error.log`, drops a marker and
   shows a native message box before exiting, so a failed start is never silent;
2. on the next start, the marker makes it move the wedged profile aside to
   `webview2.broken` and let WebView2 create a clean one;
3. the marker is cleared once the webview actually exists, so it is only cleared
   on a healthy start;
4. the profile is **per-user and owned by the app**
   (`%LOCALAPPDATA%\com.vishap.desktop\webview2`, created in `main` before the
   window is built) — it is never the folder an elevated build left behind.

**Repair by hand** (if a live process still holds the folder):

```powershell
.\scripts\reset_desktop_profile.ps1 -Launch   # kills our msedgewebview2, moves profile aside
```

If the profile refuses to move, reboot and run the script again.

**Second bug found in the same run:** the backend was spawned with the system
`python`, which has no `fastapi` (`ModuleNotFoundError` in `logs\backend.log`).
`backend.rs` now prefers `<home>\.venv\Scripts\python.exe` before falling back to
`python` on `PATH`; `%VISHAP_PYTHON%` still wins over everything.

**A white window is a different bug: missing assets.** `tauri::generate_context!`
embeds `frontendDist` only when the `tauri/custom-protocol` feature is on.
`cargo tauri build` always passes it; a plain `cargo build --release` embeds
nothing, and the webview then renders an empty white page. Verify with:

```powershell
cd src-tauri
cargo test --release --features tauri/custom-protocol --bin vishap-desktop
```

`the_exported_frontend_is_embedded` checks `index.html`, the Next 16 RSC payload
(`index.txt`) and the `_next/static/chunks` entries; without the feature it skips
instead of failing. `scripts/build_desktop.ps1` uses `cargo tauri build`, so it
is not affected.

**Not the problem:** the `.txt` files in `ui-next/out` (RSC payloads) and asset
embedding. The `.exe` does contain the exported site — its binary holds the
`_next/static/chunks` paths, `index.html`, `report.html` and `404.html`, and the
Rust test above asserts it against the real embedded map.

## Troubleshooting: the UI says "Cannot reach the Vishap API"

**Symptom.** `curl http://127.0.0.1:5001/health` answers `{"status":"ok"}`, the
shell logs `[desktop] backend answered /health`, and the window still shows
"Cannot reach the Vishap API at http://127.0.0.1:5001".

**Cause: Private Network Access (Block 42).** The UI is served from
`http://tauri.localhost`, which Chromium treats as the *public* address space,
while `127.0.0.1` is *local*. Every request is therefore a PNA request: the
browser adds `Access-Control-Request-Private-Network: true` to the preflight and
blocks the fetch unless the answer carries `Access-Control-Allow-Private-Network`.

Starlette defaults `allow_private_network` to `False` and answers that preflight
with **400**, so the fetch throws and `api.ts` reports "Cannot reach" while the
backend is perfectly healthy. Verified by hand:

```text
# before
OPTIONS /health  Origin: http://tauri.localhost  ACRPN: true
-> HTTP/1.1 400 Bad Request          (no access-control-allow-private-network)

# after (src/main.py: allow_private_network=True)
-> HTTP/1.1 200 OK  access-control-allow-private-network: true
```

The fix lives in the Python middleware, not in the exe: restarting the app (or
`python -m src.main`) is enough, no rebuild required. `tests/test_cors_pna.py`
pins it, plus a guard that foreign origins are still refused.

Rust could reach the API the whole time because it speaks plain HTTP; only the
webview enforces the browser's network rules — which is why "the backend is up"
and "the UI cannot connect" were both true at once.

## Elevation, port ownership and startup order

**No elevation (v7).** Earlier builds shipped an `app.manifest` with
`requireAdministrator`, because the WebView2 profile had been created by an
elevated run and a standard user could not reuse it. That made every launch ask
for UAC, left `data/` owned by Administrators, and forced a `perMachine`
installer.

v7 removes it. The shipped manifest is `tauri-build`'s default (Common Controls
v6, **no** `requestedExecutionLevel`, i.e. `asInvoker`), the installer is
`currentUser`, and the underlying problem is solved in code:

- `startup::prepare_webview_profile()` creates
  `%LOCALAPPDATA%\com.vishap.desktop\webview2` before the window is built;
- the window is created with `WebviewWindowBuilder::data_directory(...)`, so
  WebView2 uses that per-user folder instead of one a previous elevated build (or
  a previous install directory) owns — which is why it can no longer be
  permission-denied or UAC-worthy;
- the old `%LOCALAPPDATA%\com.vishap.desktop\EBWebView` folder is left alone; it
  may be admin-owned and the current app never opens it.

There is no `VISHAP_SKIP_ADMIN_MANIFEST` escape hatch any more: the test harness
starts without elevation, so it is not needed.

**Port ownership.** `net::kill_port(5001)` runs before Python is spawned and
terminates whatever still listens there (a crashed run, or a manual
`python -m src.main`); the PIDs land in `logs\backend.log`. Without it uvicorn dies
with `[Errno 10048] error while attempting to bind on address ('0.0.0.0', 5001)`.

**Startup order.** Python is always spawned (the shell never assumes a running
backend is someone else's), the window is built hidden (`.visible(false)` in the
Rust builder) and revealed only once `GET /health` answers 200 on `127.0.0.1`, and
closing the window kills and reaps the child. The UI must use `127.0.0.1`, never
`localhost`: `localhost` may resolve to `::1` while uvicorn binds `0.0.0.0` (IPv4
only). `scripts/build-desktop.mjs` sets `NEXT_PUBLIC_API_URL` explicitly so a
developer's `.env.local` cannot regress the packaged app.

To find a port owner by hand:

```powershell
Get-NetTCPConnection -LocalPort 5001 -State Listen |
    Select-Object LocalAddress, LocalPort, OwningProcess
```

If the owner is Vishap itself, close its window instead of killing the process:
the shell stops Python on exit, and a killed process leaves the exe locked, which
then blocks `cargo tauri build`.

## Limitations

- `child.kill()` terminates `python.exe` only. Uvicorn is run in-process without
  `--reload`, so there is no child tree; enabling the reloader would leave
  grandchildren behind and needs a Windows Job Object.
- The Python sources are not bundled yet: a release build expects `src\main.py`
  next to the executable or `%VISHAP_HOME%`. Packaging them (PyInstaller or
  `bundle.resources` + `python\python.exe`) is a separate block.
- `csp` is `null`, because Clerk loads its widgets from `*.clerk.accounts.dev`
  and the backend lives on `127.0.0.1:5001`. Tighten it if auth is dropped.
