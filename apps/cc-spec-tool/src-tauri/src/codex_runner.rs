// codex_runner.rs - Codex CLI 进程管理（Rust 版本）
//
// 当前阶段：提供基本的 exec/resume + soft_stop/kill API 框架
// 后续阶段会补充 JSONL 解析、SSE 事件输出、sessions.json 持久化等。

use once_cell::sync::Lazy;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::net::TcpStream;
use std::io::Write;
use uuid::Uuid;
use std::env;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

#[derive(Debug, Clone, Deserialize)]
pub struct CodexRunRequest {
    pub project_path: String,
    pub prompt: String,
    pub session_id: Option<String>,
    pub timeout_ms: Option<u64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct CodexRunResult {
    pub success: bool,
    pub session_id: Option<String>,
    pub run_id: String,
    pub exit_code: i32,
    pub duration_s: f64,
    pub stdout: String,
    pub stderr: String,
    pub attempts: u32,
    pub last_seq: u64,
}

static SESSIONS_LOCK: Lazy<Mutex<()>> = Lazy::new(|| Mutex::new(()));

fn now_iso() -> String {
    chrono::Utc::now().to_rfc3339()
}

fn sessions_path(project_path: &PathBuf) -> PathBuf {
    project_path
        .join(".cc-spec")
        .join("runtime")
        .join("codex")
        .join("sessions.json")
}

fn load_sessions(path: &PathBuf) -> Value {
    if let Ok(raw) = std::fs::read_to_string(path) {
        if let Ok(value) = serde_json::from_str::<Value>(&raw) {
            return value;
        }
    }
    serde_json::json!({
        "schema_version": 1,
        "updated_at": "",
        "sessions": {}
    })
}

fn find_session_pid(sessions_json: &Value, session_id: &str) -> Option<i64> {
    let sessions = sessions_json
        .get("sessions")
        .and_then(|value| value.as_object())
        .or_else(|| sessions_json.as_object());
    let record = sessions.and_then(|map| map.get(session_id))?;
    record.get("pid").and_then(|value| value.as_i64())
}

fn save_sessions(path: &PathBuf, mut value: Value) -> Result<(), String> {
    if let Some(obj) = value.as_object_mut() {
        obj.insert("schema_version".to_string(), Value::from(1));
        obj.insert("updated_at".to_string(), Value::from(now_iso()));
        obj.entry("sessions".to_string()).or_insert(Value::from(serde_json::Map::new()));
    }
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| format!("创建 sessions 目录失败: {}", e))?;
    }
    let tmp = path.with_extension("json.tmp");
    std::fs::write(&tmp, serde_json::to_string_pretty(&value).unwrap())
        .map_err(|e| format!("写入 sessions 临时文件失败: {}", e))?;
    std::fs::rename(&tmp, path).map_err(|e| format!("写入 sessions 失败: {}", e))?;
    Ok(())
}

fn register_session(path: &PathBuf, session_id: &str, task_summary: &str, pid: Option<u32>) -> Result<(), String> {
    let _guard = SESSIONS_LOCK.lock().unwrap();
    let mut data = load_sessions(path);
    let now = now_iso();
    let sessions = data
        .get_mut("sessions")
        .and_then(|v| v.as_object_mut())
        .ok_or("sessions 字段缺失")?;
    let created_at = sessions
        .get(session_id)
        .and_then(|v| v.get("created_at"))
        .and_then(|v| v.as_str())
        .unwrap_or(&now)
        .to_string();
    let record = serde_json::json!({
        "session_id": session_id,
        "state": "running",
        "task_summary": task_summary,
        "message": Value::Null,
        "exit_code": Value::Null,
        "elapsed_s": Value::Null,
        "pid": pid.map(|p| p as i64),
        "created_at": created_at,
        "updated_at": now,
    });
    sessions.insert(session_id.to_string(), record);
    save_sessions(path, data)
}

