// codex_sessions.rs - Codex 交互会话（终端/ConPTY relay）管理与自动重试
//
// 设计目标（按用户讨论的“简单好用”收敛）：
// - 用户在原生终端窗口里原生操作 Codex（TUI），tool 不解析/渲染 TUI。
// - tool 负责：会话创建、控制消息广播（send/pause/retry/kill）、监控退出并在“崩溃/未知退出且存在 pending 调度请求”时自动重试。
// - Claude Code 只需要最终结果：由 `codex.notify` hook 触发 `codex.turn_complete` 事件；tool 再补发 `codex.managed.turn_complete`（带 request_id）便于调度方订阅。

use once_cell::sync::Lazy;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::io::Write;
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{Duration, SystemTime};
use uuid::Uuid;

const DEFAULT_HOST: &str = "127.0.0.1";
const AUTO_RETRY_MAX: u32 = 3;

static SUPERVISOR: Lazy<Mutex<HashMap<String, SupervisorSession>>> =
    Lazy::new(|| Mutex::new(HashMap::new()));
static SESSIONS_FILE_LOCK: Lazy<Mutex<()>> = Lazy::new(|| Mutex::new(()));

#[derive(Clone, Debug)]
struct PendingRequest {
    id: String,
    prompt: String,
    requested_by: String,
    created_at_ms: u64,
}

#[derive(Clone, Debug, Default)]
struct SupervisorSession {
    project_root: Option<String>,
    pending: Option<PendingRequest>,
    retry_count: u32,
    last_stop_requested_by: Option<String>,
}

fn now_iso() -> String {
    chrono::Utc::now().to_rfc3339()
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .unwrap_or(Duration::from_secs(0))
        .as_millis() as u64
}

fn sessions_path(project_root: &str) -> PathBuf {
    PathBuf::from(project_root)
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
    json!({
        "schema_version": 1,
        "updated_at": "",
        "sessions": {}
    })
}

fn save_sessions(path: &PathBuf, mut value: Value) -> Result<(), String> {
    if let Some(obj) = value.as_object_mut() {
        obj.insert("schema_version".to_string(), Value::from(1));
        obj.insert("updated_at".to_string(), Value::from(now_iso()));
        obj.entry("sessions".to_string())
            .or_insert_with(|| Value::from(serde_json::Map::new()));
    }
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| format!("创建 sessions 目录失败: {}", e))?;
    }
    let tmp = path.with_extension("json.tmp");
    std::fs::write(&tmp, serde_json::to_string_pretty(&value).unwrap())
        .map_err(|e| format!("写入 sessions 临时文件失败: {}", e))?;
    // Windows: rename 不能覆盖已存在文件（WinError 183）。
    // 这里先尝试 rename（原子替换），失败且目标存在时降级为 copy+remove。
    match std::fs::rename(&tmp, path) {
        Ok(()) => {}
        Err(err) => {
            if path.exists() {
                std::fs::copy(&tmp, path).map_err(|e| format!("写入 sessions 失败: {}", e))?;
                let _ = std::fs::remove_file(&tmp);
            } else {
                return Err(format!("写入 sessions 失败: {}", err));
            }
        }
    }
    Ok(())
}

fn upsert_session_record(project_root: &str, session_id: &str, patch: Value) -> Result<(), String> {
    if project_root.trim().is_empty() || session_id.trim().is_empty() {
        return Ok(());
    }
    let _guard = SESSIONS_FILE_LOCK.lock().unwrap();
    let path = sessions_path(project_root);
    let mut data = load_sessions(&path);
    let now = now_iso();

    let sessions = data
        .get_mut("sessions")
        .and_then(|v| v.as_object_mut())
        .ok_or("sessions 字段缺失")?;

    let record = sessions.entry(session_id.to_string()).or_insert_with(|| {
        json!({
            "session_id": session_id,
            "created_at": now,
        })
    });

    if let Some(obj) = record.as_object_mut() {
        if let Some(patch_obj) = patch.as_object() {
            for (k, v) in patch_obj {
                obj.insert(k.to_string(), v.clone());
            }
        }
        obj.insert("updated_at".to_string(), Value::from(now_iso()));
        obj.entry("kind".to_string()).or_insert(Value::from("terminal"));
    }

    save_sessions(&path, data)
}

