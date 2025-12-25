// claude.rs - Claude Code (CC) 进程管理
//
// 功能:
// - 路径检测 (settings custom_path > CLAUDE_PATH > which > npm global > common paths)
// - 进程管理 (start, stop, send message)
// - 输出解析 (stream-json 格式映射到 agent:* 事件)
// - 使用 tokio 异步进程和 mpsc channel 通信

use once_cell::sync::Lazy;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::env;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, Command};
use tokio::sync::{mpsc, RwLock};
use tauri::Emitter;

// ============================================================================
// 路径检测
// ============================================================================

fn validate_path(path: &str) -> bool {
    PathBuf::from(path).exists()
}

/// 检测 Claude CLI 路径
/// 优先级: custom_path > CLAUDE_PATH > which/where > npm global > 常见路径
pub fn detect_claude_path(custom_path: Option<&str>) -> Result<String, String> {
    // 1. settings 中的自定义路径
    if let Some(path) = custom_path {
        if !path.is_empty() && path != "auto" && validate_path(path) {
            return Ok(path.to_string());
        }
    }

    // 2. 环境变量 CLAUDE_PATH
    if let Ok(path) = env::var("CLAUDE_PATH") {
        if validate_path(&path) {
            return Ok(path);
        }
    }

    // 3. which/where 命令
    let cmd = if cfg!(windows) { "where" } else { "which" };
    if let Ok(output) = std::process::Command::new(cmd).arg("claude").output() {
        if output.status.success() {
            let path = String::from_utf8_lossy(&output.stdout)
                .lines()
                .next()
                .unwrap_or("")
                .trim()
                .to_string();
            if !path.is_empty() && validate_path(&path) {
                return Ok(path);
            }
        }
    }

    // 4. npm 全局目录
    if let Ok(output) = std::process::Command::new("npm")
        .args(["config", "get", "prefix"])
        .output()
    {
        if output.status.success() {
            let prefix = String::from_utf8_lossy(&output.stdout).trim().to_string();
            let npm_path = if cfg!(windows) {
                format!("{}\\claude.cmd", prefix)
            } else {
                format!("{}/bin/claude", prefix)
            };
            if validate_path(&npm_path) {
                return Ok(npm_path);
            }
        }
    }

    // 5. 常见安装位置
    let common_paths: Vec<Option<String>> = if cfg!(windows) {
        vec![
            env::var("APPDATA")
                .map(|p| format!("{}\\npm\\claude.cmd", p))
                .ok(),
            env::var("LOCALAPPDATA")
                .map(|p| format!("{}\\npm\\claude.cmd", p))
                .ok(),
        ]
    } else {
        vec![
            Some("/usr/local/bin/claude".to_string()),
            Some("/opt/homebrew/bin/claude".to_string()),
            env::var("HOME")
                .map(|h| format!("{}/.local/bin/claude", h))
                .ok(),
            env::var("HOME")
                .map(|h| format!("{}/.npm-global/bin/claude", h))
                .ok(),
        ]
    };

    for path in common_paths.into_iter().flatten() {
        if validate_path(&path) {
            return Ok(path);
        }
    }

    Err("Claude CLI not found. Please install Claude CLI or set a custom path in settings.".to_string())
}

#[tauri::command]
pub async fn cmd_detect_claude_path() -> Result<String, String> {
    detect_claude_path(None)
}

#[tauri::command]
pub async fn cmd_validate_claude_path(path: String) -> Result<bool, String> {
    Ok(validate_path(&path))
}

// ============================================================================
// 会话管理
// ============================================================================

/// 会话状态
#[derive(Clone, Debug, Serialize)]
pub enum SessionStatus {
    Running,
    Completed,
    Error,
    Stopped,
}

/// 会话信息
#[derive(Clone, Debug, Serialize)]
pub struct SessionInfo {
    pub session_id: String,
    pub run_id: String,
    pub project_path: String,
    pub status: SessionStatus,
    pub created_at: String,
    pub pid: Option<u32>,
}

/// 活跃的 Claude 会话
struct ActiveSession {
    child: Child,
    project_path: String,
    run_id: String,
    stdin_tx: mpsc::Sender<String>,
    status: SessionStatus,
    created_at: chrono::DateTime<chrono::Utc>,
}

/// 全局会话管理器
static SESSIONS: Lazy<RwLock<HashMap<String, ActiveSession>>> =
    Lazy::new(|| RwLock::new(HashMap::new()));

