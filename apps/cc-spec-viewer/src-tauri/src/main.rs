#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::hash_map::DefaultHasher;
use std::env;
use std::fs;
use std::hash::{Hash, Hasher};
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::Command;
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

fn hash_project_path(project_path: &str) -> String {
    let mut hasher = DefaultHasher::new();
    project_path.hash(&mut hasher);
    format!("{:x}", hasher.finish())
}

fn history_path(project_path: &str) -> PathBuf {
    let hash = hash_project_path(project_path);
    home_dir()
        .join(".cc-spec")
        .join("viewer")
        .join(hash)
        .join("history.json")
}

fn sessions_path(project_path: &str) -> PathBuf {
    PathBuf::from(project_path)
        .join(".cc-spec")
        .join("runtime")
        .join("codex")
        .join("sessions.json")
}

fn find_session_pid(sessions_json: &Value, session_id: &str) -> Option<i64> {
    let sessions = sessions_json
        .get("sessions")
        .and_then(|value| value.as_object())
        .or_else(|| sessions_json.as_object());
    let record = sessions.and_then(|map| map.get(session_id))?;
    record.get("pid").and_then(|value| value.as_i64())
}

fn is_process_running(pid: i64) -> Result<bool, String> {
    let pid_str = pid.to_string();
    if cfg!(windows) {
        let output = Command::new("tasklist")
            .args(["/FI", &format!("PID eq {}", pid_str)])
            .output()
            .map_err(|err| format!("检查进程失败: {}", err))?;
        let stdout = String::from_utf8_lossy(&output.stdout);
        let running = stdout
            .lines()
            .any(|line| line.split_whitespace().any(|token| token == pid_str));
        Ok(running)
    } else {
        let status = Command::new("kill")
            .args(["-0", &pid_str])
            .status()
            .map_err(|err| format!("检查进程失败: {}", err))?;
        Ok(status.success())
    }
}

fn terminate_process(pid: i64) -> Result<(), String> {
    let pid_str = pid.to_string();
    if cfg!(windows) {
        let output = Command::new("taskkill")
            .args(["/PID", &pid_str, "/F"])
            .output()
            .map_err(|err| format!("终止进程失败: {}", err))?;
        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(format!("终止进程失败: {}", stderr.trim()));
        }
    } else {
        let status = Command::new("kill")
            .args(["-9", &pid_str])
            .status()
            .map_err(|err| format!("终止进程失败: {}", err))?;
        if !status.success() {
            return Err("终止进程失败".to_string());
        }
    }
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

#[tauri::command]
fn save_history(project_path: String, history_json: String) -> Result<(), String> {
    let path = history_path(&project_path);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| format!("创建历史记录目录失败: {}", err))?;
    }
    fs::write(&path, history_json).map_err(|err| format!("保存历史记录失败: {}", err))?;
    Ok(())
}

#[tauri::command]
fn load_history(project_path: String) -> Result<String, String> {
    let path = history_path(&project_path);
    if !path.exists() {
        return Ok("[]".to_string());
    }
    fs::read_to_string(&path).map_err(|err| format!("加载历史记录失败: {}", err))
}

#[tauri::command]
fn load_sessions(project_path: String) -> Result<String, String> {
    let path = sessions_path(&project_path);
    if !path.exists() {
        return Ok("{\"schema_version\":1,\"updated_at\":\"\",\"sessions\":{}}".to_string());
    }
    fs::read_to_string(&path).map_err(|err| format!("加载会话状态失败: {}", err))
}

#[tauri::command]
fn stop_session(project_path: String, session_id: String) -> Result<String, String> {
    if session_id.trim().is_empty() {
        return Err("session_id 为空".to_string());
    }
    let path = sessions_path(&project_path);
    if !path.exists() {
        return Err("会话状态文件不存在".to_string());
    }
    let raw = fs::read_to_string(&path).map_err(|err| format!("读取会话状态失败: {}", err))?;
    let sessions_json =
        serde_json::from_str::<Value>(&raw).map_err(|err| format!("解析会话状态失败: {}", err))?;
    let pid = match find_session_pid(&sessions_json, &session_id) {
        Some(pid) if pid > 0 => pid,
        Some(_) => return Ok("pid 无效".to_string()),
        None => return Ok("pid 未记录".to_string()),
    };

    if !is_process_running(pid)? {
        return Ok("进程未运行".to_string());
    }

    terminate_process(pid)?;
    Ok("已终止进程".to_string())
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
        .invoke_handler(tauri::generate_handler![
            get_settings,
            set_settings,
            save_history,
            load_history,
            load_sessions,
            stop_session
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
