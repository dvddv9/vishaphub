//! Startup resilience: why the window was blank, and what the app does about it.
//!
//! ## The failure this module exists for
//!
//! Creating a WebView2 webview can fail at runtime on a user's machine — the
//! observed one is
//!
//! ```text
//! failed to create webview: WebView2 error: WindowsError(
//!     Error { code: HRESULT(0x800700AA), message: "The requested resource is in use." })
//! ```
//!
//! i.e. the WebView2 user-data folder is locked by a browser process left behind
//! by an earlier crash. Because release builds are GUI-subsystem and
//! `panic = "abort"`, the process then died with `0xc0000409` (WER event,
//! `__fastfail(7)`) without a word.
//!
//! ## Why there is no elevation any more
//!
//! The first workaround was a `requireAdministrator` manifest: an elevated app
//! could always reuse the profile. It also meant every launch asked for UAC, and
//! a profile created by an elevated process is writable only by administrators —
//! which is what broke the non-elevated run in the first place.
//!
//! The real fix is here: the app hands WebView2 its **own** per-user profile
//! directory (`%LOCALAPPDATA%\Vishap\webview2`), created by the app itself, so it
//! is never shared with an elevated process and never inherited from an install
//! directory. The shipped manifest is `asInvoker` (tauri-build's default).
//!
//! Three things are still needed, and this module is all of them:
//!
//! 1. a panic hook that writes the message to a log and shows a native dialog,
//!    so a failed start is never silent;
//! 2. a failure marker, so the next start can move the wedged profile aside and
//!    try a clean one instead of failing forever;
//! 3. the marker is cleared as soon as a start actually brings the webview up.

use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

/// Must match `identifier` in `tauri.conf.json` — the repair and the profile both
/// live under this directory. `tests/test_desktop_startup.py` keeps them in sync.
pub const IDENTIFIER: &str = "com.vishap.desktop";

/// WebView2 puts its user data here. Deliberately **not** inside the install
/// directory and **not** the default `EBWebView` name: those are the locations an
/// elevated run of an older build may already own.
const PROFILE_DIR: &str = "webview2";

/// Where the previous broken profile is kept (one copy; replaced on next repair).
const BROKEN_PROFILE_DIR: &str = "webview2.broken";

const MARKER: &str = "webview-startup-failed.txt";
const STARTUP_LOG: &str = "startup-error.log";

/// `%LOCALAPPDATA%\com.vishap.desktop`, the same directory Tauri uses for
/// `app_local_data_dir()`.
pub fn app_root() -> PathBuf {
    if let Some(base) = std::env::var_os("LOCALAPPDATA") {
        return PathBuf::from(base).join(IDENTIFIER);
    }
    std::env::temp_dir().join(IDENTIFIER)
}

/// A second, app-owned root. Written by *this* build at *this* integrity level,
/// so it never inherits the elevated profile of the 6.x line.
fn app_root_v2() -> PathBuf {
    match std::env::var_os("LOCALAPPDATA") {
        Some(base) => PathBuf::from(base).join("Vishap"),
        None => std::env::temp_dir().join("Vishap"),
    }
}

/// Can we actually create files here? `create_dir_all` returns `Ok` for an
/// existing directory we may not write into, so probe with a real file.
fn ensure_writable(dir: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(dir)?;
    let probe = dir.join(".writable");
    std::fs::write(&probe, b"1")?;
    let _ = std::fs::remove_file(&probe);
    Ok(())
}

/// Every place the WebView2 profile may live, most preferred first.
///
/// The order matters: a machine that ran the elevated 6.x build has a
/// high-integrity `%LOCALAPPDATA%\com.vishap.desktop`, which a standard user
/// cannot write into (ACCESS_DENIED). `%LOCALAPPDATA%\Vishap` is created by this
/// build, so it is writable whenever the user profile is.
fn profile_candidates() -> Vec<PathBuf> {
    let exe_dir = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(Path::to_path_buf));
    let mut candidates = vec![
        app_root_v2().join(PROFILE_DIR),
        app_root().join(PROFILE_DIR),
        std::env::temp_dir().join("Vishap").join(PROFILE_DIR),
    ];
    if let Some(dir) = exe_dir {
        candidates.push(dir.join(".webview2"));
    }
    candidates
}

