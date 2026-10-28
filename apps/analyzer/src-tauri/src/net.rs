//! Loopback helpers for the backend lifecycle.
//!
//! Two questions the shell needs answered before it trusts the Python process:
//!
//! * **Who holds the port?** A previous Vishap run that was killed hard, or a
//!   developer's manual `python -m src.main`, keeps 5001 busy. Uvicorn then dies
//!   with `[Errno 10048] error while attempting to bind on address ('0.0.0.0', 5001)`
//!   and the UI has nothing to talk to. `kill_port` clears the owner first.
//! * **Is it actually answering `/health`?** An open TCP port only means a socket
//!   exists; until uvicorn has finished starting up it will accept nothing. The
//!   window is only revealed once `/health` returns 200.
//!
//! Both are dependency-free: one Win32 table lookup, one hand-rolled HTTP request.

use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::time::Duration;

/// Port the FastAPI backend listens on. Mirrors `PORT = 5001` in `src/config.py`.
pub const BACKEND_PORT: u16 = 5001;

/// PIDs listening on `port` (IPv4, loopback included).
///
/// Returns an empty list on non-Windows targets: the desktop shell only ships for
/// Windows today, and pretending to know elsewhere would be a lie.
#[cfg(windows)]
pub fn listening_pids(port: u16) -> Vec<u32> {
    let mut size: u32 = 0;
    // First call sizes the buffer; ERROR_INSUFFICIENT_BUFFER (122) is expected.
    let probe = unsafe {
        win::GetExtendedTcpTable(
            std::ptr::null_mut(),
            &mut size,
            0,
            win::AF_INET,
            win::TCP_TABLE_OWNER_PID_LISTENER,
            0,
        )
    };
    if probe != win::ERROR_INSUFFICIENT_BUFFER || size == 0 {
        return Vec::new();
    }

    // Back the buffer with `u32` so the row structs are properly aligned.
    let mut buffer: Vec<u32> = vec![0; (size as usize / 4) + 1];
    let capacity = (buffer.len() * 4) as u32;
    let mut written = capacity;
    let ret = unsafe {
        win::GetExtendedTcpTable(
            buffer.as_mut_ptr() as *mut std::ffi::c_void,
            &mut written,
            0,
            win::AF_INET,
            win::TCP_TABLE_OWNER_PID_LISTENER,
            0,
        )
    };
    if ret != 0 {
        return Vec::new();
    }

    let bytes = unsafe {
        std::slice::from_raw_parts(buffer.as_ptr() as *const u8, capacity as usize)
    };
    let count = u32::from_ne_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]) as usize;
    let row = std::mem::size_of::<win::MibTcpRowOwnerPid>();

    let mut pids = Vec::new();
    for index in 0..count {
        let offset = 4 + index * row;
        if offset + row > bytes.len() {
            break;
        }
        let entry: &win::MibTcpRowOwnerPid =
            unsafe { &*(bytes.as_ptr().add(offset) as *const win::MibTcpRowOwnerPid) };
        // dwLocalPort holds the port in network byte order in its low two bytes.
        let bound = ((entry.local_port & 0xFF) << 8) | ((entry.local_port >> 8) & 0xFF);
        if bound as u16 == port && !pids.contains(&entry.owning_pid) {
            pids.push(entry.owning_pid);
        }
    }
    pids
}

#[cfg(not(windows))]
pub fn listening_pids(_port: u16) -> Vec<u32> {
    Vec::new()
}

/// Kill every process listening on `port`, except this one.
///
/// Returns the PIDs it terminated, so the caller can log what it took down.
#[cfg(windows)]
pub fn kill_port(port: u16) -> Vec<u32> {
    let own = std::process::id();
    let mut killed = Vec::new();
    for pid in listening_pids(port) {
        if pid == own || pid == 0 {
            continue;
        }
        let handle = unsafe { win::OpenProcess(win::PROCESS_TERMINATE, 0, pid) };
        if handle.is_null() {
            continue;
        }
        let ok = unsafe { win::TerminateProcess(handle, 1) };
        unsafe { win::CloseHandle(handle) };
        if ok != 0 {
            killed.push(pid);
        }
    }
    killed
}

#[cfg(not(windows))]
pub fn kill_port(_port: u16) -> Vec<u32> {
    Vec::new()
}

