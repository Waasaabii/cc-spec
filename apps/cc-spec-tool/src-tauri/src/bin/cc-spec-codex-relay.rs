// cc-spec-codex-relay - 原生终端中的 Codex 交互会话桥接
//
// 目标：
// - 在终端中“像原生一样”运行 Codex TUI（通过 ConPTY/PTY）。
// - 监听 tools viewer 的 /events，接收 codex.control 注入输入/重试/暂停/停止。
// - 通过 /ingest 上报 session.started / session.exited；并通过 Codex notify hook 上报 turn_complete（由 cc-spec-codex-notify 负责）。

use portable_pty::{native_pty_system, CommandBuilder, PtySize};
use serde_json::Value;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpStream;
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, SystemTime};
use terminal_size::{terminal_size, Height, Width};

fn now_iso() -> String {
    chrono::Utc::now().to_rfc3339()
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .unwrap_or(Duration::from_secs(0))
        .as_millis() as u64
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

fn publish_event(host: &str, port: u16, payload: &Value) {
    if let Ok(raw) = serde_json::to_string(payload) {
        let _ = post_ingest(host, port, &raw);
    }
}

fn connect_events(host: &str, port: u16) -> std::io::Result<TcpStream> {
    let addr = format!("{}:{}", host, port);
    let mut stream = TcpStream::connect(addr)?;
    stream.set_read_timeout(Some(Duration::from_secs(15))).ok();
    let req = format!(
        "GET /events HTTP/1.1\r\nHost: {}:{}\r\nAccept: text/event-stream\r\nConnection: keep-alive\r\n\r\n",
        host, port
    );
    stream.write_all(req.as_bytes())?;
    Ok(stream)
}

#[derive(Clone, Debug)]
struct Args {
    viewer_host: String,
    viewer_port: u16,
    project_root: String,
    session_id: String,
    codex_bin: String,
}

fn parse_args() -> Option<Args> {
    let argv: Vec<String> = std::env::args().collect();
    let mut viewer_host: Option<String> = None;
    let mut viewer_port: Option<u16> = None;
    let mut project_root: Option<String> = None;
    let mut session_id: Option<String> = None;
    let mut codex_bin: Option<String> = None;

    let mut i = 1;
    while i < argv.len() {
        match argv[i].as_str() {
            "--viewer-host" if i + 1 < argv.len() => {
                viewer_host = Some(argv[i + 1].clone());
                i += 2;
            }
            "--viewer-port" if i + 1 < argv.len() => {
                viewer_port = argv[i + 1].parse::<u16>().ok();
                i += 2;
            }
            "--project-root" if i + 1 < argv.len() => {
                project_root = Some(argv[i + 1].clone());
                i += 2;
            }
            "--session-id" if i + 1 < argv.len() => {
                session_id = Some(argv[i + 1].clone());
                i += 2;
            }
            "--codex-bin" if i + 1 < argv.len() => {
                codex_bin = Some(argv[i + 1].clone());
                i += 2;
            }
            _ => {
                i += 1;
            }
        }
    }

    Some(Args {
        viewer_host: viewer_host.unwrap_or_else(|| "127.0.0.1".to_string()),
        viewer_port: viewer_port.unwrap_or(38888),
        project_root: project_root?,
        session_id: session_id?,
        codex_bin: codex_bin
            .or_else(|| std::env::var("CODEX_PATH").ok())
            .unwrap_or_else(|| "codex".to_string()),
    })
}

fn terminal_pty_size() -> PtySize {
    let default = PtySize {
        rows: 40,
        cols: 120,
        pixel_width: 0,
        pixel_height: 0,
    };
    match terminal_size() {
        Some((Width(cols), Height(rows))) if cols > 0 && rows > 0 => PtySize {
            rows,
            cols,
            pixel_width: 0,
            pixel_height: 0,
        },
        _ => default,
    }
}

fn toml_escape(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for ch in s.chars() {
        match ch {
            '\\' => out.push_str("\\\\"),
            '"' => out.push_str("\\\""),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            _ => out.push(ch),
        }
    }
    out.push('"');
    out
}

fn toml_array(values: &[String]) -> String {
    let joined = values.iter().map(|v| toml_escape(v)).collect::<Vec<_>>().join(",");
    format!("[{}]", joined)
}

fn resolve_notifier_path() -> String {
    let exe = std::env::current_exe().ok();
    if let Some(exe) = exe {
        if let Some(dir) = exe.parent() {
            let direct = if cfg!(windows) {
                dir.join("cc-spec-codex-notify.exe")
            } else {
                dir.join("cc-spec-codex-notify")
            };
            if direct.exists() {
                return direct.to_string_lossy().to_string();
            }
            // dev 模式下 externalBin 常带 target triple 后缀：cc-spec-codex-notify-<triple>.exe
            if let Ok(entries) = std::fs::read_dir(dir) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    let name = path.file_name().and_then(|v| v.to_str()).unwrap_or("");
                    if cfg!(windows) {
                        if name.starts_with("cc-spec-codex-notify-") && name.ends_with(".exe") {
                            return path.to_string_lossy().to_string();
                        }
                    } else if name.starts_with("cc-spec-codex-notify-") {
                        return path.to_string_lossy().to_string();
                    }
                }
            }
        }
    }
    if cfg!(windows) {
        "cc-spec-codex-notify.exe".to_string()
    } else {
        "cc-spec-codex-notify".to_string()
    }
}

