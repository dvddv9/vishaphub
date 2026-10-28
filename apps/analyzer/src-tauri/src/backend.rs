//! Supervisor for the local Python backend.
//!
//! Vishap's brain is a FastAPI process (`python -m src.main`, listening on
//! `127.0.0.1:5001`). The desktop shell owns that process: it starts it when the
//! window opens, waits until the port answers, and kills it when the window
//! closes so no orphan `python.exe` keeps the port (and the GPU-less CPU) busy.
//!
//! Everything here is deliberately dependency-free — `std::process::Command`,
//! `std::net::TcpStream`, `std::io` — so the only crate this file needs beyond
//! `tauri` is `serde_json` (for safely embedding an error string in JavaScript).

use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager, WebviewWindow};

/// Port the backend listens on. Mirrors `PORT = 5001` in `src/config.py`.
pub const BACKEND_PORT: u16 = 5001;

/// How long the backend gets to start answering before we call it a failure.
const READY_TIMEOUT: Duration = Duration::from_secs(45);
const READY_POLL: Duration = Duration::from_millis(250);

/// Environment variable that points at the project root, for installs where the
/// `src/` tree does not sit next to the executable (e.g. a dev checkout).
const HOME_ENV: &str = "VISHAP_HOME";

/// Environment variable that overrides the interpreter, e.g.
/// `C:\Python312\python.exe` or a virtualenv's `python.exe`.
const PYTHON_ENV: &str = "VISHAP_PYTHON";

pub struct Backend {
    child: Mutex<Option<Child>>,
    log_path: PathBuf,
    error: Option<String>,
}

impl Backend {
    /// Spawn the backend, or record why it could not be spawned.
    ///
    /// Never panics and never blocks: a failure is turned into a message that
    /// the caller paints into the window.
    pub fn start(app: &AppHandle) -> Self {
        let log_path = log_path(app);

        let home = match resolve_home(app) {
            Some(home) => home,
            None => {
                return Self {
                    child: Mutex::new(None),
                    error: Some(format!(
                        "Could not find the Vishap Python sources (a folder containing \
                         src\\main.py).\n\nSearched next to the executable and in the bundled \
                         resources.\nSet the {} environment variable to the project root to \
                         point at it explicitly.",
                        HOME_ENV
                    )),
                    log_path,
                }
            }
        };

        // A previous run — ours after a crash, or a developer's manual
        // `python -m src.main` — may still hold the port. Uvicorn would then die
        // with `[Errno 10048]` and the UI would have nothing to talk to.
        let killed = crate::net::kill_port(BACKEND_PORT);
        if !killed.is_empty() {
            log_line(
                &log_path,
                &format!("port {BACKEND_PORT} was busy; terminated pids {killed:?}"),
            );
        }

        let mut attempts: Vec<String> = Vec::new();
        for (program, args) in python_candidates(&home, python_override()) {
            let shown = format!("{} {}", program, args.join(" "));
            match spawn(&program, &args, &home, &log_path) {
                Ok(child) => {
                    log_line(
                        &log_path,
                        &format!(
                            "started `{}` (pid {}) in {}",
                            shown,
                            child.id(),
                            home.display()
                        ),
                    );
                    return Self {
                        child: Mutex::new(Some(child)),
                        error: None,
                        log_path,
                    };
                }
                Err(err) => attempts.push(format!("{shown}\n    -> {err}")),
            }
        }

        Self {
            child: Mutex::new(None),
            error: Some(format!(
                "The Python interpreter could not be started from {}.\n\nTried:\n{}\n\nInstall \
                 Python 3.11+ and make sure it is on PATH, or set {} to the full path of \
                 python.exe.\n\nLog: {}",
                home.display(),
                attempts.join("\n\n"),
                PYTHON_ENV,
                log_path.display()
            )),
            log_path,
        }
    }

    /// The message to show in the window, if startup failed.
    pub fn startup_error(&self) -> Option<String> {
        self.error.clone()
    }

    pub fn is_running(&self) -> bool {
        matches!(self.child.lock(), Ok(guard) if guard.is_some())
    }

    /// Has the child already died? A crashed backend must be reported instead of
    /// leaving the UI waiting for a port that will never open.
    fn has_exited(&self) -> bool {
        let Ok(mut guard) = self.child.lock() else {
            return true;
        };
        match guard.as_mut() {
            None => true,
            Some(child) => !matches!(child.try_wait(), Ok(None)),
        }
    }