/// 从 sessions.json 中删除指定会话记录。
pub fn delete_session_record(project_root: &str, session_id: &str) -> Result<(), String> {
    if project_root.trim().is_empty() || session_id.trim().is_empty() {
        return Err("project_root 或 session_id 为空".to_string());
    }
    let _guard = SESSIONS_FILE_LOCK.lock().unwrap();
    let path = sessions_path(project_root);
    let mut data = load_sessions(&path);

    let sessions = data
        .get_mut("sessions")
        .and_then(|v| v.as_object_mut())
        .ok_or("sessions 字段缺失")?;

    if sessions.remove(session_id).is_none() {
        return Err(format!("会话 {} 不存在", session_id));
    }

    // 同时清理 supervisor 中的记录
    {
        let mut guard = SUPERVISOR.lock().unwrap();
        guard.remove(session_id);
    }

    save_sessions(&path, data)
}

fn publish_sse_event<F: Fn(String)>(event_name: &str, body: &Value, publish: F) {
    let payload = serde_json::to_string(body).unwrap_or_else(|_| "{}".to_string());
    let sse = format!("event: {}\ndata: {}\n\n", event_name, payload);
    publish(sse);
}

fn parse_string(payload: &Value, key: &str) -> Option<String> {
    payload.get(key).and_then(|v| v.as_str()).map(|s| s.to_string())
}

fn should_auto_retry(exit_reason: &str) -> bool {
    matches!(exit_reason, "crash_or_unknown" | "crash" | "unknown")
}

fn supervisor_upsert(session_id: &str) -> SupervisorSession {
    let mut guard = SUPERVISOR.lock().unwrap();
    guard.entry(session_id.to_string()).or_default().clone()
}

fn supervisor_update<F: FnOnce(&mut SupervisorSession)>(session_id: &str, f: F) {
    let mut guard = SUPERVISOR.lock().unwrap();
    let entry = guard.entry(session_id.to_string()).or_default();
    f(entry);
}

fn supervisor_take_pending(session_id: &str) -> Option<PendingRequest> {
    let mut guard = SUPERVISOR.lock().unwrap();
    guard.get_mut(session_id).and_then(|s| s.pending.take())
}

fn supervisor_peek_pending(session_id: &str) -> Option<PendingRequest> {
    let guard = SUPERVISOR.lock().unwrap();
    guard.get(session_id).and_then(|s| s.pending.clone())
}

fn supervisor_inc_retry(session_id: &str) -> u32 {
    let mut guard = SUPERVISOR.lock().unwrap();
    let entry = guard.entry(session_id.to_string()).or_default();
    entry.retry_count += 1;
    entry.retry_count
}

fn supervisor_reset_retry(session_id: &str) {
    supervisor_update(session_id, |s| s.retry_count = 0);
}

fn post_ingest(host: &str, port: u16, body: &Value) -> Result<(), String> {
    let payload = serde_json::to_string(body).map_err(|e| format!("序列化失败: {}", e))?;
    let addr = format!("{}:{}", host, port);
    let mut stream =
        TcpStream::connect(&addr).map_err(|e| format!("连接 ingest 失败 {}: {}", addr, e))?;
    let request = format!(
        "POST /ingest HTTP/1.1\r\nHost: {}:{}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        host,
        port,
        payload.len(),
        payload
    );
    stream
        .write_all(request.as_bytes())
        .map_err(|e| format!("写入 ingest 失败: {}", e))?;
    Ok(())
}

