//! IPC bridge from the webview to the local API.
//!
//! The UI's `fetch` can be blocked by browser-level networking rules even though
//! the shell's own HTTP works (Block 42: the webview never even reached the
//! backend). `apiFetch` therefore falls back to this command, which performs the
//! request in Rust — same loopback address, no browser networking involved — and
//! returns the raw response for the UI to parse.

use std::time::Duration;

use serde::Serialize;

/// Raw API reply: the status line number and the undecoded body.
#[derive(Serialize)]
pub struct ApiReply {
    pub status: u16,
    pub body: String,
}

/// Perform one JSON request against `127.0.0.1:5001` and return the raw reply.
///
/// `body` is the already-serialised JSON payload (`None` for GET). `api_key` is
/// the `NEXT_PUBLIC_API_KEY` the UI would have sent as `X-API-Key`; it is passed
/// through untouched so auth behaves identically in both transport paths.
#[tauri::command]
pub async fn api_request(
    method: String,
    path: String,
    body: Option<String>,
    api_key: Option<String>,
) -> Result<ApiReply, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let (status, body) =
            crate::net::http_request(&method, &path, body.as_deref(), api_key.as_deref(), Duration::from_secs(30))?;
        Ok::<_, String>(ApiReply { status, body })
    })
    .await
    .map_err(|e| e.to_string())?
}