    /// Kill the backend and reap it. Idempotent, safe to call twice (close
    /// handler, then process exit).
    pub fn stop(&self) {
        let Ok(mut guard) = self.child.lock() else {
            return;
        };
        if let Some(mut child) = guard.take() {
            log_line(&self.log_path, &format!("stopping pid {}", child.id()));
            let _ = child.kill();
            let _ = child.wait();
        }
    }

    /// Last few lines of the backend log, for the error card.
    fn log_tail(&self) -> String {
        read_tail(&self.log_path, 40)
    }
}

/// Wait until `GET /health` answers, the child dies, or we time out, then reveal
/// the window. Runs on its own thread.
///
/// The window is created hidden (`visible: false` in `tauri.conf.json`), so the
/// user never sees a UI that is already showing "Cannot reach the API": the first
/// paint happens after the backend is genuinely serving.
pub fn probe_readiness(app: AppHandle) {
    std::thread::spawn(move || {
        let deadline = Instant::now() + READY_TIMEOUT;
        while Instant::now() < deadline {
            if crate::net::http_health_ok(BACKEND_PORT, Duration::from_millis(900)) {
                log_line(&log_path(&app), "backend answered /health");
                reveal(&app);
                probe_webview_origin(app.clone());
                return;
            }
            if let Some(state) = app.try_state::<Backend>() {
                if state.has_exited() {
                    let message = format!(
                        "The Python backend exited before it started answering on \
                         http://127.0.0.1:{BACKEND_PORT}.\n\nLast log lines:\n{}",
                        state.log_tail()
                    );
                    report(&app, &message);
                    reveal(&app);
                    return;
                }
            }
            std::thread::sleep(READY_POLL);
        }

        let tail = app
            .try_state::<Backend>()
            .map(|state| state.log_tail())
            .unwrap_or_default();
        report(
            &app,
            &format!(
                "The Python backend did not answer on http://127.0.0.1:{BACKEND_PORT} within {} \
                 seconds.\n\nLast log lines:\n{}",
                READY_TIMEOUT.as_secs(),
                tail
            ),
        );
        reveal(&app);
    });
}

/// Show the main window. Safe to call more than once and from any thread.
pub fn reveal(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

/// Ask the webview itself to fetch `/health`.
///
/// The backend can be healthy while the *browser* still refuses the request —
/// a CORS mismatch (the page origin is `http://tauri.localhost` on Windows) or a
/// blocked loopback connection both look identical from Rust: the port answers,
/// the UI says "Cannot reach". This runs the same fetch the UI runs, from the
/// `127.0.0.1` the UI uses, and only speaks up when it fails.
pub fn probe_webview_origin(app: AppHandle) {
    std::thread::spawn(move || {
        // Let the page finish loading before asking it to run a request.
        std::thread::sleep(Duration::from_secs(4));
        let Some(window) = app.get_webview_window("main") else {
            return;
        };
        let url = format!("http://127.0.0.1:{BACKEND_PORT}/health");
        let script = probe_script(&url);
        if let Err(err) = window.eval(&script) {
            eprintln!("vishap: could not run the UI fetch probe: {err}");
        }
    });
}

/// The probe body. Kept separate so a test can assert the URL is loopback-IPv4.
fn probe_script(url: &str) -> String {
    let literal = serde_json::to_string(url).unwrap_or_else(|_| "\"\"".to_string());
    format!(
        r#"(async () => {{
  const url = {literal};
  try {{
    const response = await fetch(url, {{ cache: "no-store" }});
    if (!response.ok) {{ throw new Error("HTTP " + response.status); }}
  }} catch (error) {{
    const detail = [
      "The window is loaded from " + location.origin + ".",
      "The API answered on 127.0.0.1 from Rust, but this webview cannot reach " + url + ".",
      "Reported: " + String(error),
    ].join("\n");
    console.error("Vishap: UI cannot reach the backend.", detail);
    document.title = "Vishap - API unreachable";
  }}
}})();"#
    )
}

/// Paint a blocking error card over the window.
///
/// Done with injected JavaScript instead of a separate window or a dialog plugin:
/// no extra crate, and it works with both the dev server and the bundled assets.
/// The snippet waits for `document.body` because it can run before first paint.
pub fn show_error(window: &WebviewWindow, message: &str) {
    let script = overlay_script(message);
    if let Err(err) = window.eval(&script) {
        eprintln!("vishap: failed to show backend error overlay: {err}");
    }
}

fn report(app: &AppHandle, message: &str) {
    match app.get_webview_window("main") {
        Some(window) => show_error(&window, message),
        None => eprintln!("vishap: no main window to report: {message}"),
    }
}