/// 将 tool 的控制消息发布到本地 ingest（进而广播到 /events，由 relay 接收）。
pub fn publish_control_to(
    host: &str,
    port: u16,
    project_root: &str,
    session_id: &str,
    body: Value,
) -> Result<(), String> {
    let mut full = body;
    if let Some(obj) = full.as_object_mut() {
        obj.insert("project_root".to_string(), Value::from(project_root.to_string()));
        obj.insert("session_id".to_string(), Value::from(session_id.to_string()));
        obj.entry("ts".to_string()).or_insert(Value::from(now_iso()));
    }
    post_ingest(host, port, &full)
}

/// 处理 ingest 事件：更新 sessions.json、维护 pending、并在必要时自动重试（向 /events 广播 codex.control）。
pub fn handle_ingest_event<F: Fn(String)>(payload: &Value, publish: F) {
    let event_type = payload.get("type").and_then(|v| v.as_str()).unwrap_or("");
    let session_id = payload
        .get("session_id")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let project_root = payload
        .get("project_root")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    if session_id.is_empty() {
        return;
    }

    match event_type {
        "codex.session.started" => {
            let pid = payload.get("pid").and_then(|v| v.as_u64()).map(|v| v as i64);
            let _ = upsert_session_record(
                &project_root,
                &session_id,
                json!({
                    "state": "running",
                    "pid": pid,
                    "kind": "terminal",
                    "mode": "interactive",
                    "last_exit_reason": Value::Null,
                    "exit_code": Value::Null,
                }),
            );
            supervisor_update(&session_id, |s| {
                if !project_root.trim().is_empty() {
                    s.project_root = Some(project_root.clone());
                }
            });
        }
        "codex.session.exited" => {
            let exit_code = payload.get("exit_code").and_then(|v| v.as_i64());
            let exit_reason = payload
                .get("exit_reason")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown")
                .to_string();
            let _ = upsert_session_record(
                &project_root,
                &session_id,
                json!({
                    "state": "exited",
                    "exit_code": exit_code,
                    "last_exit_reason": exit_reason,
                }),
            );

            // 自动重试：仅当存在 pending 请求且退出原因属于 crash/unknown
            let pending = supervisor_peek_pending(&session_id);
            if let Some(pending) = pending {
                if should_auto_retry(&exit_reason) {
                    let retry_n = supervisor_inc_retry(&session_id);
                    if retry_n <= AUTO_RETRY_MAX {
                        let ctrl = json!({
                            "type": "codex.control",
                            "ts": now_iso(),
                            "project_root": project_root,
                            "session_id": session_id,
                            "action": "retry",
                            "requested_by": "tool",
                            "request_id": pending.id,
                            "text": pending.prompt,
                        });
                        publish_sse_event("codex.control", &ctrl, &publish);
                        let note = json!({
                            "type": "codex.retry_scheduled",
                            "ts": now_iso(),
                            "session_id": session_id,
                            "request_id": pending.id,
                            "attempt": retry_n,
                        });
                        publish_sse_event("codex.retry_scheduled", &note, publish);
                    }
                }
            }
        }
        "codex.turn_complete" => {
            let message = payload
                .get("last_assistant_message")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let thread_id = parse_string(payload, "thread_id");
            let turn_id = parse_string(payload, "turn_id");
            let _ = upsert_session_record(
                &project_root,
                &session_id,
                json!({
                    "message": message,
                    "thread_id": thread_id,
                    "turn_id": turn_id,
                    "state": "running",
                }),
            );

            // 将本次完成与 pending 关联（best-effort：取当前 pending）
            if let Some(pending) = supervisor_take_pending(&session_id) {
                supervisor_reset_retry(&session_id);
                let managed = json!({
                    "type": "codex.managed.turn_complete",
                    "ts": now_iso(),
                    "session_id": session_id,
                    "request_id": pending.id,
                    "requested_by": pending.requested_by,
                    "created_at_ms": pending.created_at_ms,
                    "thread_id": payload.get("thread_id").cloned().unwrap_or(Value::Null),
                    "turn_id": payload.get("turn_id").cloned().unwrap_or(Value::Null),
                    "cwd": payload.get("cwd").cloned().unwrap_or(Value::Null),
                    "input_messages": payload.get("input_messages").cloned().unwrap_or(Value::Null),
                    "last_assistant_message": payload.get("last_assistant_message").cloned().unwrap_or(Value::Null),
                });
                publish_sse_event("codex.managed.turn_complete", &managed, publish);
            }
        }
        "codex.control" => {
            // 外部（Claude Code）也可能直接 POST /ingest，这里做一次 best-effort 记录。
            let action = payload.get("action").and_then(|v| v.as_str()).unwrap_or("");
            let requested_by = payload
                .get("requested_by")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown")
                .to_string();
            if action == "send_input" {
                let text = payload.get("text").and_then(|v| v.as_str()).unwrap_or("").to_string();
                let request_id = payload
                    .get("request_id")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string();
                if !text.trim().is_empty() {
                    supervisor_update(&session_id, |s| {
                        if !project_root.trim().is_empty() {
                            s.project_root = Some(project_root.clone());
                        }
                        s.pending = Some(PendingRequest {
                            id: if request_id.is_empty() {
                                Uuid::new_v4().to_string()
                            } else {
                                request_id
                            },
                            prompt: text,
                            requested_by,
                            created_at_ms: now_ms(),
                        });
                    });
                }
            } else if matches!(action, "pause" | "kill" | "restart" | "retry") {
                supervisor_update(&session_id, |s| s.last_stop_requested_by = Some(requested_by));
            }
        }
        _ => {}
    }
}