/// The per-user WebView2 user-data folder (first candidate, for diagnostics).
pub fn webview_profile_path() -> PathBuf {
    app_root_v2().join(PROFILE_DIR)
}

/// Log directory: the first writable candidate, cached for the process.
fn log_dir() -> PathBuf {
    static CACHE: std::sync::OnceLock<PathBuf> = std::sync::OnceLock::new();
    CACHE
        .get_or_init(|| {
            for root in [app_root(), app_root_v2(), std::env::temp_dir().join("Vishap")] {
                let dir = root.join("logs");
                if ensure_writable(&dir).is_ok() {
                    return dir;
                }
            }
            app_root().join("logs")
        })
        .clone()
}

fn marker_path() -> PathBuf {
    log_dir().join(MARKER)
}

/// Create the profile directory before WebView2 is asked to use it.
///
/// Tries each candidate until one is writable; returns the first that worked, or
/// the preferred path when none did (WebView2 then reports the error itself and
/// the panic hook shows a dialog naming it).
pub fn prepare_webview_profile() -> PathBuf {
    for profile in profile_candidates() {
        match ensure_writable(&profile) {
            Ok(()) => {
                eprintln!("[startup] profile: {}", profile.display());
                return profile;
            }
            Err(err) => eprintln!(
                "[startup] cannot use the WebView2 profile {}: {err}",
                profile.display()
            ),
        }
    }

    let fallback = webview_profile_path();
    append_log(
        &log_dir().join(STARTUP_LOG),
        &format!(
            "[startup] no writable WebView2 profile location; last tried {}",
            fallback.display()
        ),
    );
    fallback
}

/// Write a one-line boot trace before anything else runs.
///
/// Support question number one is "did it even start?". A file with a PID and a
/// timestamp answers it without a debugger, and it survives a silent crash that
/// happens before the panic hook could report anything. Failures are echoed to
/// stderr as well: swallowing them is what made an "access denied" look like
/// "the app never started".
pub fn trace_boot() {
    let log = log_dir().join("boot.txt");
    let write = || -> std::io::Result<()> {
        std::fs::create_dir_all(log_dir())?;
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_millis())
            .unwrap_or(0);
        std::fs::write(&log, format!("pid={} ts_ms={stamp}\n", std::process::id()))
    };
    if let Err(err) = write() {
        eprintln!("[startup] cannot write {}: {err}", log.display());
    }
}

/// Install the panic hook. Must be the first thing `main` does.
pub fn install_panic_hook() {
    let previous = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        let message = info.to_string();

        // 1. Record it. The marker drives the recovery below.
        let _ = std::fs::create_dir_all(log_dir());
        let _ = std::fs::write(marker_path(), &message);
        append_log(&log_dir().join(STARTUP_LOG), &message);

        // 2. Keep the default hook's stderr output, then tell the user instead of
        //    vanishing.
        previous(info);
        message_box(
            "Vishap could not start",
            &format!(
                "The window could not be created.\n\n{message}\n\n\
                 This is almost always the WebView2 profile being locked by a \
                 leftover process from a previous crash. Vishap retries with a \
                 clean profile the next time you start it; if it keeps failing, \
                 reboot (or run scripts\\reset_desktop_profile.ps1) and try again.\n\n\
                 Log: {}",
                log_dir().join(STARTUP_LOG).display()
            ),
        );

        // 3. Skip the abort / Windows Error Reporting dump: unwinding a panic out
        //    of the win32 event loop is not something to rely on.
        std::process::exit(1);
    }));
}

/// If the previous start failed, the WebView2 profile is usually locked by a
/// browser process that never exited. Move it aside so WebView2 starts clean.
pub fn recover_profile_if_needed() {
    recover(&app_root());
}