/// The JS that renders the error card. Message is embedded as a JSON string
/// literal, and everything is inserted with `textContent`, so a path containing
/// quotes or angle brackets cannot break out of the string or the DOM.
fn overlay_script(message: &str) -> String {
    let literal = serde_json::to_string(message).unwrap_or_else(|_| "\"\"".to_string());
    format!(
        r#"(function () {{
  var message = {literal};
  function paint() {{
    if (!document.body) {{ return setTimeout(paint, 100); }}
    var existing = document.getElementById("vishap-backend-error");
    if (existing) {{ existing.parentNode.removeChild(existing); }}
    var wrap = document.createElement("div");
    wrap.id = "vishap-backend-error";
    wrap.setAttribute("role", "alertdialog");
    wrap.style.cssText = "position:fixed;inset:0;z-index:2147483647;display:flex;align-items:center;justify-content:center;background:rgba(8,12,22,.94);padding:40px;font:15px/1.65 system-ui,Segoe UI,sans-serif;color:#e8f0fa;";
    var card = document.createElement("div");
    card.style.cssText = "max-width:660px;max-height:80vh;overflow:auto;background:#111a2b;border:1px solid #24344d;border-radius:14px;padding:28px 32px;box-shadow:0 24px 64px rgba(0,0,0,.45);";
    var title = document.createElement("h1");
    title.textContent = "Python backend is not running";
    title.style.cssText = "margin:0 0 12px;font-size:19px;color:#f87171;";
    var lead = document.createElement("p");
    lead.textContent = "Vishap runs its FastAPI backend as a local Python process, and that process could not be started.";
    lead.style.cssText = "margin:0 0 16px;color:#c3d2e6;";
    var pre = document.createElement("pre");
    pre.textContent = message;
    pre.style.cssText = "white-space:pre-wrap;word-break:break-word;background:#0b1020;border:1px solid #1f2c42;border-radius:8px;padding:12px;margin:0 0 16px;font:12.5px/1.55 Consolas,ui-monospace,monospace;color:#fca5a5;";
    var hint = document.createElement("p");
    hint.textContent = "Install Python 3.11+ so that `python` is on PATH, then restart Vishap. To use a specific interpreter, set VISHAP_PYTHON to its full path.";
    hint.style.cssText = "margin:0;color:#8fa3bd;font-size:13.5px;";
    card.appendChild(title);
    card.appendChild(lead);
    card.appendChild(pre);
    card.appendChild(hint);
    wrap.appendChild(card);
    document.body.appendChild(wrap);
  }}
  paint();
}})();"#
    )
}

// ---------------------------------------------------------------------------
// Process plumbing
// ---------------------------------------------------------------------------

/// Interpreter override from the environment. An empty value is treated as unset
/// (a launcher that exports `VISHAP_PYTHON=` should not break startup).
fn python_override() -> Option<PathBuf> {
    let raw = std::env::var_os(PYTHON_ENV)?;
    let path = PathBuf::from(raw);
    if path.as_os_str().is_empty() {
        return None;
    }
    Some(path)
}

/// Commands to try, in order: explicit override, interpreter bundled with the
/// installer, the project virtualenv, `python` on PATH, then the Windows
/// launcher (`py -3`).
fn python_candidates(home: &Path, over: Option<PathBuf>) -> Vec<(String, Vec<String>)> {
    let module = |exe: &Path| {
        (
            exe.display().to_string(),
            ["-m".to_string(), "src.main".to_string()].to_vec(),
        )
    };
    let mut out = Vec::new();

    if let Some(exe) = over {
        out.push(module(&exe));
    }
    let bundled = home.join("python").join("python.exe");
    if bundled.is_file() {
        out.push(module(&bundled));
    }
    // The project virtualenv comes next: a system `python` usually has none of
    // the dependencies, and starting it only yields
    // `ModuleNotFoundError: No module named 'fastapi'` in the backend log.
    for venv in [".venv", "venv"] {
        let candidate = venv_python(&home.join(venv));
        if candidate.is_file() {
            out.push(module(&candidate));
            break;
        }
    }
    out.push((
        "python".to_string(),
        ["-m".to_string(), "src.main".to_string()].to_vec(),
    ));
    out.push((
        "py".to_string(),
        ["-3".to_string(), "-m".to_string(), "src.main".to_string()].to_vec(),
    ));
    out
}

/// `<venv>\Scripts\python.exe` on Windows, `<venv>/bin/python` elsewhere.
fn venv_python(venv_root: &Path) -> PathBuf {
    #[cfg(windows)]
    {
        venv_root.join("Scripts").join("python.exe")
    }
    #[cfg(not(windows))]
    {
        venv_root.join("bin").join("python")
    }
}