fn update_session(
    path: &PathBuf,
    session_id: &str,
    state: Option<&str>,
    message: Option<&str>,
    exit_code: Option<i32>,
    elapsed_s: Option<f64>,
    pid: Option<Option<u32>>,
) -> Result<(), String> {
    let _guard = SESSIONS_LOCK.lock().unwrap();
    let mut data = load_sessions(path);
    let now = now_iso();
    let sessions = data
        .get_mut("sessions")
        .and_then(|v| v.as_object_mut())
        .ok_or("sessions 字段缺失")?;
    let record = sessions
        .entry(session_id.to_string())
        .or_insert_with(|| serde_json::json!({ "session_id": session_id, "created_at": now }));
    if let Some(state) = state {
        record.as_object_mut().unwrap().insert("state".to_string(), Value::from(state));
    }
    if let Some(message) = message {
        record.as_object_mut().unwrap().insert("message".to_string(), Value::from(message));
    }
    if let Some(exit_code) = exit_code {
        record.as_object_mut().unwrap().insert("exit_code".to_string(), Value::from(exit_code));
    }
    if let Some(elapsed_s) = elapsed_s {
        record.as_object_mut().unwrap().insert("elapsed_s".to_string(), Value::from(elapsed_s));
    }
    if let Some(pid_opt) = pid {
        let value = pid_opt.map(|p| Value::from(p as i64)).unwrap_or(Value::Null);
        record.as_object_mut().unwrap().insert("pid".to_string(), value);
    }
    record.as_object_mut().unwrap().insert("updated_at".to_string(), Value::from(now));
    save_sessions(path, data)
}

fn summarize_task(task: &str, limit: usize) -> String {
    let summary = task
        .lines()
        .map(|line| line.trim())
        .filter(|line| !line.is_empty())
        .collect::<Vec<_>>()
        .join(" ");
    let base = if summary.is_empty() { task.trim().to_string() } else { summary };
    if base.len() > limit {
        format!("{}...", &base[..limit])
    } else {
        base
    }
}

struct ViewerClient {
    host: String,
    port: u16,
    project_root: PathBuf,
}

impl ViewerClient {
    fn publish_event(&self, mut event: serde_json::Value) {
        if let Some(obj) = event.as_object_mut() {
            obj.insert("project_root".to_string(), Value::from(self.project_root.to_string_lossy().to_string()));
        }
        let payload = serde_json::to_string(&event).unwrap_or_else(|_| "{}".to_string());
        let addr = format!("{}:{}", self.host, self.port);
        if let Ok(mut stream) = TcpStream::connect(addr) {
            let request = format!(
                "POST /ingest HTTP/1.1\r\nHost: {}:{}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                self.host,
                self.port,
                payload.len(),
                payload
            );
            let _ = stream.write_all(request.as_bytes());
        }
    }
}

fn load_viewer_config() -> Option<Value> {
    let home = env::var("USERPROFILE").or_else(|_| env::var("HOME")).ok()?;
    let new_path = PathBuf::from(&home).join(".cc-spec").join("tools.json");
    if let Ok(raw) = std::fs::read_to_string(&new_path) {
        if let Ok(config) = serde_json::from_str(&raw) {
            return Some(config);
        }
    }
    let legacy_path = PathBuf::from(home).join(".cc-spec").join("viewer.json");
    let raw = std::fs::read_to_string(legacy_path).ok()?;
    serde_json::from_str(&raw).ok()
}

fn get_viewer_client(project_path: &PathBuf) -> Option<ViewerClient> {
    let enabled = env::var("CC_SPEC_CODEX_SSE")
        .ok()
        .map(|v| {
            let v = v.to_lowercase();
            !(v == "0" || v == "false" || v == "no" || v == "off")
        })
        .unwrap_or(true);
    if !enabled {
        return None;
    }

    let config = load_viewer_config();
    let host = env::var("CC_SPEC_CODEX_SSE_HOST")
        .ok()
        .filter(|v| !v.trim().is_empty())
        .or_else(|| config.as_ref().and_then(|c| c.get("host").and_then(|v| v.as_str()).map(|s| s.to_string())))
        .unwrap_or_else(|| "127.0.0.1".to_string());
    let port = env::var("CC_SPEC_CODEX_SSE_PORT")
        .ok()
        .and_then(|v| v.parse::<u16>().ok())
        .or_else(|| config.as_ref().and_then(|c| c.get("port").and_then(|v| v.as_u64()).map(|p| p as u16)))
        .unwrap_or(38888);

    Some(ViewerClient {
        host,
        port,
        project_root: project_path.clone(),
    })
}

fn extract_session_id(line: &str) -> Option<String> {
    let value: serde_json::Value = serde_json::from_str(line).ok()?;
    if value.get("type")?.as_str()? != "thread.started" {
        return None;
    }
    value
        .get("thread_id")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
}

