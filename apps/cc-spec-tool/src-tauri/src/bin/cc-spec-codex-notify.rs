// cc-spec-codex-notify - Codex notify hook receiver
//
// 用法（由 Codex CLI 调用）：
//   cc-spec-codex-notify --endpoint http://127.0.0.1:38888 --session-id <sid> --project-root <path> <NOTIFICATION_JSON>
//
// Codex 会把通知 JSON 作为最后一个 argv 传入（见 reference/codex/docs/config.md#notify）。

use serde_json::Value;
use std::io::Write;
use std::net::TcpStream;
use std::time::Duration;

fn now_iso() -> String {
    chrono::Utc::now().to_rfc3339()
}

fn parse_endpoint(endpoint: &str) -> Option<(String, u16)> {
    let mut s = endpoint.trim();
    if let Some(rest) = s.strip_prefix("http://") {
        s = rest;
    } else if let Some(rest) = s.strip_prefix("https://") {
        s = rest;
    }
    let s = s.trim_end_matches('/');
    let mut parts = s.split(':');
    let host = parts.next()?.trim().to_string();
    let port = parts.next()?.trim().parse::<u16>().ok()?;
    Some((host, port))
}

fn post_ingest(host: &str, port: u16, body: &str) -> std::io::Result<()> {
    let addr = format!("{}:{}", host, port);
    let mut stream = TcpStream::connect(addr)?;
    stream.set_write_timeout(Some(Duration::from_secs(1))).ok();
    let request = format!(
        "POST /ingest HTTP/1.1\r\nHost: {}:{}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        host,
        port,
        body.as_bytes().len(),
        body
    );
    stream.write_all(request.as_bytes())?;
    Ok(())
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let mut endpoint: Option<String> = None;
    let mut session_id: Option<String> = None;
    let mut project_root: Option<String> = None;
    let mut json_arg: Option<String> = None;

    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--endpoint" if i + 1 < args.len() => {
                endpoint = Some(args[i + 1].clone());
                i += 2;
            }
            "--session-id" if i + 1 < args.len() => {
                session_id = Some(args[i + 1].clone());
                i += 2;
            }
            "--project-root" if i + 1 < args.len() => {
                project_root = Some(args[i + 1].clone());
                i += 2;
            }
            _ => {
                // Codex 传入的通知 JSON 通常是最后一个参数；这里采用“遇到未知参数则视为 JSON”策略。
                json_arg = Some(args[i].clone());
                i += 1;
            }
        }
    }

    let endpoint = match endpoint {
        Some(v) => v,
        None => return,
    };
    let session_id = match session_id {
        Some(v) if !v.trim().is_empty() => v,
        _ => return,
    };
    let json_arg = match json_arg {
        Some(v) => v,
        None => return,
    };

    let (host, port) = match parse_endpoint(&endpoint) {
        Some(v) => v,
        None => return,
    };

    let parsed: Value = match serde_json::from_str(&json_arg) {
        Ok(v) => v,
        Err(_) => return,
    };

    let body = serde_json::json!({
        "type": "codex.turn_complete",
        "ts": now_iso(),
        "session_id": session_id,
        "project_root": project_root.unwrap_or_default(),
        "thread_id": parsed.get("thread-id").cloned().unwrap_or(Value::Null),
        "turn_id": parsed.get("turn-id").cloned().unwrap_or(Value::Null),
        "cwd": parsed.get("cwd").cloned().unwrap_or(Value::Null),
        "input_messages": parsed.get("input-messages").cloned().unwrap_or(Value::Null),
        "last_assistant_message": parsed.get("last-assistant-message").cloned().unwrap_or(Value::Null),
    });

    if let Ok(raw) = serde_json::to_string(&body) {
        let _ = post_ingest(&host, port, &raw);
    }
}