fn spawn(program: &str, args: &[String], cwd: &Path, log: &Path) -> std::io::Result<Child> {
    if let Some(parent) = log.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let log_file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(log)?;
    let err_file = log_file.try_clone()?;

    let mut cmd = Command::new(program);
    cmd.args(args)
        .current_dir(cwd)
        .stdin(Stdio::null())
        .stdout(Stdio::from(log_file))
        .stderr(Stdio::from(err_file))
        // Unbuffered + UTF-8, otherwise the log stays empty and Cyrillic output
        // dies on the cp1251 console encoding.
        .env("PYTHONUNBUFFERED", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .env("PYTHONUTF8", "1");

    // The desktop app is a single-user local tool: it runs the in-memory job
    // store, never Postgres. A developer's `.env` sets JOB_STORE=postgres for the
    // hosted server; `load_dotenv()` does not override process env, so setting it
    // here wins. Mirror `tests/conftest.py::_configure_store`, including the
    // `VISHAP_TEST_POSTGRES` opt-out for a live-database desktop run.
    if std::env::var_os("VISHAP_TEST_POSTGRES").is_none() {
        cmd.env("JOB_STORE", "memory").env("VISHAP_TENANT_KEYS", "false");
    }

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        // CREATE_NO_WINDOW: a packaged GUI app must not flash a console.
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    cmd.spawn()
}

/// Where the Python project root lives.
fn resolve_home(app: &AppHandle) -> Option<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();

    if let Some(raw) = std::env::var_os(HOME_ENV) {
        candidates.push(PathBuf::from(raw));
    }
    if let Some(dev_root) = Path::new(env!("CARGO_MANIFEST_DIR")).parent() {
        candidates.push(dev_root.to_path_buf());
    }
    if let Ok(resources) = app.path().resource_dir() {
        candidates.push(resources.join("vishap"));
        candidates.push(resources);
    }
    if let Ok(exe) = std::env::current_exe() {
        candidates.extend(ancestors_of(&exe, 4));
    }

    find_home(candidates)
}

/// First candidate that actually looks like the project root.
fn find_home(candidates: impl IntoIterator<Item = PathBuf>) -> Option<PathBuf> {
    candidates
        .into_iter()
        .find(|dir| dir.join("src").join("main.py").is_file())
}

/// The directories above `exe` (its own folder first). Covers
/// `src-tauri/target/release/vishap-desktop.exe` -> repo root.
fn ancestors_of(exe: &Path, depth: usize) -> Vec<PathBuf> {
    let mut out = Vec::new();
    let mut current = exe.parent();
    for _ in 0..depth {
        match current {
            Some(dir) => {
                out.push(dir.to_path_buf());
                current = dir.parent();
            }
            None => break,
        }
    }
    out
}

fn log_path(app: &AppHandle) -> PathBuf {
    let dir = app
        .path()
        .app_log_dir()
        .unwrap_or_else(|_| std::env::temp_dir());
    dir.join("backend.log")
}

fn log_line(path: &Path, line: &str) {
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if let Ok(mut file) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
    {
        use std::io::Write;
        let _ = writeln!(file, "[desktop] {line}");
    }
}

