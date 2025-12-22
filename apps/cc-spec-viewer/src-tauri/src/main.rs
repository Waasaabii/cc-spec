#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::env;
use std::fs;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::Duration;

const DEFAULT_PORT: u16 = 38888;

#[derive(Clone, Debug, Serialize, Deserialize)]
struct ViewerSettings {
    port: u16,
}

struct Broadcaster {
    clients: Mutex<Vec<mpsc::Sender<String>>>,
}

impl Broadcaster {
    fn new() -> Self {
        Self {
            clients: Mutex::new(Vec::new()),
        }
    }

    fn add_client(&self) -> mpsc::Receiver<String> {
        let (tx, rx) = mpsc::channel();
        if let Ok(mut clients) = self.clients.lock() {
            clients.push(tx);
        }
        rx
    }

    fn publish(&self, payload: String) {
        if let Ok(mut clients) = self.clients.lock() {
            clients.retain(|tx| tx.send(payload.clone()).is_ok());
        }
    }
}

fn parse_request(stream: &mut TcpStream) -> Option<(String, String, String)> {
    let mut buffer = [0_u8; 4096];
    let mut data: Vec<u8> = Vec::new();

    stream.set_read_timeout(Some(Duration::from_secs(2))).ok()?;
    loop {
        let read = stream.read(&mut buffer).ok()?;
        if read == 0 {
            break;
        }
        data.extend_from_slice(&buffer[..read]);
        if data.windows(4).any(|w| w == b"\r\n\r\n") {
            break;
        }
        if data.len() > 16_384 {
            break;
        }
    }

    let header_end = data.windows(4).position(|w| w == b"\r\n\r\n")?;
    let head = String::from_utf8_lossy(&data[..header_end]).to_string();
    let mut body = data[(header_end + 4)..].to_vec();

    let mut lines = head.lines();
    let request_line = lines.next()?.to_string();
    let mut parts = request_line.split_whitespace();
    let method = parts.next()?.to_string();
    let path = parts.next()?.to_string();

    let mut content_length = 0_usize;
    for line in lines {
        let lower = line.to_ascii_lowercase();
        if let Some(rest) = lower.strip_prefix("content-length:") {
            content_length = rest.trim().parse().unwrap_or(0);
            break;
        }
    }

    if content_length > 0 && body.len() < content_length {
        let mut remaining = content_length - body.len();
        while remaining > 0 {
            let read = stream.read(&mut buffer).ok()?;
            if read == 0 {
                break;
            }
            body.extend_from_slice(&buffer[..read]);
            remaining = content_length.saturating_sub(body.len());
        }
    }

    let body_text = if content_length == 0 {
        String::new()
    } else {
        String::from_utf8_lossy(&body[..content_length.min(body.len())]).to_string()
    };

    Some((method, path, body_text))
}

fn write_response(stream: &mut TcpStream, status: &str, headers: &[(&str, &str)], body: &str) {
    let mut response = String::new();
    response.push_str(status);
    response.push_str("\r\n");
    for (key, value) in headers {
        response.push_str(key);
        response.push_str(": ");
        response.push_str(value);
        response.push_str("\r\n");
    }
    response.push_str("\r\n");
    response.push_str(body);
    let _ = stream.write_all(response.as_bytes());
}