/// CC 输出事件
#[derive(Clone, Debug, Serialize)]
pub struct AgentEvent {
    pub event_type: String,
    pub source: String,
    pub session_id: String,
    pub run_id: String,
    pub data: serde_json::Value,
}

/// CC 输出类型映射到统一事件
pub fn map_claude_event(raw: &str, session_id: &str, run_id: &str) -> Option<AgentEvent> {
    let json: serde_json::Value = serde_json::from_str(raw).ok()?;
    let cc_type = json.get("type")?.as_str()?;

    let event_type = match cc_type {
        "system" => "agent:started",
        "assistant" => {
            if json.get("tool_use").is_some() {
                "agent:tool_request"
            } else {
                "agent:stream"
            }
        }
        "result" => {
            if json
                .get("success")
                .and_then(|v| v.as_bool())
                .unwrap_or(false)
            {
                "agent:completed"
            } else {
                "agent:error"
            }
        }
        "user" => "agent:user_input",
        "error" => "agent:error",
        _ => return None,
    };

    Some(AgentEvent {
        event_type: event_type.to_string(),
        source: "claude".to_string(),
        session_id: session_id.to_string(),
        run_id: run_id.to_string(),
        data: json,
    })
}

/// 启动 Claude 会话响应
#[derive(Clone, Debug, Serialize)]
pub struct StartClaudeResponse {
    pub session_id: String,
    pub run_id: String,
    pub pid: Option<u32>,
}

#[tauri::command]
pub async fn start_claude(
    project_path: String,
    message: String,
    custom_claude_path: Option<String>,
    app_handle: tauri::AppHandle,
) -> Result<StartClaudeResponse, String> {
    let claude_path = detect_claude_path(custom_claude_path.as_deref())?;

    let mut cmd = Command::new(&claude_path);
    cmd.current_dir(&project_path)
        .args(["--print", "--output-format", "stream-json"])
        .env("CC_SPEC_IN_AGENT", "1")
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .kill_on_drop(true);

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("Failed to start Claude: {}", e))?;

    let pid = child.id();
    let session_id = uuid::Uuid::new_v4().to_string();
    let run_id = uuid::Uuid::new_v4().to_string();

    // 创建 stdin writer channel
    let (stdin_tx, mut stdin_rx) = mpsc::channel::<String>(32);

    // 获取 stdin handle
    let mut stdin = child
        .stdin
        .take()
        .ok_or_else(|| "Failed to get stdin".to_string())?;

    // 启动 stdin writer task
    let sid_clone = session_id.clone();
    tokio::spawn(async move {
        while let Some(msg) = stdin_rx.recv().await {
            if stdin.write_all(msg.as_bytes()).await.is_err() {
                break;
            }
            if stdin.write_all(b"\n").await.is_err() {
                break;
            }
            if stdin.flush().await.is_err() {
                break;
            }
        }
        // Channel 关闭，stdin 自动关闭
        drop(stdin);
    });

    // 写入初始消息
    stdin_tx
        .send(message)
        .await
        .map_err(|e| format!("Failed to send initial message: {}", e))?;

    // 启动 stdout reader task
    if let Some(stdout) = child.stdout.take() {
        let handle = app_handle.clone();
        let sid = session_id.clone();
        let rid = run_id.clone();
        tokio::spawn(async move {
            let reader = BufReader::new(stdout);
            let mut lines = reader.lines();
            
            while let Ok(Some(line)) = lines.next_line().await {
                if let Some(event) = map_claude_event(&line, &sid, &rid) {
                    let event_type = event.event_type.clone();
                    let _ = handle.emit(&event_type, &event);
                    let _ = handle.emit("agent:event", &event);
                }
            }
            
            // 输出结束，更新会话状态
            let mut sessions = SESSIONS.write().await;
            if let Some(session) = sessions.get_mut(&sid) {
                session.status = SessionStatus::Completed;
            }
            
            let _ = handle.emit(
                "agent:session_ended",
                serde_json::json!({
                    "session_id": sid,
                    "run_id": rid,
                    "source": "claude"
                }),
            );
        });
    }

    // 启动 stderr reader task
    if let Some(stderr) = child.stderr.take() {
        let sid = session_id.clone();
        let handle = app_handle.clone();
        tokio::spawn(async move {
            let reader = BufReader::new(stderr);
            let mut lines = reader.lines();
            
            while let Ok(Some(line)) = lines.next_line().await {
                if !line.trim().is_empty() {
                    let _ = handle.emit(
                        "agent:stderr",
                        serde_json::json!({
                            "session_id": sid,
                            "source": "claude",
                            "text": line
                        }),
                    );
                }
            }
        });
    }

    // 保存会话
    {
        let session = ActiveSession {
            child,
            project_path: project_path.clone(),
            run_id: run_id.clone(),
            stdin_tx,
            status: SessionStatus::Running,
            created_at: chrono::Utc::now(),
        };
        SESSIONS.write().await.insert(session_id.clone(), session);
    }

    Ok(StartClaudeResponse {
        session_id,
        run_id,
        pid,
    })
}