fn resolve_codex_bin() -> String {
    // 与 Python 版本保持一致：默认使用 PATH 中的 codex
    // Windows 下使用 where/which 定位 .cmd 可执行文件
    if let Ok(path) = env::var("CODEX_PATH") {
        if !path.trim().is_empty() {
            return path;
        }
    }

    let locator = if cfg!(windows) { "where" } else { "which" };
    if let Ok(output) = Command::new(locator).arg("codex").output() {
        if output.status.success() {
            if let Some(first) = String::from_utf8_lossy(&output.stdout).lines().next() {
                let trimmed = first.trim();
                if !trimmed.is_empty() {
                    return trimmed.to_string();
                }
            }
        }
    }

    "codex".to_string()
}

fn build_command(project_path: &str, session_id: Option<&str>) -> Vec<String> {
    let mut cmd = vec![
        resolve_codex_bin(),
        "exec".to_string(),
        "--skip-git-repo-check".to_string(),
        "--cd".to_string(),
        project_path.to_string(),
        "--json".to_string(),
    ];
    if let Some(sid) = session_id {
        cmd.push("resume".to_string());
        cmd.push(sid.to_string());
    }
    cmd.push("-".to_string());
    cmd
}

fn run_codex_once(request: CodexRunRequest) -> Result<CodexRunResult, String> {
    let uuid = Uuid::new_v4().to_string().replace('-', "");
    let run_id = format!(
        "run_{}_{}",
        chrono::Utc::now().timestamp_millis(),
        &uuid[..8]
    );
    let project_path = PathBuf::from(&request.project_path);
    let sessions_file = sessions_path(&project_path);
    let task_summary = summarize_task(&request.prompt, 200);
    let cmd = build_command(
        request.project_path.as_str(),
        request.session_id.as_deref(),
    );
    let viewer = Arc::new(get_viewer_client(&project_path));
    let prompt_for_event = request.prompt.clone();

    let mut iter = cmd.iter();
    let program = iter.next().ok_or("codex command empty")?.to_string();
    let args: Vec<String> = iter.cloned().collect();

    let started = Instant::now();
    let timeout_ms = request
        .timeout_ms
        .or_else(|| env::var("CODEX_TIMEOUT").ok().and_then(|v| v.parse().ok()))
        .unwrap_or(7_200_000);
    let timeout_deadline = started + Duration::from_millis(timeout_ms);
    let idle_timeout_s = env::var("CC_SPEC_CODEX_IDLE_TIMEOUT")
        .ok()
        .and_then(|v| v.parse::<u64>().ok())
        .unwrap_or(60);
    if let Some(viewer) = viewer.as_ref() {
        viewer.publish_event(serde_json::json!({
            "type": "codex.user_input",
            "ts": now_iso(),
            "session_id": request.session_id,
            "text": prompt_for_event,
        }));
    }

    let mut child = Command::new(program)
        .args(args)
        .current_dir(&project_path)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn();

    let mut child = match child {
        Ok(child) => child,
        Err(err) => {
            if let Some(viewer) = viewer.as_ref() {
                viewer.publish_event(serde_json::json!({
                    "type": "codex.error",
                    "ts": now_iso(),
                    "run_id": run_id.clone(),
                    "session_id": request.session_id,
                    "error_type": "not_found",
                    "message": format!("未找到 Codex CLI: {}", err),
                }));
                viewer.publish_event(serde_json::json!({
                    "type": "codex.completed",
                    "ts": now_iso(),
                    "run_id": run_id.clone(),
                    "session_id": request.session_id,
                    "success": false,
                    "exit_code": 127,
                    "error_type": "not_found",
                    "duration_s": started.elapsed().as_secs_f64(),
                }));
            }
            return Err(format!("启动 Codex 失败: {}", err));
        }
    };

    let pid = Some(child.id());
    if let Some(viewer) = viewer.as_ref() {
        viewer.publish_event(serde_json::json!({
            "type": "codex.started",
            "ts": now_iso(),
            "run_id": run_id.clone(),
            "session_id": request.session_id,
            "pid": pid,
            "project_root": project_path.to_string_lossy().to_string(),
        }));
    }
    let session_registered = Arc::new(AtomicBool::new(false));
    if let Some(ref sid) = request.session_id {
        register_session(&sessions_file, sid, &task_summary, pid)
            .map_err(|e| format!("注册 session 失败: {}", e))?;
        session_registered.store(true, Ordering::Relaxed);
    }

    if let Some(stdin) = child.stdin.as_mut() {
        use std::io::Write;
        let _ = stdin.write_all(request.prompt.as_bytes());
    }

    let stdout_lines: Arc<Mutex<Vec<String>>> = Arc::new(Mutex::new(Vec::new()));
    let stderr_lines: Arc<Mutex<Vec<String>>> = Arc::new(Mutex::new(Vec::new()));
    let session_id: Arc<Mutex<Option<String>>> = Arc::new(Mutex::new(request.session_id.clone()));
    let last_activity = Arc::new(Mutex::new(Instant::now()));
    let idle_warned = Arc::new(Mutex::new(false));
    let seq = Arc::new(Mutex::new(0_u64));

    let stdout_handle = if let Some(stdout) = child.stdout.take() {
        let stdout_lines = Arc::clone(&stdout_lines);
        let session_id = Arc::clone(&session_id);
        let sessions_file = sessions_file.clone();
        let task_summary = task_summary.clone();
        let session_registered = Arc::clone(&session_registered);
        let pid = pid;
        let seq = Arc::clone(&seq);
        let viewer = Arc::clone(&viewer);
        let run_id = run_id.clone();
        let last_activity = Arc::clone(&last_activity);
        let idle_warned = Arc::clone(&idle_warned);
        Some(std::thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            let mut buf = Vec::new();
            loop {
                buf.clear();
                let read = reader.read_until(b'\n', &mut buf).unwrap_or(0);
                if read == 0 {
                    break;
                }
                let line = String::from_utf8_lossy(&buf)
                    .trim_end_matches('\n')
                    .trim_end_matches('\r')
                    .to_string();
                if line.is_empty() {
                    continue;
                }
                let seq_value = {
                    let mut guard = seq.lock().unwrap();
                    *guard += 1;
                    *guard
                };
                *last_activity.lock().unwrap() = Instant::now();
                *idle_warned.lock().unwrap() = false;
                if let Some(sid) = extract_session_id(&line) {
                    let mut guard = session_id.lock().unwrap();
                    if guard.is_none() {
                        *guard = Some(sid);
                    }
                    if !session_registered.load(Ordering::Relaxed) {
                        if let Some(ref current_sid) = *guard {
                            let _ = register_session(&sessions_file, current_sid, &task_summary, pid);
                            session_registered.store(true, Ordering::Relaxed);
                        }
                    }
                }
                if let Some(viewer) = viewer.as_ref() {
                    let sid = session_id.lock().unwrap().clone();
                    viewer.publish_event(serde_json::json!({
                        "type": "codex.stream",
                        "ts": now_iso(),
                        "run_id": run_id,
                        "session_id": sid,
                        "stream": "stdout",
                        "seq": seq_value,
                        "text": line,
                    }));
                }
                stdout_lines.lock().unwrap().push(line);
            }
        }))
    } else {
        None
    };

    let stderr_handle = if let Some(stderr) = child.stderr.take() {
        let stderr_lines = Arc::clone(&stderr_lines);
        let seq = Arc::clone(&seq);
        let viewer = Arc::clone(&viewer);
        let run_id = run_id.clone();
        let last_activity = Arc::clone(&last_activity);
        let idle_warned = Arc::clone(&idle_warned);
        let session_id = Arc::clone(&session_id);
        Some(std::thread::spawn(move || {
            let mut reader = BufReader::new(stderr);
            let mut buf = Vec::new();
            loop {
                buf.clear();
                let read = reader.read_until(b'\n', &mut buf).unwrap_or(0);
                if read == 0 {
                    break;
                }
                let line = String::from_utf8_lossy(&buf)
                    .trim_end_matches('\n')
                    .trim_end_matches('\r')
                    .to_string();
                if line.is_empty() {
                    continue;
                }
                let seq_value = {
                    let mut guard = seq.lock().unwrap();
                    *guard += 1;
                    *guard
                };
                *last_activity.lock().unwrap() = Instant::now();
                *idle_warned.lock().unwrap() = false;
                if let Some(viewer) = viewer.as_ref() {
                    let sid = session_id.lock().unwrap().clone();
                    viewer.publish_event(serde_json::json!({
                        "type": "codex.stream",
                        "ts": now_iso(),
                        "run_id": run_id,
                        "session_id": sid,
                        "stream": "stderr",
                        "seq": seq_value,
                        "text": line,
                    }));
                }
                stderr_lines.lock().unwrap().push(line);
            }
        }))
    } else {
        None
    };

    let stderr_lines_for_idle = Arc::clone(&stderr_lines);
    let last_activity_for_idle = Arc::clone(&last_activity);
    let idle_warned_for_idle = Arc::clone(&idle_warned);
    let sessions_file_for_idle = sessions_file.clone();
    let session_id_for_idle = Arc::clone(&session_id);
    let viewer_for_idle = Arc::clone(&viewer);
    let run_id_for_idle = run_id.clone();
    let stop_idle = Arc::new(AtomicBool::new(false));
    let stop_idle_flag = Arc::clone(&stop_idle);
    let idle_handle = std::thread::spawn(move || {
        while !stop_idle_flag.load(Ordering::Relaxed) {
            std::thread::sleep(Duration::from_secs(10));
            if stop_idle_flag.load(Ordering::Relaxed) {
                break;
            }
            let last = *last_activity_for_idle.lock().unwrap();
            let elapsed = last.elapsed().as_secs();
            if elapsed >= idle_timeout_s && !*idle_warned_for_idle.lock().unwrap() {
                *idle_warned_for_idle.lock().unwrap() = true;
                let msg = format!(
                    "[cc-spec] Codex idle {}s without output",
                    elapsed
                );
                stderr_lines_for_idle.lock().unwrap().push(msg);
                if let Some(viewer) = viewer_for_idle.as_ref() {
                    let sid = session_id_for_idle.lock().unwrap().clone();
                    viewer.publish_event(serde_json::json!({
                        "type": "codex.idle_warning",
                        "ts": now_iso(),
                        "run_id": run_id_for_idle,
                        "session_id": sid,
                        "idle_seconds": elapsed,
                        "total_seconds": started.elapsed().as_secs(),
                    }));
                }
                if let Some(ref sid) = *session_id_for_idle.lock().unwrap() {
                    let _ = update_session(
                        &sessions_file_for_idle,
                        sid,
                        Some("idle"),
                        Some("idle warning: no output"),
                        None,
                        None,
                        None,
                    );
                }
            }
        }
    });

    let mut status = None;
    let mut timed_out = false;
    loop {
        if let Some(s) = child
            .try_wait()
            .map_err(|e| format!("等待 Codex 失败: {}", e))?
        {
            status = Some(s);
            break;
        }
        if Instant::now() >= timeout_deadline {
            timed_out = true;
            let pid = child.id();
            let _ = soft_stop(pid as i64);
            std::thread::sleep(Duration::from_secs(3));
            if let Ok(Some(_)) = child.try_wait() {
                status = Some(child.wait().map_err(|e| format!("等待 Codex 失败: {}", e))?);
                break;
            }
            let _ = child.kill();
            status = Some(child.wait().map_err(|e| format!("等待 Codex 失败: {}", e))?);
            break;
        }
        std::thread::sleep(Duration::from_millis(200));
    }

    let status = status.ok_or("Codex 退出状态未知".to_string())?;

    if let Some(handle) = stdout_handle {
        let _ = handle.join();
    }
    if let Some(handle) = stderr_handle {
        let _ = handle.join();
    }
    stop_idle.store(true, Ordering::Relaxed);
    let _ = idle_handle.join();

    let duration_s = started.elapsed().as_secs_f64();
    let exit_code = if timed_out { 124 } else { status.code().unwrap_or(-1) };
    let stdout = stdout_lines.lock().unwrap().join("\n");
    let stderr = stderr_lines.lock().unwrap().join("\n");
    let session_id = session_id.lock().unwrap().clone();
    let last_seq = *seq.lock().unwrap();

    if let Some(ref sid) = session_id {
        let state = if exit_code == 0 && !timed_out { "done" } else { "failed" };
        let _ = update_session(
            &sessions_file,
            sid,
            Some(state),
            None,
            Some(exit_code),
            Some(duration_s),
            Some(None),
        );
    }

    if let Some(viewer) = viewer.as_ref() {
        let error_type = if timed_out { "timeout" } else if exit_code == 0 { "none" } else { "exec_failed" };
        viewer.publish_event(serde_json::json!({
            "type": "codex.completed",
            "ts": now_iso(),
            "run_id": run_id.clone(),
            "session_id": session_id.clone(),
            "success": exit_code == 0 && !timed_out,
            "exit_code": exit_code,
            "error_type": error_type,
            "duration_s": duration_s,
        }));
    }

    Ok(CodexRunResult {
        success: exit_code == 0,
        session_id,
        run_id,
        exit_code,
        duration_s,
        stdout,
        stderr,
        attempts: 1,
        last_seq,
    })
}