/// The testable core of the repair: everything is relative to `root`, which is
/// the app data directory (`%LOCALAPPDATA%\com.vishap.desktop`).
///
/// Best effort by design: if the folder is genuinely held by a live process the
/// rename fails, the app fails again, and the dialog explains what to do.
fn recover(root: &Path) {
    let logs = root.join("logs");
    let marker = logs.join(MARKER);
    if !marker.is_file() {
        return;
    }

    let previous_error = std::fs::read_to_string(&marker).unwrap_or_default();
    append_log(
        &logs.join(STARTUP_LOG),
        &format!(
            "[startup] recovering from a failed start: {}",
            previous_error.trim()
        ),
    );

    let profile = root.join(PROFILE_DIR);
    if !profile.is_dir() {
        let _ = std::fs::remove_file(&marker);
        return;
    }

    let broken = root.join(BROKEN_PROFILE_DIR);
    let _ = std::fs::remove_dir_all(&broken);
    match std::fs::rename(&profile, &broken) {
        Ok(()) => append_log(
            &logs.join(STARTUP_LOG),
            &format!("[startup] moved the wedged profile to {}", broken.display()),
        ),
        Err(err) => append_log(
            &logs.join(STARTUP_LOG),
            &format!(
                "[startup] could not move the wedged profile ({}): {err}\n\
                 A leftover msedgewebview2.exe is probably still running. Reboot, \
                 or run scripts\\reset_desktop_profile.ps1.",
                profile.display()
            ),
        ),
    }
}

/// Called once the webview exists — reaching it means the start was healthy.
pub fn mark_started() {
    let marker = marker_path();
    if marker.is_file() {
        let _ = std::fs::remove_file(&marker);
    }
}

/// Report a fatal error to the log and to the user, then leave without a panic.
///
/// Used for errors Tauri would otherwise turn into an invisible `panic!` inside
/// a GUI-subsystem release build.
pub fn fatal(message: &str) -> ! {
    let log = log_dir().join(STARTUP_LOG);
    append_log(&log, message);
    message_box(
        "Vishap could not start",
        &format!("{message}\n\nLog: {}", log.display()),
    );
    std::process::exit(1)
}

fn append_log(path: &Path, line: &str) {
    use std::io::Write;

    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if let Ok(mut file) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
    {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0);
        let _ = writeln!(file, "[{stamp}] {line}");
    }
}

/// Native message box, so a GUI-subsystem binary can report a fatal error.
#[cfg(windows)]
fn message_box(title: &str, text: &str) {
    use std::ffi::OsStr;
    use std::os::windows::ffi::OsStrExt;

    const MB_OK: u32 = 0x0000_0000;
    const MB_ICONERROR: u32 = 0x0000_0010;
    const MB_SETFOREGROUND: u32 = 0x0001_0000;
    const MB_TOPMOST: u32 = 0x0004_0000;

    #[link(name = "user32")]
    extern "system" {
        fn MessageBoxW(
            hwnd: *mut core::ffi::c_void,
            text: *const u16,
            caption: *const u16,
            u_type: u32,
        ) -> i32;
    }

    fn wide(value: &str) -> Vec<u16> {
        OsStr::new(value)
            .encode_wide()
            .chain(std::iter::once(0))
            .collect()
    }

    let text = wide(text);
    let title = wide(title);
    // SAFETY: both buffers are NUL-terminated and outlive the call.
    unsafe {
        MessageBoxW(
            std::ptr::null_mut(),
            text.as_ptr(),
            title.as_ptr(),
            MB_OK | MB_ICONERROR | MB_SETFOREGROUND | MB_TOPMOST,
        );
    }
}

