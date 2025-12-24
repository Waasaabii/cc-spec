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
use std::sync::atomic::{AtomicU8, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::Duration;
use events::{AgentEvent, AgentEventType, AgentSource, EventDispatcher};

mod claude;
mod codex_runner;
mod concurrency;
mod database;
mod events;
mod export;
mod index;
mod projects;
mod sidecar;
mod skills;
mod terminal;
mod translation;

const DEFAULT_PORT: u16 = 38888;
const SETTINGS_VERSION: u32 = 1;

// ============================================================================
// 设置结构体定义
// ============================================================================

#[derive(Clone, Debug, Serialize, Deserialize)]
struct ViewerSettings {
    #[serde(default = "default_version")]
    version: u32,
    #[serde(default = "default_port")]
    port: u16,
    #[serde(default)]
    claude: ClaudeSettings,
    #[serde(default)]
    codex: CodexSettings,
    #[serde(default)]
    index: IndexSettings,
    #[serde(default)]
    translation: TranslationSettings,
    #[serde(default)]
    database: DatabaseSettings,
    #[serde(default)]
    ui: UiSettings,
}

fn default_version() -> u32 {
    SETTINGS_VERSION
}

fn default_port() -> u16 {
    DEFAULT_PORT
}

impl Default for ViewerSettings {
    fn default() -> Self {
        Self {
            version: SETTINGS_VERSION,
            port: DEFAULT_PORT,
            claude: ClaudeSettings::default(),
            codex: CodexSettings::default(),
            index: IndexSettings::default(),
            translation: TranslationSettings::default(),
            database: DatabaseSettings::default(),
            ui: UiSettings::default(),
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
struct ClaudeSettings {
    /// "auto" 表示自动检测，否则为自定义路径
    #[serde(default = "default_claude_path")]
    path: String,
    /// 自定义路径（当 path 不是 "auto" 时使用）
    #[serde(default)]
    custom_path: Option<String>,
    /// CC 最大并发数
    #[serde(default = "default_cc_max_concurrent")]
    max_concurrent: u8,
}

fn default_claude_path() -> String {
    "auto".to_string()
}

fn default_cc_max_concurrent() -> u8 {
    1
}

impl Default for ClaudeSettings {
    fn default() -> Self {
        Self {
            path: "auto".to_string(),
            custom_path: None,
            max_concurrent: 1,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
struct CodexSettings {
    /// CX 最大并发数
    #[serde(default = "default_cx_max_concurrent")]
    max_concurrent: u8,
}

fn default_cx_max_concurrent() -> u8 {
    5
}

impl Default for CodexSettings {
    fn default() -> Self {
        Self { max_concurrent: 5 }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
struct IndexSettings {
    /// 是否启用多级索引
    #[serde(default = "default_true")]
    enabled: bool,
    /// 是否自动更新索引
    #[serde(default = "default_true")]
    auto_update: bool,
}

fn default_true() -> bool {
    true
}

impl Default for IndexSettings {
    fn default() -> Self {
        Self {
            enabled: true,
            auto_update: true,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
struct TranslationSettings {
    /// 翻译模型是否已下载
    #[serde(default)]
    model_downloaded: bool,
    /// 模型存储路径
    #[serde(default)]
    model_path: Option<String>,
    /// 是否启用翻译缓存
    #[serde(default = "default_true")]
    cache_enabled: bool,
}

impl Default for TranslationSettings {
    fn default() -> Self {
        Self {
            model_downloaded: false,
            model_path: None,
            cache_enabled: true,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
struct DatabaseSettings {
    /// 数据库类型: "docker" | "remote" | "none"
    #[serde(default = "default_db_type")]
    db_type: String,
    /// 远程数据库连接字符串
    #[serde(default)]
    connection_string: Option<String>,
}

fn default_db_type() -> String {
    "none".to_string()
}

impl Default for DatabaseSettings {
    fn default() -> Self {
        Self {
            db_type: "none".to_string(),
            connection_string: None,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
struct UiSettings {
    /// 主题: "system" | "dark" | "light"
    #[serde(default = "default_theme")]
    theme: String,
    /// 语言: "zh-CN" | "en-US"
    #[serde(default = "default_language")]
    language: String,
}

fn default_theme() -> String {
    "system".to_string()
}

fn default_language() -> String {
    "zh-CN".to_string()
}

impl Default for UiSettings {
    fn default() -> Self {
        Self {
            theme: "system".to_string(),
            language: "zh-CN".to_string(),
        }
    }
}

/// 总并发限制（CC + CX 共享）
const TOTAL_CONCURRENCY_LIMIT: u8 = 6;

struct ConcurrencyController {
    cc_running: AtomicU8,
    cx_running: AtomicU8,
    cc_queued: AtomicU8,
    cx_queued: AtomicU8,
}

impl ConcurrencyController {
    fn new() -> Self {
        Self {
            cc_running: AtomicU8::new(0),
            cx_running: AtomicU8::new(0),
            cc_queued: AtomicU8::new(0),
            cx_queued: AtomicU8::new(0),
        }
    }

    /// 获取当前总运行数
    fn total_running(&self) -> u8 {
        self.cc_running.load(Ordering::SeqCst) + self.cx_running.load(Ordering::SeqCst)
    }

    fn can_start_cc(&self, max: u8) -> bool {
        self.cc_running.load(Ordering::SeqCst) < max 
            && self.total_running() < TOTAL_CONCURRENCY_LIMIT
    }

    fn can_start_cx(&self, max: u8) -> bool {
        self.cx_running.load(Ordering::SeqCst) < max 
            && self.total_running() < TOTAL_CONCURRENCY_LIMIT
    }

    fn acquire_cc(&self, max: u8) -> Result<(), String> {
        let current = self.cc_running.load(Ordering::SeqCst);
        if current >= max {
            return Err(format!("CC 并发已达上限 {}", max));
        }
        if self.total_running() >= TOTAL_CONCURRENCY_LIMIT {
            return Err(format!("总并发已达上限 {}", TOTAL_CONCURRENCY_LIMIT));
        }
        self.cc_running.fetch_add(1, Ordering::SeqCst);
        Ok(())
    }

    fn acquire_cx(&self, max: u8) -> Result<(), String> {
        let current = self.cx_running.load(Ordering::SeqCst);
        if current >= max {
            return Err(format!("CX 并发已达上限 {}", max));
        }
        if self.total_running() >= TOTAL_CONCURRENCY_LIMIT {
            return Err(format!("总并发已达上限 {}", TOTAL_CONCURRENCY_LIMIT));
        }
        self.cx_running.fetch_add(1, Ordering::SeqCst);
        Ok(())
    }

    fn release_cc(&self) {
        let prev = self.cc_running.fetch_sub(1, Ordering::SeqCst);
        if prev == 0 {
            // 防止下溢，恢复为 0
            self.cc_running.store(0, Ordering::SeqCst);
        }
    }

    fn release_cx(&self) {
        let prev = self.cx_running.fetch_sub(1, Ordering::SeqCst);
        if prev == 0 {
            // 防止下溢，恢复为 0
            self.cx_running.store(0, Ordering::SeqCst);
        }
    }

    /// 增加 CC 队列计数
    fn enqueue_cc(&self) {
        self.cc_queued.fetch_add(1, Ordering::SeqCst);
    }

    /// 减少 CC 队列计数
    fn dequeue_cc(&self) {
        let prev = self.cc_queued.fetch_sub(1, Ordering::SeqCst);
        if prev == 0 {
            self.cc_queued.store(0, Ordering::SeqCst);
        }
    }

    /// 增加 CX 队列计数
    fn enqueue_cx(&self) {
        self.cx_queued.fetch_add(1, Ordering::SeqCst);
    }

    /// 减少 CX 队列计数
    fn dequeue_cx(&self) {
        let prev = self.cx_queued.fetch_sub(1, Ordering::SeqCst);
        if prev == 0 {
            self.cx_queued.store(0, Ordering::SeqCst);
        }
    }
}

#[derive(Clone, Debug, Serialize)]
struct ConcurrencyStatus {
    cc_running: u8,
    cx_running: u8,
    cc_max: u8,
    cx_max: u8,
    /// CC 队列中等待的任务数
    cc_queued: u8,
    /// CX 队列中等待的任务数
    cx_queued: u8,
    /// 总运行数
    total_running: u8,
    /// 总并发限制
    total_max: u8,
}

struct AppState {
    concurrency: Arc<concurrency::ConcurrencyController>,
    legacy_concurrency: Arc<ConcurrencyController>,
    settings: Arc<Mutex<ViewerSettings>>,
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

fn normalize_agent_ids(payload: &Value) -> (String, String) {
    let session_id = payload
        .get("session_id")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let run_id = payload
        .get("run_id")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let mut sid = if session_id.is_empty() { run_id.clone() } else { session_id };
    let mut rid = if run_id.is_empty() { sid.clone() } else { run_id };
    if sid.is_empty() {
        sid = "unknown".to_string();
    }
    if rid.is_empty() {
        rid = sid.clone();
    }
    (sid, rid)
}

fn agent_event_name(event: &AgentEvent) -> &'static str {
    match event.event_type {
        AgentEventType::Started { .. } => "agent.started",
        AgentEventType::Stream { .. } => "agent.stream",
        AgentEventType::ToolRequest { .. } => "agent.tool.request",
        AgentEventType::ToolResult { .. } => "agent.tool.result",
        AgentEventType::Completed { .. } => "agent.completed",
        AgentEventType::Error { .. } => "agent.error",
        AgentEventType::Heartbeat { .. } => "agent.heartbeat",
    }
}

fn publish_agent_from_ingest(payload: &Value, dispatcher: &EventDispatcher, broadcaster: &Broadcaster) {
    let event_type = payload.get("type").and_then(|v| v.as_str()).unwrap_or("");
    let (session_id, run_id) = normalize_agent_ids(payload);
    let mapped = match event_type {
        "codex.started" => {
            let pid = payload.get("pid").and_then(|v| v.as_u64()).map(|v| v as u32);
            let project_root = payload
                .get("project_root")
                .and_then(|v| v.as_str())
                .map(|v| v.to_string());
            Some((AgentEventType::Started { pid, project_root }, AgentSource::Codex))
        }
        "codex.stream" => {
            let text = payload.get("text").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let channel = payload
                .get("stream")
                .and_then(|v| v.as_str())
                .map(|v| v.to_string());
            Some((AgentEventType::Stream { text, channel, partial: None }, AgentSource::Codex))
        }
        "codex.completed" => {
            let success = payload.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
            let exit_code = payload.get("exit_code").and_then(|v| v.as_i64()).map(|v| v as i32);
            let duration = payload.get("duration_s").and_then(|v| v.as_f64());
            Some((AgentEventType::Completed { success, exit_code, duration }, AgentSource::Codex))
        }
        "codex.error" => {
            let message = payload
                .get("message")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown error")
                .to_string();
            let error_type = payload
                .get("error_type")
                .and_then(|v| v.as_str())
                .map(|v| v.to_string());
            Some((AgentEventType::Error { message, error_type, recoverable: None }, AgentSource::Codex))
        }
        "codex.user_input" => {
            let text = payload.get("text").and_then(|v| v.as_str()).unwrap_or("").to_string();
            Some((AgentEventType::Stream { text, channel: Some("user_input".to_string()), partial: None }, AgentSource::Viewer))
        }
        _ => None,
    };

    if let Some((event_type, source)) = mapped {
        let event = dispatcher.publish_raw(event_type, source, session_id, run_id);
        let payload = serde_json::to_string(&event).unwrap_or_else(|_| "{}".to_string());
        let event_name = agent_event_name(&event);
        let sse_payload = format!("event: {}\ndata: {}\n\n", event_name, payload);
        broadcaster.publish(sse_payload);
    }
}

fn handle_ingest(mut stream: TcpStream, broadcaster: Arc<Broadcaster>, dispatcher: Arc<EventDispatcher>, body: String) {
    let parsed = serde_json::from_str::<Value>(&body).ok();
    let event_name = parsed
        .as_ref()
        .and_then(|value| value.get("type").and_then(|v| v.as_str()).map(|s| s.to_string()))
        .unwrap_or_else(|| "codex.stream".to_string());
    let payload = format!("event: {}\ndata: {}\n\n", event_name, body);
    broadcaster.publish(payload);

    if let Some(value) = parsed {
        publish_agent_from_ingest(&value, &dispatcher, &broadcaster);
    }

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
    home_dir().join(".cc-spec").join("tools.json")
}

fn legacy_config_path() -> PathBuf {
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
    let legacy = legacy_config_path();
    if let Ok(raw) = fs::read_to_string(&legacy) {
        if let Ok(mut settings) = serde_json::from_str::<ViewerSettings>(&raw) {
            if settings.port == 0 {
                settings.port = DEFAULT_PORT;
            }
            let _ = save_settings(&settings);
            return settings;
        }
    }
    ViewerSettings::default()
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
        .join("tools")
        .join(hash)
        .join("history.json")
}

fn legacy_history_path(project_path: &str) -> PathBuf {
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

/// 发送软终止信号（不强制杀死）
fn soft_terminate_process(pid: i64) -> Result<(), String> {
    let pid_str = pid.to_string();
    if cfg!(windows) {
        // Windows: taskkill 不带 /F，发送 WM_CLOSE 消息
        // 注意：这可能不会对所有进程生效
        let output = Command::new("taskkill")
            .args(["/PID", &pid_str])
            .output()
            .map_err(|err| format!("发送终止信号失败: {}", err))?;
        // 不检查返回值，因为进程可能不响应 WM_CLOSE
        let _ = output;
        Ok(())
    } else {
        // Unix: 发送 SIGINT (Ctrl-C)
        let status = Command::new("kill")
            .args(["-INT", &pid_str])
            .status()
            .map_err(|err| format!("发送终止信号失败: {}", err))?;
        if !status.success() {
            // SIGINT 可能失败，继续尝试
        }
        Ok(())
    }
}

/// 强制终止进程
fn force_terminate_process(pid: i64) -> Result<(), String> {
    let pid_str = pid.to_string();
    if cfg!(windows) {
        let output = Command::new("taskkill")
            .args(["/PID", &pid_str, "/F"])
            .output()
            .map_err(|err| format!("强制终止进程失败: {}", err))?;
        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(format!("强制终止进程失败: {}", stderr.trim()));
        }
    } else {
        let status = Command::new("kill")
            .args(["-9", &pid_str])
            .status()
            .map_err(|err| format!("强制终止进程失败: {}", err))?;
        if !status.success() {
            return Err("强制终止进程失败".to_string());
        }
    }
    Ok(())
}

/// 优雅停止进程：软终止 → 等待 → 检查 → 强制终止
/// 返回 (是否成功, 是否使用了强制终止)
fn graceful_stop_process(pid: i64, wait_secs: u64) -> Result<(bool, bool), String> {
    // 1. 发送软终止信号
    let _ = soft_terminate_process(pid);
    
    // 2. 等待进程退出
    let wait_time = Duration::from_secs(wait_secs);
    let check_interval = Duration::from_millis(500);
    let start = std::time::Instant::now();
    
    while start.elapsed() < wait_time {
        thread::sleep(check_interval);
        if !is_process_running(pid)? {
            // 进程已优雅退出
            return Ok((true, false));
        }
    }
    
    // 3. 检查进程是否仍在运行
    if !is_process_running(pid)? {
        return Ok((true, false));
    }
    
    // 4. 强制终止
    force_terminate_process(pid)?;
    
    // 5. 再次检查确认已退出
    thread::sleep(Duration::from_millis(500));
    if is_process_running(pid)? {
        return Err("进程仍在运行，无法终止".to_string());
    }
    
    Ok((true, true))
}

/// 旧版强制终止（保持兼容）
fn terminate_process(pid: i64) -> Result<(), String> {
    force_terminate_process(pid)
}

#[tauri::command]
fn get_settings() -> ViewerSettings {
    load_settings()
}

#[tauri::command]
fn set_settings(settings: ViewerSettings) -> Result<ViewerSettings, String> {
    if settings.port == 0 {
        return Err("端口无效".to_string());
    }
    save_settings(&settings)?;
    Ok(settings)
}

#[tauri::command]
fn launch_claude_terminal(
    project_path: String,
    session_id: Option<String>,
) -> Result<(), String> {
    if project_path.trim().is_empty() {
        return Err("project_path 为空".to_string());
    }
    let settings = load_settings();
    terminal::launch_claude_terminal(
        project_path,
        "127.0.0.1".to_string(),
        settings.port,
        session_id,
    )
}

#[tauri::command]
fn codex_pause(
    project_path: String,
    session_id: String,
    run_id: Option<String>,
) -> Result<(), String> {
    codex_runner::pause_session(project_path, session_id, run_id)
}

#[tauri::command]
fn codex_resume(
    project_path: String,
    session_id: String,
    prompt: String,
    timeout_ms: Option<u64>,
) -> Result<codex_runner::CodexRunResult, String> {
    if prompt.trim().is_empty() {
        return Err("prompt 为空".to_string());
    }
    let request = codex_runner::CodexRunRequest {
        project_path,
        prompt,
        session_id: Some(session_id),
        timeout_ms,
    };
    codex_runner::run_codex(request)
}

#[tauri::command]
fn get_concurrency_status(state: tauri::State<AppState>) -> concurrency::ConcurrencyStatus {
    state.concurrency.status()
}

/// 取消排队中的任务
#[tauri::command]
fn cancel_queued_task(state: tauri::State<AppState>, task_id: u64) -> Result<bool, String> {
    Ok(state.concurrency.cancel_queued(task_id))
}

/// 更新并发限制
#[tauri::command]
fn update_concurrency_limits(state: tauri::State<AppState>, cc_max: u8, cx_max: u8) -> Result<(), String> {
    state.concurrency.set_limits(cc_max, cx_max);
    Ok(())
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
    if path.exists() {
        return fs::read_to_string(&path).map_err(|err| format!("加载历史记录失败: {}", err));
    }
    let legacy = legacy_history_path(&project_path);
    if legacy.exists() {
        return fs::read_to_string(&legacy).map_err(|err| format!("加载历史记录失败: {}", err));
    }
    Ok("[]".to_string())
}

#[tauri::command]
fn load_sessions(project_path: String) -> Result<String, String> {
    let path = sessions_path(&project_path);
    if !path.exists() {
        return Ok("{\"schema_version\":1,\"updated_at\":\"\",\"sessions\":{}}".to_string());
    }
    fs::read_to_string(&path).map_err(|err| format!("加载会话状态失败: {}", err))
}

/// 停止会话响应
#[derive(Clone, Debug, Serialize)]
struct StopSessionResponse {
    success: bool,
    message: String,
    forced: bool,
}

/// 优雅停止 CX 会话（软终止 → 等待 → 强制终止）
#[tauri::command]
fn graceful_stop_session(
    project_path: String,
    session_id: String,
    wait_secs: Option<u64>,
) -> Result<StopSessionResponse, String> {
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
        Some(_) => {
            return Ok(StopSessionResponse {
                success: false,
                message: "pid 无效".to_string(),
                forced: false,
            })
        }
        None => {
            return Ok(StopSessionResponse {
                success: false,
                message: "pid 未记录".to_string(),
                forced: false,
            })
        }
    };

    if !is_process_running(pid)? {
        return Ok(StopSessionResponse {
            success: true,
            message: "进程已停止".to_string(),
            forced: false,
        });
    }

    // 使用优雅停止，默认等待 3 秒
    let wait = wait_secs.unwrap_or(3);
    let (success, forced) = graceful_stop_process(pid, wait)?;
    
    Ok(StopSessionResponse {
        success,
        message: if forced {
            "已强制终止进程".to_string()
        } else {
            "进程已优雅停止".to_string()
        },
        forced,
    })
}

/// 强制停止会话（保持向后兼容）
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

    // 使用优雅停止，等待 3 秒
    match graceful_stop_process(pid, 3) {
        Ok((_, forced)) => {
            if forced {
                Ok("已强制终止进程".to_string())
            } else {
                Ok("进程已优雅停止".to_string())
            }
        }
        Err(e) => Err(e),
    }
}

fn start_server(port: u16) {
    let broadcaster = Arc::new(Broadcaster::new());
    let dispatcher = Arc::new(EventDispatcher::new());
    let addr = format!("127.0.0.1:{}", port);
    let listener = match TcpListener::bind(&addr) {
        Ok(listener) => listener,
        Err(err) => {
            eprintln!("tools server failed to bind {}: {}", addr, err);
            return;
        }
    };

    for stream in listener.incoming() {
        let broadcaster = Arc::clone(&broadcaster);
        let dispatcher = Arc::clone(&dispatcher);
        match stream {
            Ok(stream) => {
                thread::spawn(move || {
                    let mut stream = stream;
                    if let Some((method, path, body)) = parse_request(&mut stream) {
                        match (method.as_str(), path.as_str()) {
                            ("GET", "/events") => handle_events(stream, broadcaster),
                            ("POST", "/ingest") => handle_ingest(stream, broadcaster, dispatcher, body),
                            _ => handle_not_found(stream),
                        }
                    }
                });
            }
            Err(err) => {
                eprintln!("tools server connection error: {}", err);
            }
        }
    }
}

fn main() {
    let settings = load_settings();
    let port = settings.port;
    let cc_max = settings.claude.max_concurrent;
    let cx_max = settings.codex.max_concurrent;
    thread::spawn(move || start_server(port));
    let app_state = AppState {
        concurrency: Arc::new(concurrency::ConcurrencyController::new(cc_max, cx_max)),
        legacy_concurrency: Arc::new(ConcurrencyController::new()),
        settings: Arc::new(Mutex::new(settings)),
    };

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(app_state)
        .invoke_handler(tauri::generate_handler![
            get_settings,
            set_settings,
            get_concurrency_status,
            cancel_queued_task,
            update_concurrency_limits,
            save_history,
            load_history,
            load_sessions,
            stop_session,
            graceful_stop_session,
            launch_claude_terminal,
            codex_pause,
            codex_resume,
            projects::import_project,
            projects::list_projects,
            projects::get_current_project,
            projects::set_current_project,
            projects::remove_project,
            // Claude commands
            claude::cmd_detect_claude_path,
            claude::cmd_validate_claude_path,
            claude::start_claude,
            claude::send_claude_message,
            claude::stop_claude,
            claude::graceful_stop_claude,
            claude::get_claude_session,
            claude::list_claude_sessions,
            claude::is_claude_session_active,
            claude::get_claude_session_count,
            // Database commands
            database::check_database_connection,
            database::start_docker_postgres,
            database::stop_docker_postgres,
            database::get_docker_postgres_logs,
            database::connect_remote_database,
            // Index commands
            index::get_index_status,
            index::check_index_exists,
            index::init_index,
            index::update_index,
            index::get_index_settings_prompt_dismissed,
            index::set_index_settings_prompt_dismissed,
            // Translation commands
            translation::check_translation_model,
            translation::download_translation_model,
            translation::translate_text,
            translation::clear_translation_cache,
            translation::delete_translation_model,
            translation::get_translation_cache_stats,
            translation::preload_translation_model,
            // Export commands
            export::export_history,
            export::import_history,
            export::get_export_size_estimate,
            // Sidecar commands
            sidecar::run_ccspec_command,
            sidecar::run_ccspec_stream,
            sidecar::check_sidecar_available,
            sidecar::get_ccspec_version,
            // Skills commands
            skills::check_skills_status,
            skills::install_skills,
            skills::uninstall_skills,
            skills::get_skills_version,
            skills::check_skills_update_needed
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
