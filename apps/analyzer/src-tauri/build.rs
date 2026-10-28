fn main() {
    // No custom application manifest.
    //
    // Earlier releases embedded an `app.manifest` with `requireAdministrator`
    // because the WebView2 profile had been created by an elevated process and a
    // non-elevated run could not reuse it (HRESULT 0x800700AA, "resource is in
    // use"). That made every launch ask for UAC — unacceptable for a desktop tool
    // — so the real fix lives in the code instead:
    //
    //   `src/startup.rs::prepare_webview_profile` gives WebView2 a per-user
    //   profile directory under `%LOCALAPPDATA%\Vishap\webview2`, created by the
    //   app itself, so it is never shared with an elevated process.
    //
    // `tauri-build`'s default manifest (asInvoker + Common Controls v6) is what
    // ships now. Do not reintroduce an elevation manifest here.
    tauri_build::try_build(tauri_build::Attributes::new()).expect("failed to run tauri-build");
}