#[cfg(not(windows))]
fn message_box(title: &str, text: &str) {
    eprintln!("{title}: {text}");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn app_root_ends_with_the_bundle_identifier() {
        assert_eq!(app_root().file_name().unwrap(), IDENTIFIER);
    }

    #[test]
    fn marker_and_log_live_under_the_app_log_dir() {
        assert!(log_dir().ends_with("logs"));
        assert!(marker_path().ends_with("logs/webview-startup-failed.txt"));
        assert!(log_dir()
            .join(STARTUP_LOG)
            .ends_with("logs/startup-error.log"));
    }

    #[test]
    fn profile_paths_are_per_user_and_distinct_from_the_old_location() {
        let profile = webview_profile_path();
        assert!(profile.ends_with("webview2"));
        assert!(
            !profile.to_string_lossy().contains("EBWebView"),
            "the old elevated profile name must not be reused"
        );
        assert!(app_root()
            .join(BROKEN_PROFILE_DIR)
            .ends_with("webview2.broken"));
    }

    fn scratch_root(name: &str) -> PathBuf {
        // Not `std::env::temp_dir()`: sandboxed environments (the DSH harness,
        // some CI runners) deny writes there, and the fallback is the same one
        // `tests/conftest.py` uses on the Python side — a directory inside the
        // build tree, which is always writable.
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("target")
            .join("test-tmp")
            .join(format!("startup-{name}"));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("logs")).unwrap();
        root
    }

    fn write_marker(root: &Path) {
        std::fs::write(
            root.join("logs").join(MARKER),
            "Failed to setup app: failed to create webview: HRESULT(0x800700AA)",
        )
        .unwrap();
    }

    fn make_profile(root: &Path) {
        let profile = root.join(PROFILE_DIR);
        std::fs::create_dir_all(&profile).unwrap();
        std::fs::write(profile.join("Local State"), "{}").unwrap();
    }

    #[test]
    fn recover_moves_the_wedged_profile_aside_and_keeps_the_marker() {
        let root = scratch_root("recover");
        write_marker(&root);
        make_profile(&root);

        recover(&root);

        assert!(!root.join(PROFILE_DIR).exists(), "profile must be moved away");
        assert!(
            root.join(BROKEN_PROFILE_DIR).join("Local State").is_file(),
            "the broken profile is kept, not deleted"
        );
        assert!(
            root.join("logs").join(MARKER).is_file(),
            "the marker stays until a start actually brings the webview up"
        );

        let log = std::fs::read_to_string(root.join("logs").join(STARTUP_LOG)).unwrap();
        assert!(log.contains("recovering from a failed start"));
        assert!(log.contains("moved the wedged profile"));
    }

    #[test]
    fn recover_does_nothing_when_the_last_start_was_healthy() {
        let root = scratch_root("healthy");
        make_profile(&root);

        recover(&root);

        assert!(root.join(PROFILE_DIR).is_dir(), "a healthy profile is untouched");
        assert!(!root.join(BROKEN_PROFILE_DIR).exists());
    }

    #[test]
    fn recover_clears_a_stale_marker_when_there_is_no_profile() {
        let root = scratch_root("no-profile");
        write_marker(&root);

        recover(&root);

        assert!(!root.join("logs").join(MARKER).exists());
    }

    #[test]
    fn recover_replaces_the_previous_broken_copy() {
        let root = scratch_root("repeat");
        write_marker(&root);
        make_profile(&root);
        std::fs::create_dir_all(root.join(BROKEN_PROFILE_DIR)).unwrap();
        std::fs::write(root.join(BROKEN_PROFILE_DIR).join("old"), "stale").unwrap();

        recover(&root);

        assert!(
            !root.join(BROKEN_PROFILE_DIR).join("old").exists(),
            "only one broken copy is kept"
        );
        assert!(root.join(BROKEN_PROFILE_DIR).join("Local State").is_file());
    }

    #[test]
    fn append_log_creates_the_file_and_appends() {
        let root = scratch_root("log");
        let log = root.join("logs").join(STARTUP_LOG);
        append_log(&log, "first");
        append_log(&log, "second");

        let text = std::fs::read_to_string(&log).unwrap();
        assert!(text.contains("first"));
        assert!(text.contains("second"));
        assert_eq!(text.lines().count(), 2);
    }
}