#[derive(Clone, Debug)]
enum ControlCommand {
    SendInput {
        text: String,
        request_id: Option<String>,
        requested_by: Option<String>,
    },
    Pause {
        requested_by: Option<String>,
    },
    Kill {
        requested_by: Option<String>,
    },
    Retry {
        text: String,
        request_id: Option<String>,
        requested_by: Option<String>,
    },
}

#[derive(Clone, Debug)]
enum RelayEvent {
    Stdin(Vec<u8>),
    Control(ControlCommand),
    ChildExited { generation: u64, exit_code: i32 },
    ViewerDisconnected,
}

fn parse_control(session_id: &str, data: &str) -> Option<ControlCommand> {
    let v: Value = serde_json::from_str(data).ok()?;
    if v.get("type").and_then(|x| x.as_str()) != Some("codex.control") {
        return None;
    }
    let sid = v.get("session_id").and_then(|x| x.as_str()).unwrap_or("");
    if sid != session_id {
        return None;
    }
    let action = v.get("action").and_then(|x| x.as_str()).unwrap_or("");
    let requested_by = v
        .get("requested_by")
        .and_then(|x| x.as_str())
        .map(|s| s.to_string());
    let request_id = v
        .get("request_id")
        .and_then(|x| x.as_str())
        .map(|s| s.to_string());
    match action {
        "send_input" => Some(ControlCommand::SendInput {
            text: v.get("text").and_then(|x| x.as_str()).unwrap_or("").to_string(),
            request_id,
            requested_by,
        }),
        "pause" => Some(ControlCommand::Pause { requested_by }),
        "kill" => Some(ControlCommand::Kill { requested_by }),
        "retry" => Some(ControlCommand::Retry {
            text: v.get("text").and_then(|x| x.as_str()).unwrap_or("").to_string(),
            request_id,
            requested_by,
        }),
        _ => None,
    }
}

fn spawn_codex(
    args: &Args,
    pty_size: PtySize,
) -> Result<
    (
        Box<dyn Write + Send>,
        Box<dyn Read + Send>,
        i32,
        Box<dyn portable_pty::Child + Send>,
    ),
    String,
> {
    let endpoint = format!("http://{}:{}", args.viewer_host, args.viewer_port);
    let notifier = resolve_notifier_path();
    let notify_args = vec![
        notifier,
        "--endpoint".to_string(),
        endpoint,
        "--session-id".to_string(),
        args.session_id.clone(),
        "--project-root".to_string(),
        args.project_root.clone(),
    ];
    let notify_cfg = format!("notify={}", toml_array(&notify_args));

    let pty_system = native_pty_system();
    let pair = pty_system
        .openpty(pty_size)
        .map_err(|e| format!("openpty 失败: {}", e))?;

    let mut cmd = CommandBuilder::new(&args.codex_bin);
    cmd.cwd(&args.project_root);
    cmd.args(&["--config".to_string(), notify_cfg]);

    let child = pair
        .slave
        .spawn_command(cmd)
        .map_err(|e| format!("spawn codex 失败: {}", e))?;

    let pid = child
        .process_id()
        .map(|p| p as i32)
        .unwrap_or(-1);

    let reader = pair
        .master
        .try_clone_reader()
        .map_err(|e| format!("clone reader 失败: {}", e))?;
    let writer = pair
        .master
        .take_writer()
        .map_err(|e| format!("take writer 失败: {}", e))?;

    Ok((writer, reader, pid, child))
}

