//! Vishap desktop shell.
//!
//! Wraps the Next.js UI in a native window and owns the local Python backend:
//!
//! * the window points at `http://localhost:3000` in dev (`cargo tauri dev`,
//!   where `beforeDevCommand` starts Next) and at the exported static site in
//!   release (`cargo tauri build`);
//! * `Backend::start` launches `python -m src.main` and waits for it to answer;
//! * closing the window kills the backend, so no orphan process keeps port 5001.

// Release builds are GUI-only: without this a console window follows the app.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;
mod ipc;
mod net;
mod startup;

use tauri::{Manager, RunEvent, WindowEvent};

use backend::Backend;

fn main() {
    // Answer "did it even start?" before anything can fail.
    startup::trace_boot();
    // First, before anything can fail: make a failed start explain itself.
    startup::install_panic_hook();
    // If the previous start failed, the WebView2 profile is usually wedged.
    startup::recover_profile_if_needed();
    // Give WebView2 its own per-user profile: this is what replaced the
    // `requireAdministrator` manifest (see src/startup.rs).
    let profile = startup::prepare_webview_profile();

    let built = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![ipc::api_request])
        .setup(move |app| {
            // The window is built here rather than from `tauri.conf.json`: only
            // the Rust builder takes `data_directory`, and a per-user profile is
            // what keeps the app out of UAC. An error propagates as `Err`, which
            // Tauri turns into a panic that our hook reports.
            tauri::WebviewWindowBuilder::new(
                app,
                "main",
                tauri::WebviewUrl::App("index.html".into()),
            )
            .title("Vishap")
            .inner_size(1280.0, 800.0)
            .min_inner_size(900.0, 600.0)
            .center()
            .visible(false)
            .devtools(true)
            .data_directory(profile.clone())
            .build()?;

            // Reaching this point means the webview exists: the start was healthy.
            startup::mark_started();

            let handle = app.handle().clone();
            let backend = Backend::start(&handle);

            // A failed spawn must be visible, not a silently blank window (the
            // window starts hidden, so it has to be revealed explicitly).
            if let Some(message) = backend.startup_error() {
                if let Some(window) = app.get_webview_window("main") {
                    backend::show_error(&window, &message);
                }
                backend::reveal(&handle);
            }

            let running = backend.is_running();
            app.manage(backend);

            // The window stays hidden until `GET /health` answers, so the UI never
            // loads into a "Cannot reach the API" state.
            if running {
                backend::probe_readiness(handle);
            }

            Ok(())
        })
        // Close button: stop Python first so it cannot outlive the window.
        .on_window_event(|window, event| {
            if matches!(event, WindowEvent::CloseRequested { .. }) && window.label() == "main" {
                if let Some(state) = window.try_state::<Backend>() {
                    state.stop();
                }
            }
        })
        .build(tauri::generate_context!());

    let app = match built {
        Ok(app) => app,
        // A GUI-subsystem binary has nowhere to print a panic: report it and stop.
        Err(err) => startup::fatal(&format!("Could not create the Vishap window: {err}")),
    };

    app.run(|app_handle, event| {
        // Belt and braces: also covers quit paths that never raise CloseRequested
        // (tray quit, Ctrl-C in `cargo tauri dev`, session shutdown).
        if let RunEvent::Exit = event {
            if let Some(state) = app_handle.try_state::<Backend>() {
                state.stop();
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use tauri::utils::assets::AssetKey;

    /// The window shows a blank page if the exported site is not embedded, so pin
    /// the entry points a Next.js static export needs. `generate_context!` embeds
    /// `frontendDist` (`ui-next/out`) only when the `tauri/custom-protocol`
    /// feature is on — which `cargo tauri build` passes. A plain
    /// `cargo build --release` embeds nothing and renders a white window, so skip
    /// there instead of failing.
    #[test]
    fn the_exported_frontend_is_embedded() {
        let context: tauri::Context<tauri::Wry> = tauri::generate_context!();
        let assets = context.assets.as_ref();

        if assets.iter().next().is_none() {
            eprintln!(
                "skipping: this build has no embedded frontend; build with \
                 `cargo tauri build` or `--features tauri/custom-protocol`"
            );
            return;
        }

        let index = assets
            .get(&AssetKey::from(String::from("index.html")))
            .expect("index.html must be embedded - was ui-next/out missing at build time?");
        let html = String::from_utf8_lossy(&index);
        assert!(html.contains("<html"), "index.html does not look like HTML");
        assert!(
            html.contains("Vishap"),
            "index.html is not the Vishap UI"
        );

        // Next 16 writes RSC payloads next to each page; they belong in the bundle.
        assert!(
            assets
                .get(&AssetKey::from(String::from("index.txt")))
                .is_some(),
            "RSC payload index.txt must be embedded"
        );

        // The hashed chunks are what `/_next/static/...` requests resolve to.
        let chunk = assets
            .iter()
            .any(|(key, _contents)| key.contains("_next/static/chunks/"));
        assert!(chunk, "no _next/static chunks embedded");
    }
}