fn handle_events(mut stream: TcpStream, broadcaster: Arc<Broadcaster>) {
    let headers = [
        ("Content-Type", "text/event-stream"),
        ("Cache-Control", "no-cache"),
        ("Connection", "keep-alive"),
        ("Access-Control-Allow-Origin", "*"),
    ];
    write_response(&mut stream, "HTTP/1.1 200 OK", &headers, "");
    let _ = stream.write_all(b": ok\n\n");
    let _ = stream.flush();

    let receiver = broadcaster.add_client();
    loop {
        match receiver.recv_timeout(Duration::from_secs(10)) {
            Ok(payload) => {
                if stream.write_all(payload.as_bytes()).is_err() {
                    break;
                }
                let _ = stream.flush();
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {
                if stream.write_all(b": ping\n\n").is_err() {
                    break;
                }
                let _ = stream.flush();
            }
            Err(_) => break,
        }
    }
}

fn handle_ingest(mut stream: TcpStream, broadcaster: Arc<Broadcaster>, body: String) {
    let event_name = serde_json::from_str::<Value>(&body)
        .ok()
        .and_then(|value| value.get("type").and_then(|v| v.as_str()).map(|s| s.to_string()))
        .unwrap_or_else(|| "codex.stream".to_string());
    let payload = format!("event: {}\ndata: {}\n\n", event_name, body);
    broadcaster.publish(payload);

    let headers = [
        ("Content-Type", "text/plain"),
        ("Access-Control-Allow-Origin", "*"),
        ("Connection", "close"),
    ];
    write_response(&mut stream, "HTTP/1.1 202 Accepted", &headers, "ok");
}

fn handle_not_found(mut stream: TcpStream) {
    let headers = [
        ("Content-Type", "text/plain"),
        ("Access-Control-Allow-Origin", "*"),
        ("Connection", "close"),
    ];
    write_response(&mut stream, "HTTP/1.1 404 Not Found", &headers, "not found");
}

fn home_dir() -> PathBuf {
    env::var_os("USERPROFILE")
        .map(PathBuf::from)
        .or_else(|| env::var_os("HOME").map(PathBuf::from))
        .unwrap_or_else(|| env::current_dir().unwrap_or_else(|_| PathBuf::from(".")))
}

fn config_path() -> PathBuf {
    home_dir().join(".cc-spec").join("viewer.json")
}

fn load_settings() -> ViewerSettings {
    let path = config_path();
    if let Ok(raw) = fs::read_to_string(&path) {
        if let Ok(mut settings) = serde_json::from_str::<ViewerSettings>(&raw) {
            if settings.port == 0 {
                settings.port = DEFAULT_PORT;
            }
            return settings;
        }
    }
    ViewerSettings {
        port: DEFAULT_PORT,
    }
}

fn save_settings(settings: &ViewerSettings) -> Result<(), String> {
    let path = config_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| format!("创建配置目录失败: {}", err))?;
    }
    let raw = serde_json::to_string_pretty(settings).map_err(|err| format!("序列化失败: {}", err))?;
    fs::write(&path, raw).map_err(|err| format!("写入失败: {}", err))?;
    Ok(())
}

#[tauri::command]
fn get_settings() -> ViewerSettings {
    load_settings()
}

#[tauri::command]
fn set_settings(port: u16) -> Result<ViewerSettings, String> {
    if port == 0 {
        return Err("端口无效".to_string());
    }
    let settings = ViewerSettings { port };
    save_settings(&settings)?;
    Ok(settings)
}

fn start_server(port: u16) {
    let broadcaster = Arc::new(Broadcaster::new());
    let addr = format!("127.0.0.1:{}", port);
    let listener = match TcpListener::bind(&addr) {
        Ok(listener) => listener,
        Err(err) => {
            eprintln!("viewer server failed to bind {}: {}", addr, err);
            return;
        }
    };

    for stream in listener.incoming() {
        let broadcaster = Arc::clone(&broadcaster);
        match stream {
            Ok(stream) => {
                thread::spawn(move || {
                    let mut stream = stream;
                    if let Some((method, path, body)) = parse_request(&mut stream) {
                        match (method.as_str(), path.as_str()) {
                            ("GET", "/events") => handle_events(stream, broadcaster),
                            ("POST", "/ingest") => handle_ingest(stream, broadcaster, body),
                            _ => handle_not_found(stream),
                        }
                    }
                });
            }
            Err(err) => {
                eprintln!("viewer server connection error: {}", err);
            }
        }
    }
}

fn main() {
    let settings = load_settings();
    let port = settings.port;
    thread::spawn(move || start_server(port));

    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![get_settings, set_settings])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