fn kill_pid(pid: i32) {
    if pid <= 0 {
        return;
    }
    if cfg!(windows) {
        let _ = std::process::Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/F"])
            .output();
    } else {
        let _ = std::process::Command::new("kill")
            .args(["-9", &pid.to_string()])
            .status();
    }
}

fn main() {
    let args = match parse_args() {
        Some(v) => v,
        None => return,
    };

    // 说明：这里不对 relay 本身单独建模；`codex.session.*` 表示“交互式 codex 子进程”的状态。
    // relay 会在每次成功拉起 codex（含 retry/restart）后发送 `codex.session.started`（pid=codex_pid）。

    let (tx, rx) = mpsc::channel::<RelayEvent>();

    // stdin thread: 原样读取字节，交给主循环写入 PTY writer
    {
        let tx = tx.clone();
        thread::spawn(move || {
            let mut stdin = std::io::stdin();
            let mut buf = [0u8; 4096];
            loop {
                match stdin.read(&mut buf) {
                    Ok(0) => break,
                    Ok(n) => {
                        if tx.send(RelayEvent::Stdin(buf[..n].to_vec())).is_err() {
                            break;
                        }
                    }
                    Err(_) => break,
                }
            }
        });
    }

    // events thread: SSE 订阅 /events，接收 codex.control
    {
        let viewer_host = args.viewer_host.clone();
        let viewer_port = args.viewer_port;
        let session_id = args.session_id.clone();
        let tx = tx.clone();
        thread::spawn(move || loop {
            let stream = match connect_events(&viewer_host, viewer_port) {
                Ok(s) => s,
                Err(_) => {
                    let _ = tx.send(RelayEvent::ViewerDisconnected);
                    return;
                }
            };
            let mut reader = BufReader::new(stream);
            let mut line = String::new();
            let mut cur_event: Option<String> = None;
            let mut cur_data: Option<String> = None;

            loop {
                line.clear();
                match reader.read_line(&mut line) {
                    Ok(0) => {
                        let _ = tx.send(RelayEvent::ViewerDisconnected);
                        return;
                    }
                    Ok(_) => {}
                    Err(_) => {
                        let _ = tx.send(RelayEvent::ViewerDisconnected);
                        return;
                    }
                }
                let l = line.trim_end_matches(['\r', '\n']);
                if l.starts_with(':') {
                    continue;
                }
                if l.starts_with("event:") {
                    cur_event = Some(l.trim_start_matches("event:").trim().to_string());
                } else if l.starts_with("data:") {
                    let chunk = l.trim_start_matches("data:").trim().to_string();
                    match &mut cur_data {
                        Some(existing) => {
                            existing.push('\n');
                            existing.push_str(&chunk);
                        }
                        None => cur_data = Some(chunk),
                    }
                } else if l.is_empty() {
                    if let (Some(ev), Some(data)) = (cur_event.take(), cur_data.take()) {
                        if ev == "codex.control" {
                            if let Some(cmd) = parse_control(&session_id, &data) {
                                let _ = tx.send(RelayEvent::Control(cmd));
                            }
                        }
                    }
                }
            }
        });
    }

    // 主循环状态
    let mut writer: Option<Box<dyn Write + Send>> = None;
    let mut codex_pid: i32 = -1;
    let mut generation: u64 = 1;
    let mut last_stop_requested_by: Option<String> = None;
    let mut last_stop_requested_at_ms: u64 = 0;
    let mut last_user_interrupt_at_ms: u64 = 0;

    // 启动 codex
    let mut current_child: Option<Box<dyn portable_pty::Child + Send>> = None;
    let pty_size = terminal_pty_size();
    match spawn_codex(&args, pty_size) {
        Ok((w, mut r, pid, child)) => {
            writer = Some(w);
            codex_pid = pid;
            current_child = Some(child);
            publish_event(
                &args.viewer_host,
                args.viewer_port,
                &serde_json::json!({
                    "type": "codex.session.started",
                    "ts": now_iso(),
                    "session_id": args.session_id.clone(),
                    "project_root": args.project_root.clone(),
                    "pid": pid,
                }),
            );

            // 输出线程：读 PTY -> stdout
            thread::spawn(move || {
                let mut stdout = std::io::stdout();
                let mut buf = [0u8; 8192];
                loop {
                    match r.read(&mut buf) {
                        Ok(0) => break,
                        Ok(n) => {
                            let _ = stdout.write_all(&buf[..n]);
                            let _ = stdout.flush();
                        }
                        Err(_) => break,
                    }
                }
            });
        }
        Err(e) => {
            eprintln!("[cc-spec] failed to start codex: {}", e);
            publish_event(
                &args.viewer_host,
                args.viewer_port,
                &serde_json::json!({
                    "type": "codex.session.exited",
                    "ts": now_iso(),
                    "session_id": args.session_id.clone(),
                    "project_root": args.project_root.clone(),
                    "exit_code": -1,
                    "exit_reason": "spawn_failed",
                }),
            );
        }
    }

    // 等待 codex 退出的线程：child.wait()
    {
        let tx = tx.clone();
        if let Some(mut child) = current_child.take() {
            let gen = generation;
            thread::spawn(move || {
                let exit = child
                    .wait()
                    .ok()
                    .map(|s| s.exit_code() as i32)
                    .unwrap_or(-1);
                let _ = tx.send(RelayEvent::ChildExited {
                    generation: gen,
                    exit_code: exit,
                });
            });
        }
    }

    // 主事件循环：stdin + 控制命令 + 退出监控
    loop {
        let ev = match rx.recv() {
            Ok(ev) => ev,
            Err(_) => break,
        };

        match ev {
            RelayEvent::ViewerDisconnected => {
                // tool 不在了：直接退出，避免孤儿会话
                kill_pid(codex_pid);
                break;
            }
            RelayEvent::Stdin(bytes) => {
                if bytes.iter().any(|b| *b == 0x03) {
                    last_user_interrupt_at_ms = now_ms();
                }
                if let Some(w) = writer.as_mut() {
                    let _ = w.write_all(&bytes);
                    let _ = w.flush();
                }
            }
            RelayEvent::Control(cmd) => match cmd {
                ControlCommand::SendInput { text, .. } => {
                    if text.trim().is_empty() {
                        continue;
                    }
                    if writer.is_none() {
                        // codex 不在了：尝试拉起再注入
                        generation = generation.wrapping_add(1);
                        let gen = generation;
                        match spawn_codex(&args, terminal_pty_size()) {
                            Ok((w, mut r, pid, mut child)) => {
                                writer = Some(w);
                                codex_pid = pid;
                                publish_event(
                                    &args.viewer_host,
                                    args.viewer_port,
                                    &serde_json::json!({
                                        "type": "codex.session.started",
                                        "ts": now_iso(),
                                        "session_id": args.session_id.clone(),
                                        "project_root": args.project_root.clone(),
                                        "pid": pid,
                                    }),
                                );
                                thread::spawn(move || {
                                    let mut stdout = std::io::stdout();
                                    let mut buf = [0u8; 8192];
                                    loop {
                                        match r.read(&mut buf) {
                                            Ok(0) => break,
                                            Ok(n) => {
                                                let _ = stdout.write_all(&buf[..n]);
                                                let _ = stdout.flush();
                                            }
                                            Err(_) => break,
                                        }
                                    }
                                });
                                let tx = tx.clone();
                                thread::spawn(move || {
                                    let exit = child
                                        .wait()
                                        .ok()
                                        .map(|s| s.exit_code() as i32)
                                        .unwrap_or(-1);
                                    let _ = tx.send(RelayEvent::ChildExited {
                                        generation: gen,
                                        exit_code: exit,
                                    });
                                });
                            }
                            Err(e) => {
                                eprintln!("[cc-spec] failed to restart codex: {}", e);
                                publish_event(
                                    &args.viewer_host,
                                    args.viewer_port,
                                    &serde_json::json!({
                                        "type": "codex.session.exited",
                                        "ts": now_iso(),
                                        "session_id": args.session_id.clone(),
                                        "project_root": args.project_root.clone(),
                                        "exit_code": -1,
                                        "exit_reason": "spawn_failed",
                                    }),
                                );
                                continue;
                            }
                        }
                    }

                    if let Some(w) = writer.as_mut() {
                        let mut data = text.into_bytes();
                        data.push(b'\n');
                        let _ = w.write_all(&data);
                        let _ = w.flush();
                    }
                }
                ControlCommand::Pause { requested_by } => {
                    last_stop_requested_by = requested_by;
                    last_stop_requested_at_ms = now_ms();
                    if let Some(w) = writer.as_mut() {
                        let _ = w.write_all(&[0x03]);
                        let _ = w.flush();
                    }
                }
                ControlCommand::Kill { requested_by } => {
                    last_stop_requested_by = requested_by;
                    last_stop_requested_at_ms = now_ms();
                    kill_pid(codex_pid);
                    let reason = match &last_stop_requested_by {
                        Some(v) if v == "claude_code" => "claude_requested",
                        Some(_) => "tool_requested",
                        None => "tool_requested",
                    };
                    publish_event(
                        &args.viewer_host,
                        args.viewer_port,
                        &serde_json::json!({
                            "type": "codex.session.exited",
                            "ts": now_iso(),
                            "session_id": args.session_id.clone(),
                            "project_root": args.project_root.clone(),
                            "exit_code": 137,
                            "exit_reason": reason,
                        }),
                    );
                    // kill 后直接退出 relay
                    break;
                }
                ControlCommand::Retry {
                    text,
                    requested_by,
                    ..
                } => {
                    // 重试 = 杀掉旧进程（如有）+ 拉起新 codex + 注入 prompt
                    last_stop_requested_by = requested_by;
                    last_stop_requested_at_ms = now_ms();
                    generation = generation.wrapping_add(1);
                    let gen = generation;
                    kill_pid(codex_pid);
                    writer = None;
                    codex_pid = -1;

                    match spawn_codex(&args, terminal_pty_size()) {
                        Ok((w, mut r, pid, mut child)) => {
                            writer = Some(w);
                            codex_pid = pid;
                            publish_event(
                                &args.viewer_host,
                                args.viewer_port,
                                &serde_json::json!({
                                    "type": "codex.session.started",
                                    "ts": now_iso(),
                                    "session_id": args.session_id.clone(),
                                    "project_root": args.project_root.clone(),
                                    "pid": pid,
                                }),
                            );
                            thread::spawn(move || {
                                let mut stdout = std::io::stdout();
                                let mut buf = [0u8; 8192];
                                loop {
                                    match r.read(&mut buf) {
                                        Ok(0) => break,
                                        Ok(n) => {
                                            let _ = stdout.write_all(&buf[..n]);
                                            let _ = stdout.flush();
                                        }
                                        Err(_) => break,
                                    }
                                }
                            });
                            let tx = tx.clone();
                            thread::spawn(move || {
                                let exit = child
                                    .wait()
                                    .ok()
                                    .map(|s| s.exit_code() as i32)
                                    .unwrap_or(-1);
                                let _ = tx.send(RelayEvent::ChildExited {
                                    generation: gen,
                                    exit_code: exit,
                                });
                            });
                        }
                        Err(e) => {
                            eprintln!("[cc-spec] failed to retry codex: {}", e);
                            publish_event(
                                &args.viewer_host,
                                args.viewer_port,
                                &serde_json::json!({
                                    "type": "codex.session.exited",
                                    "ts": now_iso(),
                                    "session_id": args.session_id.clone(),
                                    "project_root": args.project_root.clone(),
                                    "exit_code": -1,
                                    "exit_reason": "spawn_failed",
                                }),
                            );
                            continue;
                        }
                    }

                    if let Some(w) = writer.as_mut() {
                        let mut data = text.into_bytes();
                        data.push(b'\n');
                        let _ = w.write_all(&data);
                        let _ = w.flush();
                    }
                }
            },
            RelayEvent::ChildExited { generation: gen, exit_code } => {
                if gen != generation {
                    continue;
                }
                let now = now_ms();
                let exit_reason = if let Some(by) = &last_stop_requested_by {
                    if now.saturating_sub(last_stop_requested_at_ms) <= 5000 {
                        if by == "claude_code" {
                            "claude_requested"
                        } else {
                            "tool_requested"
                        }
                    } else {
                        "crash_or_unknown"
                    }
                } else if now.saturating_sub(last_user_interrupt_at_ms) <= 2000 {
                    "user_requested"
                } else if exit_code == 0 {
                    "user_requested"
                } else {
                    "crash_or_unknown"
                };

                publish_event(
                    &args.viewer_host,
                    args.viewer_port,
                    &serde_json::json!({
                        "type": "codex.session.exited",
                        "ts": now_iso(),
                        "session_id": args.session_id.clone(),
                        "project_root": args.project_root.clone(),
                        "exit_code": exit_code,
                        "exit_reason": exit_reason,
                    }),
                );

                // codex 已退出，等待 tool 的 restart/retry；stdin 继续读但会被丢弃
                writer = None;
                codex_pid = -1;
                last_stop_requested_by = None;
            }
        }
    }
}