#[derive(Clone, Debug)]
pub struct LaunchResult {
    pub session_id: String,
}

fn dev_sidecar_candidates(manifest_dir: &Path, name: &str) -> Vec<PathBuf> {
    let mut out = Vec::new();
    let sidecar_dir = manifest_dir.join("sidecar");
    if cfg!(windows) {
        out.push(sidecar_dir.join(format!("{}.exe", name)));
        // 开发时优先使用本地构建产物，避免 sidecar 目录里的预构建二进制过期导致行为不一致。
        out.push(manifest_dir.join("target").join("debug").join(format!("{}.exe", name)));
        out.push(
            manifest_dir
                .join("target")
                .join("release")
                .join(format!("{}.exe", name)),
        );
        // 支持 Tauri externalBin 的 target-triple 命名：<name>-<triple>.exe
        if let Ok(entries) = std::fs::read_dir(&sidecar_dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path
                    .file_name()
                    .and_then(|v| v.to_str())
                    .map(|s| s.starts_with(&format!("{}-", name)) && s.ends_with(".exe"))
                    .unwrap_or(false)
                {
                    out.push(path);
                }
            }
        }
    } else {
        out.push(sidecar_dir.join(name));
        out.push(manifest_dir.join("target").join("debug").join(name));
        out.push(manifest_dir.join("target").join("release").join(name));
    }
    out
}

pub fn resolve_sidecar_binary(app_handle: &tauri::AppHandle, name: &str) -> Result<PathBuf, String> {
    // 生产模式：使用打包资源目录
    #[cfg(not(debug_assertions))]
    {
        use tauri::Manager;
        let file_name = if cfg!(windows) {
            format!("{}.exe", name)
        } else {
            name.to_string()
        };
        return app_handle
            .path()
            .resource_dir()
            .map_err(|e| format!("获取资源目录失败: {}", e))?
            .join("sidecar")
            .join(file_name)
            .canonicalize()
            .map_err(|e| format!("sidecar 路径不存在: {}", e));
    }

    // 开发模式：优先从 src-tauri/sidecar 或 src-tauri/target/* 查找
    #[cfg(debug_assertions)]
    {
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        for candidate in dev_sidecar_candidates(&manifest_dir, name) {
            if candidate.exists() {
                return candidate
                    .canonicalize()
                    .map_err(|e| format!("解析 sidecar 路径失败: {}", e));
            }
        }
        Err(format!(
            "未找到 sidecar 可执行文件: {}（请先构建 relay/notifier sidecar）",
            name
        ))
    }
}