/// `true` when `GET /health` on the loopback interface answers 200.
///
/// Deliberately tiny: uvicorn answers this route before any pipeline work, and
/// the whole point is to ask it over real HTTP from the same address the webview
/// will use (`127.0.0.1`, never `localhost` — that may resolve to `::1`, which
/// the backend does not bind).
pub fn http_health_ok(port: u16, timeout: Duration) -> bool {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let Ok(mut stream) = TcpStream::connect_timeout(&addr, timeout) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(timeout));
    let _ = stream.set_write_timeout(Some(timeout));

    let request =
        format!("GET /health HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n");
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }

    let mut buf = [0u8; 64];
    let Ok(read) = stream.read(&mut buf) else {
        return false;
    };
    let status = String::from_utf8_lossy(&buf[..read]);
    status.starts_with("HTTP/1.1 200") || status.starts_with("HTTP/1.0 200")
}

/// One JSON request to the loopback API, and the raw response.
///
/// The webview's own `fetch` can be blocked by browser-level networking rules
/// (Private Network Access, a proxy, an AV shim) even though plain HTTP works;
/// this is the escape hatch: the shell performs the request in Rust and hands the
/// webview the result over IPC, where no browser networking is involved.
pub fn http_request(
    method: &str,
    path: &str,
    body: Option<&str>,
    api_key: Option<&str>,
    timeout: Duration,
) -> Result<(u16, String), String> {
    http_request_to(BACKEND_PORT, method, path, body, api_key, timeout)
}

fn http_request_to(
    port: u16,
    method: &str,
    path: &str,
    body: Option<&str>,
    api_key: Option<&str>,
    timeout: Duration,
) -> Result<(u16, String), String> {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let mut stream = TcpStream::connect_timeout(&addr, timeout).map_err(|e| e.to_string())?;
    let _ = stream.set_read_timeout(Some(timeout));
    let _ = stream.set_write_timeout(Some(timeout));

    let body = body.unwrap_or("");
    let mut head = format!(
        "{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nAccept: application/json\r\nConnection: close\r\n"
    );
    if !body.is_empty() {
        head.push_str("Content-Type: application/json\r\n");
        head.push_str(&format!("Content-Length: {}\r\n", body.len()));
    }
    if let Some(key) = api_key.filter(|k| !k.is_empty()) {
        head.push_str(&format!("X-API-Key: {key}\r\n"));
    }
    head.push_str("\r\n");

    // One write: writing headers and body separately lets a tiny loopback peer
    // respond (and close) in between, which surfaces as RST/ECONNRESET on the
    // second write.
    let mut request = head.into_bytes();
    request.extend_from_slice(body.as_bytes());
    stream
        .write_all(&request)
        .map_err(|e| format!("write request: {e}"))?;

    let mut raw = Vec::new();
    stream.read_to_end(&mut raw).map_err(|e| e.to_string())?;
    parse_http_response(&raw)
}

/// Split a raw HTTP response into `(status_code, body)`.
fn parse_http_response(raw: &[u8]) -> Result<(u16, String), String> {
    let text = String::from_utf8_lossy(raw);
    let (head, body) = text
        .split_once("\r\n\r\n")
        .ok_or_else(|| "malformed HTTP response (no header terminator)".to_string())?;
    let status_line = head.lines().next().ok_or("empty HTTP response")?;
    let mut parts = status_line.split_whitespace();
    let _version = parts.next();
    let code = parts
        .next()
        .and_then(|c| c.parse::<u16>().ok())
        .ok_or_else(|| format!("unreadable status line: {status_line}"))?;
    Ok((code, body.to_string()))
}

#[cfg(windows)]
mod win {
    use std::ffi::c_void;

    pub const AF_INET: u32 = 2;
    pub const TCP_TABLE_OWNER_PID_LISTENER: u32 = 3;
    pub const ERROR_INSUFFICIENT_BUFFER: u32 = 122;
    pub const PROCESS_TERMINATE: u32 = 0x0001;

    /// `MIB_TCPROW_OWNER_PID`, 24 bytes.
    #[repr(C)]
    pub struct MibTcpRowOwnerPid {
        pub state: u32,
        pub local_addr: u32,
        pub local_port: u32,
        pub remote_addr: u32,
        pub remote_port: u32,
        pub owning_pid: u32,
    }

    #[link(name = "iphlpapi")]
    extern "system" {
        pub fn GetExtendedTcpTable(
            table: *mut c_void,
            size: *mut u32,
            order: i32,
            address_family: u32,
            table_class: u32,
            reserved: u32,
        ) -> u32;
    }