#[tauri::command]
pub async fn send_claude_message(session_id: String, message: String) -> Result<(), String> {
    let sessions = SESSIONS.read().await;
    let session = sessions
        .get(&session_id)
        .ok_or_else(|| format!("Session {} not found", session_id))?;

    session
        .stdin_tx
        .send(message)
        .await
        .map_err(|e| format!("Failed to send message: {}", e))?;

    Ok(())
}

#[tauri::command]
pub async fn stop_claude(session_id: String) -> Result<(), String> {
    let mut sessions = SESSIONS.write().await;

    if let Some(mut session) = sessions.remove(&session_id) {
        // 1. 关闭 stdin channel 触发优雅退出
        drop(session.stdin_tx);

        // 2. 等待短时间让进程优雅退出
        tokio::time::sleep(tokio::time::Duration::from_secs(2)).await;

        // 3. 检查是否已退出，否则强制终止
        match session.child.try_wait() {
            Ok(Some(_status)) => {
                // 进程已退出
                Ok(())
            }
            Ok(None) => {
                // 进程仍在运行，强制终止
                session
                    .child
                    .kill()
                    .await
                    .map_err(|e| format!("Failed to kill process: {}", e))?;
                Ok(())
            }
            Err(e) => Err(format!("Error checking process status: {}", e)),
        }
    } else {
        // 会话不存在不算错误
        Ok(())
    }
}

/// 优雅停止会话（可配置等待时间）
#[tauri::command]
pub async fn graceful_stop_claude(
    session_id: String,
    wait_seconds: Option<u64>,
) -> Result<(), String> {
    let mut sessions = SESSIONS.write().await;

    if let Some(mut session) = sessions.remove(&session_id) {
        let wait_time = wait_seconds.unwrap_or(3);
        
        // 1. 关闭 stdin channel
        drop(session.stdin_tx);
        session.status = SessionStatus::Stopped;

        // 2. 等待指定时间
        tokio::time::sleep(tokio::time::Duration::from_secs(wait_time)).await;

        // 3. 检查并强制终止
        match session.child.try_wait() {
            Ok(Some(_)) => Ok(()),
            Ok(None) => {
                session.child.kill().await.ok();
                Ok(())
            }
            Err(e) => Err(format!("Error: {}", e)),
        }
    } else {
        Ok(())
    }
}

/// 获取会话信息
#[tauri::command]
pub async fn get_claude_session(session_id: String) -> Result<Option<SessionInfo>, String> {
    let sessions = SESSIONS.read().await;
    
    if let Some(session) = sessions.get(&session_id) {
        Ok(Some(SessionInfo {
            session_id: session_id.clone(),
            run_id: session.run_id.clone(),
            project_path: session.project_path.clone(),
            status: session.status.clone(),
            created_at: session.created_at.to_rfc3339(),
            pid: session.child.id(),
        }))
    } else {
        Ok(None)
    }
}

/// 获取活跃会话列表
#[tauri::command]
pub async fn list_claude_sessions() -> Result<Vec<SessionInfo>, String> {
    let sessions = SESSIONS.read().await;
    
    let list: Vec<SessionInfo> = sessions
        .iter()
        .map(|(id, session)| SessionInfo {
            session_id: id.clone(),
            run_id: session.run_id.clone(),
            project_path: session.project_path.clone(),
            status: session.status.clone(),
            created_at: session.created_at.to_rfc3339(),
            pid: session.child.id(),
        })
        .collect();
    
    Ok(list)
}

/// 检查会话是否存在
#[tauri::command]
pub async fn is_claude_session_active(session_id: String) -> Result<bool, String> {
    let sessions = SESSIONS.read().await;
    Ok(sessions.contains_key(&session_id))
}

/// 获取活跃会话数量
#[tauri::command]
pub async fn get_claude_session_count() -> Result<usize, String> {
    let sessions = SESSIONS.read().await;
    Ok(sessions.len())
}