/// 生成并登记一个“终端交互式”Codex session，返回 session_id。
pub fn create_terminal_session(project_root: &str) -> Result<LaunchResult, String> {
    if project_root.trim().is_empty() {
        return Err("project_root 为空".to_string());
    }
    let session_id = Uuid::new_v4().to_string();
    upsert_session_record(
        project_root,
        &session_id,
        json!({
            "state": "starting",
            "kind": "terminal",
            "mode": "interactive",
            "task_summary": "codex (interactive)".to_string(),
            "pid": Value::Null,
            "exit_code": Value::Null,
            "last_exit_reason": Value::Null,
        }),
    )?;
    supervisor_update(&session_id, |s| {
        s.project_root = Some(project_root.to_string());
    });
    Ok(LaunchResult { session_id })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn create_temp_project_root() -> PathBuf {
        let dir = std::env::temp_dir().join(format!("cc-spec-tool-test-{}", Uuid::new_v4()));
        std::fs::create_dir_all(&dir).expect("create temp project root");
        dir
    }

    #[test]
    fn create_terminal_session_persists_even_when_sessions_file_exists() {
        let project_root = create_temp_project_root();
        let project_root_str = project_root.to_string_lossy().to_string();

        let first = create_terminal_session(&project_root_str).expect("create first session");
        let second = create_terminal_session(&project_root_str).expect("create second session");

        let raw = std::fs::read_to_string(sessions_path(&project_root_str))
            .expect("read sessions.json");
        let value: Value = serde_json::from_str(&raw).expect("parse sessions.json");
        let sessions = value
            .get("sessions")
            .and_then(|v| v.as_object())
            .expect("sessions object");

        assert!(sessions.contains_key(&first.session_id));
        assert!(sessions.contains_key(&second.session_id));
        assert!(sessions.len() >= 2);

        let _ = std::fs::remove_dir_all(&project_root);
    }
}

pub fn set_pending_request(session_id: &str, project_root: &str, requested_by: &str, prompt: &str) -> String {
    let request_id = Uuid::new_v4().to_string();
    supervisor_update(session_id, |s| {
        s.project_root = Some(project_root.to_string());
        s.pending = Some(PendingRequest {
            id: request_id.clone(),
            prompt: prompt.to_string(),
            requested_by: requested_by.to_string(),
            created_at_ms: now_ms(),
        });
    });
    request_id
}

#[cfg(windows)]
const CREATE_NEW_CONSOLE: u32 = 0x00000010;

/// 启动 relay（原生终端窗口），并将 session_id/project_root/ingest 信息传入。
pub fn launch_relay_terminal(
    app_handle: &tauri::AppHandle,
    project_root: &str,
    host: &str,
    port: u16,
    session_id: &str,
    codex_bin: Option<&str>,
) -> Result<(), String> {
    let relay_path = resolve_sidecar_binary(app_handle, "cc-spec-codex-relay")?;

    let mut cmd = std::process::Command::new(&relay_path);
    cmd.current_dir(project_root);
    cmd.args([
        "--viewer-host",
        host,
        "--viewer-port",
        &port.to_string(),
        "--project-root",
        project_root,
        "--session-id",
        session_id,
    ]);

    // 传递 codex 可执行文件路径
    if let Some(bin) = codex_bin {
        cmd.args(["--codex-bin", bin]);
    }

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(CREATE_NEW_CONSOLE);
    }

    cmd.spawn()
        .map_err(|e| format!("启动 codex relay 失败: {}", e))?;
    Ok(())
}