    #[link(name = "kernel32")]
    extern "system" {
        pub fn OpenProcess(access: u32, inherit: i32, pid: u32) -> *mut c_void;
        pub fn TerminateProcess(handle: *mut c_void, exit_code: u32) -> i32;
        pub fn CloseHandle(handle: *mut c_void) -> i32;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;
    use std::thread;

    /// Bind an ephemeral port and return it; the listener keeps it busy.
    fn bind() -> (TcpListener, u16) {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind ephemeral port");
        let port = listener.local_addr().unwrap().port();
        (listener, port)
    }

    /// Minimal HTTP/1.1 responder for one request.
    fn serve_once(listener: TcpListener, status: &'static str) {
        thread::spawn(move || {
            if let Ok((mut stream, _)) = listener.accept() {
                let mut buf = [0u8; 256];
                let _ = stream.read(&mut buf);
                let _ = stream.write_all(
                    format!("HTTP/1.1 {status}\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
                        .as_bytes(),
                );
            }
        });
    }

    #[test]
    fn health_is_ok_when_the_backend_answers_200() {
        let (listener, port) = bind();
        serve_once(listener, "200 OK");
        assert!(http_health_ok(port, Duration::from_secs(2)));
    }

    #[test]
    fn health_is_not_ok_for_an_error_status() {
        let (listener, port) = bind();
        serve_once(listener, "500 Internal Server Error");
        assert!(!http_health_ok(port, Duration::from_secs(2)));
    }

    #[test]
    fn health_is_not_ok_when_nothing_listens() {
        let (listener, port) = bind();
        drop(listener); // free the port again
        assert!(!http_health_ok(port, Duration::from_millis(300)));
    }

    #[cfg(windows)]
    #[test]
    fn listening_pids_finds_our_own_listener() {
        let (_listener, port) = bind();
        let pids = listening_pids(port);
        assert!(
            pids.contains(&std::process::id()),
            "expected our own pid in {pids:?} for port {port}"
        );
    }

    #[cfg(windows)]
    #[test]
    fn listening_pids_is_empty_for_a_free_port() {
        let (listener, port) = bind();
        drop(listener);
        thread::sleep(Duration::from_millis(100));
        assert!(listening_pids(port).is_empty());
    }

    #[cfg(windows)]
    #[test]
    fn kill_port_never_kills_the_caller() {
        // Our test process listens, so the guard would fire if it were missing.
        let (_listener, port) = bind();
        let killed = kill_port(port);
        assert!(
            !killed.contains(&std::process::id()),
            "kill_port must never terminate its own process"
        );
    }

    #[test]
    fn parse_http_response_reads_status_and_body() {
        let (status, body) =
            parse_http_response(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok").unwrap();
        assert_eq!(status, 200);
        assert_eq!(body, "ok");
    }

    #[test]
    fn parse_http_response_rejects_a_bodyless_response() {
        assert!(parse_http_response(b"HTTP/1.1 404").is_err());
    }

    /// A tiny one-shot HTTP server that records the request it received.
    fn echo_once(listener: TcpListener, status_line: &'static str, body: &'static str) -> std::sync::mpsc::Receiver<String> {
        let (tx, rx) = std::sync::mpsc::channel();
        thread::spawn(move || {
            if let Ok((mut stream, _)) = listener.accept() {
                // Read the whole request (headers + body) before replying, so the
                // client is never still writing when we answer and close.
                let mut buf = [0u8; 4096];
                let mut seen = Vec::new();
                loop {
                    match stream.read(&mut buf) {
                        Ok(0) => break,
                        Ok(n) => {
                            seen.extend_from_slice(&buf[..n]);
                            if String::from_utf8_lossy(&seen).contains("\r\n\r\n") {
                                break;
                            }
                        }
                        Err(_) => break,
                    }
                }
                let _ = tx.send(String::from_utf8_lossy(&seen).into_owned());
                let _ = stream.write_all(
                    format!(
                        "{status_line}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                        body.len()
                    )
                    .as_bytes(),
                );
            }
        });
        rx
    }

    #[test]
    fn http_request_sends_method_path_body_and_key_and_returns_the_body() {
        // Bind an ephemeral port so the test never fights the running backend.
        let listener = TcpListener::bind(("127.0.0.1", 0)).expect("bind ephemeral");
        let port = listener.local_addr().unwrap().port();
        let rx = echo_once(listener, "HTTP/1.1 201 Created", "{\"ok\":true}");

        let (status, body) = http_request_to(
            port,
            "POST",
            "/analyze/async",
            Some("{\"material\":\"x\"}"),
            Some("k"),
            Duration::from_secs(2),
        )
        .unwrap();

        assert_eq!(status, 201);
        assert_eq!(body, "{\"ok\":true}");
        let request = rx.recv_timeout(Duration::from_secs(2)).unwrap();
        assert!(request.starts_with("POST /analyze/async HTTP/1.1"));
        assert!(request.contains("X-API-Key: k"));
        assert!(request.contains("{\"material\":\"x\"}"));
    }
}