/// Last `max_lines` lines of a file, without loading a multi-megabyte log.
fn read_tail(path: &Path, max_lines: usize) -> String {
    const WINDOW: u64 = 8 * 1024;
    let Ok(mut file) = std::fs::File::open(path) else {
        return String::from("(no backend log yet)");
    };
    let len = file.metadata().map(|m| m.len()).unwrap_or(0);
    let start = len.saturating_sub(WINDOW);
    if file.seek(SeekFrom::Start(start)).is_err() {
        return String::from("(backend log unreadable)");
    }
    let mut buf = Vec::new();
    if file.read_to_end(&mut buf).is_err() {
        return String::from("(backend log unreadable)");
    }
    let text = String::from_utf8_lossy(&buf);
    let lines: Vec<&str> = text.lines().collect();
    let from = lines.len().saturating_sub(max_lines);
    let tail = lines[from..].join("\n");
    if tail.trim().is_empty() {
        String::from("(backend log is empty)")
    } else {
        tail
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp_dir(name: &str) -> PathBuf {
        // `std::env::temp_dir()` is denied in sandboxed environments; the build
        // tree is always writable (same fallback as tests/conftest.py).
        let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("target")
            .join("test-tmp")
            .join(format!("backend-{name}"));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn fake_project(name: &str) -> PathBuf {
        let dir = tmp_dir(name);
        std::fs::create_dir_all(dir.join("src")).unwrap();
        std::fs::write(dir.join("src").join("main.py"), "# fake").unwrap();
        dir
    }

    #[test]
    fn find_home_skips_directories_without_src_main_py() {
        let bogus = tmp_dir("bogus");
        let real = fake_project("real");
        let found = find_home(vec![bogus, real.clone()]);
        assert_eq!(found, Some(real));
    }

    #[test]
    fn find_home_returns_none_when_nothing_matches() {
        let bogus = tmp_dir("empty");
        assert_eq!(find_home(vec![bogus]), None);
    }

    #[test]
    fn python_candidates_start_with_override_then_fall_back_to_path() {
        let home = fake_project("candidates");
        let exe = home.join("python").join("python.exe");
        std::fs::create_dir_all(exe.parent().unwrap()).unwrap();
        std::fs::write(&exe, "").unwrap();

        let found = python_candidates(&home, Some(PathBuf::from("C:\\Py312\\python.exe")));
        let programs: Vec<&str> = found.iter().map(|(p, _)| p.as_str()).collect();

        assert_eq!(
            programs,
            vec![
                "C:\\Py312\\python.exe",
                exe.to_str().unwrap(),
                "python",
                "py"
            ]
        );
        // Every candidate runs the module, and only `py` needs a version flag.
        assert_eq!(found[0].1, vec!["-m".to_string(), "src.main".to_string()]);
        assert_eq!(
            found[3].1,
            vec!["-3".to_string(), "-m".to_string(), "src.main".to_string()]
        );
    }

    #[test]
    fn python_candidates_without_bundled_interpreter() {
        let home = fake_project("no-bundled");
        let found = python_candidates(&home, None);
        let programs: Vec<&str> = found.iter().map(|(p, _)| p.as_str()).collect();
        assert_eq!(programs, vec!["python", "py"]);
    }

    /// A packaged release run against the project root must pick `.venv`: the
    /// system interpreter has no fastapi, which is what a blank backend looked
    /// like in the field (see `logs/backend.log`).
    #[test]
    fn python_candidates_prefer_the_project_virtualenv() {
        let home = fake_project("venv");
        let exe = venv_python(&home.join(".venv"));
        std::fs::create_dir_all(exe.parent().unwrap()).unwrap();
        std::fs::write(&exe, "").unwrap();

        let found = python_candidates(&home, None);
        let programs: Vec<&str> = found.iter().map(|(p, _)| p.as_str()).collect();

        assert_eq!(programs, vec![exe.to_str().unwrap(), "python", "py"]);
        assert_eq!(found[0].1, vec!["-m".to_string(), "src.main".to_string()]);
    }

    #[test]
    fn python_candidates_fall_back_to_venv_dir_name() {
        let home = fake_project("venv-plain");
        let exe = venv_python(&home.join("venv"));
        std::fs::create_dir_all(exe.parent().unwrap()).unwrap();
        std::fs::write(&exe, "").unwrap();

        let found = python_candidates(&home, None);
        assert_eq!(found[0].0, exe.to_str().unwrap());
    }

    #[test]
    fn ancestors_of_walks_up_from_the_executable() {
        let exe = PathBuf::from("C:\\repo\\src-tauri\\target\\release\\vishap-desktop.exe");
        let up = ancestors_of(&exe, 3);
        assert_eq!(
            up,
            vec![
                PathBuf::from("C:\\repo\\src-tauri\\target\\release"),
                PathBuf::from("C:\\repo\\src-tauri\\target"),
                PathBuf::from("C:\\repo\\src-tauri"),
            ]
        );
    }

    #[test]
    fn overlay_script_escapes_hostile_messages() {
        let script = overlay_script("bad \"path\" </script><script>alert(1)</script>\nnext");
        assert!(script.contains(r#""bad \"path\" </script><script>alert(1)</script>\nnext""#));
        assert!(script.contains("textContent"));
        // The payload must exist exactly once, inside the JSON literal.
        assert_eq!(script.matches("alert(1)").count(), 1);
    }

    #[test]
    fn read_tail_returns_placeholder_for_missing_log() {
        let missing = tmp_dir("tail").join("nope.log");
        assert_eq!(read_tail(&missing, 10), "(no backend log yet)");
    }

    #[test]
    fn read_tail_keeps_only_the_last_lines() {
        let dir = tmp_dir("tail-lines");
        let log = dir.join("backend.log");
        std::fs::write(&log, "one\ntwo\nthree\nfour\n").unwrap();
        assert_eq!(read_tail(&log, 2), "three\nfour");
    }
}