pub fn run_codex(request: CodexRunRequest) -> Result<CodexRunResult, String> {
    let mut attempts = 0;
    let mut current_session_id = request.session_id.clone();
    let mut last_result: Option<CodexRunResult> = None;

    loop {
        attempts += 1;
        let mut req = request.clone();
        req.session_id = current_session_id.clone();
        let mut result = run_codex_once(req)?;

        if result.session_id.is_some() {
            current_session_id = result.session_id.clone();
        }

        if result.success {
            result.attempts = attempts;
            return Ok(result);
        }

        last_result = Some(result);
        if attempts >= 5 {
            break;
        }
        std::thread::sleep(Duration::from_secs(2));
    }

    let mut final_result = last_result.ok_or("Codex 执行失败且无结果")?;
    final_result.attempts = attempts;
    let hint = format!(
        "[cc-spec] Codex failed after {} attempts. You can resume with session_id={}",
        attempts,
        final_result
            .session_id
            .clone()
            .unwrap_or_else(|| "none".to_string())
    );
    if final_result.stderr.is_empty() {
        final_result.stderr = hint;
    } else {
        final_result.stderr = format!("{}\n{}", final_result.stderr, hint);
    }
    Ok(final_result)
}

pub fn pause_session(
    project_path: String,
    session_id: String,
    run_id: Option<String>,
) -> Result<(), String> {
    if session_id.trim().is_empty() {
        return Err("session_id 为空".to_string());
    }
    let project_path = PathBuf::from(&project_path);
    let sessions_file = sessions_path(&project_path);
    if !sessions_file.exists() {
        return Err("会话状态文件不存在".to_string());
    }
    let sessions_json = load_sessions(&sessions_file);
    let pid = match find_session_pid(&sessions_json, &session_id) {
        Some(pid) if pid > 0 => pid,
        Some(_) => return Err("pid 无效".to_string()),
        None => return Err("pid 未记录".to_string()),
    };
    let _ = soft_stop(pid);
    update_session(
        &sessions_file,
        &session_id,
        Some("idle"),
        Some("paused"),
        None,
        None,
        Some(None),
    )?;
    if let Some(run_id) = run_id {
        if let Some(viewer) = get_viewer_client(&project_path) {
            viewer.publish_event(serde_json::json!({
                "type": "codex.completed",
                "ts": now_iso(),
                "run_id": run_id,
                "session_id": session_id,
                "success": false,
                "exit_code": 130,
                "error_type": "paused",
                "duration_s": 0.0,
            }));
        }
    }
    Ok(())
}

pub fn soft_stop(pid: i64) -> Result<(), String> {
    let pid_str = pid.to_string();
    if cfg!(windows) {
        let _ = Command::new("taskkill")
            .args(["/PID", &pid_str])
            .output()
            .map_err(|e| format!("soft_stop 失败: {}", e))?;
    } else {
        let _ = Command::new("kill")
            .args(["-INT", &pid_str])
            .status()
            .map_err(|e| format!("soft_stop 失败: {}", e))?;
    }
    Ok(())
}

pub fn force_kill(pid: i64) -> Result<(), String> {
    let pid_str = pid.to_string();
    if cfg!(windows) {
        let output = Command::new("taskkill")
            .args(["/PID", &pid_str, "/F"])
            .output()
            .map_err(|e| format!("force_kill 失败: {}", e))?;
        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(format!("force_kill 失败: {}", stderr.trim()));
        }
    } else {
        let status = Command::new("kill")
            .args(["-9", &pid_str])
            .status()
            .map_err(|e| format!("force_kill 失败: {}", e))?;
        if !status.success() {
            return Err("force_kill 失败".to_string());
        }
    }
    Ok(())
}
