// cc-spec-codex-relay - 原生终端中的 Codex 交互会话桥接
//
// 目标：
// - 在终端中“像原生一样”运行 Codex TUI（非 Windows：通过 PTY；Windows：直接挂载 console，避免 ConPTY 嵌套崩溃）。
// - 监听 tools viewer 的 /events，接收 codex.control 注入输入/重试/暂停/停止。
// - 通过 /ingest 上报 session.started / session.exited；并通过 Codex notify hook 上报 turn_complete（由 cc-spec-codex-notify 负责）。

use serde_json::Value;
use std::io::{BufRead, BufReader, Write};

#[cfg(not(windows))]
use portable_pty::{native_pty_system, CommandBuilder, PtySize};
#[cfg(not(windows))]
use std::io::Read;
use std::net::TcpStream;
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, SystemTime};

#[cfg(not(windows))]
use terminal_size::{terminal_size, Height, Width};

#[cfg(windows)]
use windows_sys::Win32::Foundation::GetLastError;
#[cfg(windows)]
use windows_sys::Win32::System::Console::{
    GenerateConsoleCtrlEvent, GetStdHandle, SetConsoleCtrlHandler, WriteConsoleInputW, CTRL_C_EVENT,
    INPUT_RECORD, INPUT_RECORD_0, KEY_EVENT, KEY_EVENT_RECORD, KEY_EVENT_RECORD_0, STD_INPUT_HANDLE,
};

fn now_iso() -> String {
    chrono::Utc::now().to_rfc3339()
}

#[cfg(windows)]
const CREATE_NEW_PROCESS_GROUP: u32 = 0x00000200;

#[cfg(windows)]
unsafe extern "system" fn ignore_ctrl_handler(_ctrl_type: u32) -> i32 {
    // TRUE：表示该事件已处理，避免 relay 被 Ctrl+C 终止。
    1
}

#[cfg(windows)]
fn inject_text_to_console(text: &str) -> Result<(), String> {
    let handle = unsafe { GetStdHandle(STD_INPUT_HANDLE) };
    // INVALID_HANDLE_VALUE = -1，且 GetStdHandle 失败时返回 NULL
    if handle.is_null() || handle as isize == -1 {
        return Err("获取 STD_INPUT_HANDLE 失败".to_string());
    }

    let mut records: Vec<INPUT_RECORD> = Vec::new();
    for ch in text.chars().chain(std::iter::once('\r')) {
        let u = ch as u16;
        let key_down = KEY_EVENT_RECORD {
            bKeyDown: 1,
            wRepeatCount: 1,
            wVirtualKeyCode: 0,
            wVirtualScanCode: 0,
            uChar: KEY_EVENT_RECORD_0 { UnicodeChar: u },
            dwControlKeyState: 0,
        };
        let key_up = KEY_EVENT_RECORD {
            bKeyDown: 0,
            wRepeatCount: 1,
            wVirtualKeyCode: 0,
            wVirtualScanCode: 0,
            uChar: KEY_EVENT_RECORD_0 { UnicodeChar: u },
            dwControlKeyState: 0,
        };
        records.push(INPUT_RECORD {
            EventType: KEY_EVENT as u16,
            Event: INPUT_RECORD_0 { KeyEvent: key_down },
        });
        records.push(INPUT_RECORD {
            EventType: KEY_EVENT as u16,
            Event: INPUT_RECORD_0 { KeyEvent: key_up },
        });
    }

    let mut written: u32 = 0;
    let ok = unsafe {
        WriteConsoleInputW(
            handle,
            records.as_ptr(),
            records.len() as u32,
            &mut written,
        )
    };
    if ok == 0 {
        return Err(format!(
            "WriteConsoleInputW 失败: {} (err={})",
            std::io::Error::last_os_error(),
            unsafe { GetLastError() }
        ));
    }
    Ok(())
}

#[cfg(windows)]
fn send_ctrl_c_to_process_group(process_group_id: u32) -> Result<(), String> {
    let ok = unsafe { GenerateConsoleCtrlEvent(CTRL_C_EVENT, process_group_id) };
    if ok == 0 {
        return Err(format!(
            "GenerateConsoleCtrlEvent 失败: {} (err={})",
            std::io::Error::last_os_error(),
            unsafe { GetLastError() }
        ));
    }
    Ok(())
}

/// 通过 console 输入缓冲区注入 Ctrl+C 按键事件
/// 这种方式比 GenerateConsoleCtrlEvent 更可靠，因为后者在 CREATE_NEW_PROCESS_GROUP 下可能被忽略
#[cfg(windows)]
fn inject_ctrl_c_to_console() -> Result<(), String> {
    let handle = unsafe { GetStdHandle(STD_INPUT_HANDLE) };
    if handle.is_null() || handle as isize == -1 {
        return Err("获取 STD_INPUT_HANDLE 失败".to_string());
    }

    // Ctrl+C: virtual key = 'C' (0x43), char = 0x03, with LEFT_CTRL_PRESSED
    const LEFT_CTRL_PRESSED: u32 = 0x0008;
    let key_down = KEY_EVENT_RECORD {
        bKeyDown: 1,
        wRepeatCount: 1,
        wVirtualKeyCode: 0x43, // 'C'
        wVirtualScanCode: 0x2E, // scan code for 'C'
        uChar: KEY_EVENT_RECORD_0 { UnicodeChar: 0x03 },
        dwControlKeyState: LEFT_CTRL_PRESSED,
    };
    let key_up = KEY_EVENT_RECORD {
        bKeyDown: 0,
        wRepeatCount: 1,
        wVirtualKeyCode: 0x43,
        wVirtualScanCode: 0x2E,
        uChar: KEY_EVENT_RECORD_0 { UnicodeChar: 0x03 },
        dwControlKeyState: LEFT_CTRL_PRESSED,
    };

    let records = [
        INPUT_RECORD {
            EventType: KEY_EVENT as u16,
            Event: INPUT_RECORD_0 { KeyEvent: key_down },
        },
        INPUT_RECORD {
            EventType: KEY_EVENT as u16,
            Event: INPUT_RECORD_0 { KeyEvent: key_up },
        },
    ];

    let mut written: u32 = 0;
    let ok = unsafe {
        WriteConsoleInputW(
            handle,
            records.as_ptr(),
            records.len() as u32,
            &mut written,
        )
    };
    if ok == 0 {
        return Err(format!(
            "WriteConsoleInputW (Ctrl+C) 失败: {} (err={})",
            std::io::Error::last_os_error(),
            unsafe { GetLastError() }
        ));
    }
    Ok(())
}

#[cfg(windows)]
fn spawn_codex_direct(args: &Args) -> Result<(i32, std::process::Child), String> {
    use std::os::windows::process::CommandExt;

    let codex_bin = &args.codex_bin;
    let codex_bin_lower = codex_bin.to_ascii_lowercase();

    let mut cmd = if codex_bin_lower.ends_with(".cmd") || codex_bin_lower.ends_with(".bat") {
        let mut c = std::process::Command::new("cmd.exe");
        c.args(["/c", codex_bin, "--yolo"]);
        c
    } else {
        let mut c = std::process::Command::new(codex_bin);
        c.args(["--yolo"]);
        c
    };
    cmd.current_dir(&args.project_root);
    cmd.env("CODEX_DISABLE_TELEMETRY", "1");

    // 让 codex 进程成为新的 process group，便于向其发送 Ctrl+C（不影响 relay 本身）。
    cmd.creation_flags(CREATE_NEW_PROCESS_GROUP);

    let child = cmd
        .spawn()
        .map_err(|e| format!("spawn codex 失败: {} (bin: {})", e, codex_bin))?;
    let pid = child.id() as i32;
    Ok((pid, child))
}

#[cfg(windows)]
fn main_windows_direct(args: Args) {
    // Windows 直连 console：避免在已有 console 下再创建 ConPTY，导致子进程 0xC0000142 秒退。
    unsafe {
        SetConsoleCtrlHandler(Some(ignore_ctrl_handler), 1);
    }

    let (tx, rx) = mpsc::channel::<RelayEvent>();

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

    let mut codex_pid: i32 = -1;
    let mut generation: u64 = 1;
    let mut last_stop_requested_by: Option<String> = None;
    let mut last_stop_requested_at_ms: u64 = 0;

    // 启动 codex（直接挂载到当前 console）
    let mut current_child: Option<std::process::Child> = None;
    match spawn_codex_direct(&args) {
        Ok((pid, child)) => {
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
                    .and_then(|s| s.code())
                    .unwrap_or(-1);
                let _ = tx.send(RelayEvent::ChildExited {
                    generation: gen,
                    exit_code: exit,
                });
            });
        }
    }

    loop {
        let ev = match rx.recv() {
            Ok(ev) => ev,
            Err(_) => break,
        };

        match ev {
            RelayEvent::ViewerDisconnected => {
                kill_pid(codex_pid);
                break;
            }
            RelayEvent::Control(cmd) => match cmd {
                ControlCommand::SendInput { text, .. } => {
                    if text.trim().is_empty() {
                        continue;
                    }
                    if codex_pid <= 0 {
                        generation = generation.wrapping_add(1);
                        let gen = generation;
                        match spawn_codex_direct(&args) {
                            Ok((pid, mut child)) => {
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
                                let tx = tx.clone();
                                thread::spawn(move || {
                                    let exit = child
                                        .wait()
                                        .ok()
                                        .and_then(|s| s.code())
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
                    let _ = inject_text_to_console(&text);
                }
                ControlCommand::Retry { text, .. } => {
                    if text.trim().is_empty() {
                        continue;
                    }
                    if codex_pid <= 0 {
                        generation = generation.wrapping_add(1);
                        let gen = generation;
                        match spawn_codex_direct(&args) {
                            Ok((pid, mut child)) => {
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
                                let tx = tx.clone();
                                thread::spawn(move || {
                                    let exit = child
                                        .wait()
                                        .ok()
                                        .and_then(|s| s.code())
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
                    }
                    let _ = inject_text_to_console(&text);
                }
                ControlCommand::Pause { requested_by } => {
                    last_stop_requested_by = requested_by;
                    last_stop_requested_at_ms = now_ms();
                    if codex_pid > 0 {
                        // 优先使用 console 输入注入方式，比 GenerateConsoleCtrlEvent 更可靠
                        if let Err(e) = inject_ctrl_c_to_console() {
                            eprintln!("[cc-spec] inject_ctrl_c_to_console failed: {}, falling back to GenerateConsoleCtrlEvent", e);
                            let _ = send_ctrl_c_to_process_group(codex_pid as u32);
                        }
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

                    codex_pid = -1;
                    break;
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

                codex_pid = -1;
                last_stop_requested_by = None;
            }
            // Windows direct 模式下不使用的事件
            _ => {}
        }
    }
}

fn main() {
    let args = match parse_args() {
        Some(v) => v,
        None => return,
    };

    #[cfg(windows)]
    main_windows_direct(args);

    #[cfg(not(windows))]
    main_pty(args);
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

#[cfg(not(windows))]
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
    /// 终端查询：光标位置报告（DSR, ESC[6n）
    TerminalDsr,
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

#[cfg(not(windows))]
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
    let pty_system = native_pty_system();
    let pair = pty_system
        .openpty(pty_size)
        .map_err(|e| format!("openpty 失败: {}", e))?;

    // 直接启动 codex（对于 .cmd/.bat 文件，通过 cmd.exe /c 运行）
    let codex_bin = &args.codex_bin;
    let codex_bin_lower = codex_bin.to_ascii_lowercase();
    let mut cmd = if codex_bin_lower.ends_with(".cmd") || codex_bin_lower.ends_with(".bat") {
        let mut c = CommandBuilder::new("cmd.exe");
        c.args(["/c", codex_bin, "--yolo"]);
        c
    } else {
        let mut c = CommandBuilder::new(codex_bin);
        c.args(["--yolo"]);
        c
    };
    cmd.cwd(&args.project_root);

    // 设置终端环境变量
    cmd.env("TERM", "xterm-256color");
    cmd.env("COLORTERM", "truecolor");
    cmd.env("FORCE_COLOR", "1");
    cmd.env("CODEX_DISABLE_TELEMETRY", "1");

    eprintln!("[relay] 启动 codex: {} (cwd: {})", codex_bin, args.project_root);
    eprintln!("[relay] PTY size: {}x{}", pty_size.cols, pty_size.rows);

    let child = pair
        .slave
        .spawn_command(cmd)
        .map_err(|e| format!("spawn codex 失败: {} (bin: {})", e, codex_bin))?;

    let pid = child
        .process_id()
        .map(|p| p as i32)
        .unwrap_or(-1);

    eprintln!("[relay] codex 已启动, pid={}", pid);

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

#[cfg(not(windows))]
fn main_pty(args: Args) {
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
            // Windows 的 conhost/部分终端对 DSR(ESC[6n) 不会响应，可能导致 TUI 初始化卡死；
            // 这里拦截该查询并由 relay 代答（ESC[1;1R），保证 Codex 能继续渲染。
            {
                let tx = tx.clone();
                thread::spawn(move || {
                    const DSR_QUERY: &[u8] = b"\x1b[6n";
                    let mut stdout = std::io::stdout();
                    let mut buf = [0u8; 8192];
                    let mut carry: Vec<u8> = Vec::new();
                    loop {
                        match r.read(&mut buf) {
                            Ok(0) => break,
                            Ok(n) => {
                                let mut data = Vec::with_capacity(carry.len() + n);
                                data.extend_from_slice(&carry);
                                data.extend_from_slice(&buf[..n]);

                                let safe_len = data.len().saturating_sub(DSR_QUERY.len() - 1);
                                let mut out = Vec::with_capacity(n);
                                let mut i = 0usize;
                                while i < safe_len {
                                    if i + DSR_QUERY.len() <= data.len()
                                        && &data[i..i + DSR_QUERY.len()] == DSR_QUERY
                                    {
                                        let _ = tx.send(RelayEvent::TerminalDsr);
                                        i += DSR_QUERY.len();
                                        continue;
                                    }
                                    out.push(data[i]);
                                    i += 1;
                                }

                                carry.clear();
                                if i < data.len() {
                                    carry.extend_from_slice(&data[i..]);
                                }

                                if !out.is_empty() {
                                    let _ = stdout.write_all(&out);
                                    let _ = stdout.flush();
                                }
                            }
                            Err(_) => break,
                        }
                    }
                    if !carry.is_empty() {
                        let _ = stdout.write_all(&carry);
                        let _ = stdout.flush();
                    }
                });
            }

            writer = Some(w);
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
            RelayEvent::TerminalDsr => {
                // 终端查询光标位置报告（DSR）——返回左上角即可（最常见的初始化位置）
                if let Some(w) = writer.as_mut() {
                    let _ = w.write_all(b"\x1b[1;1R");
                    let _ = w.flush();
                }
            }
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
                                {
                                    let tx = tx.clone();
                                    thread::spawn(move || {
                                        const DSR_QUERY: &[u8] = b"\x1b[6n";
                                        let mut stdout = std::io::stdout();
                                        let mut buf = [0u8; 8192];
                                        let mut carry: Vec<u8> = Vec::new();
                                        loop {
                                            match r.read(&mut buf) {
                                                Ok(0) => break,
                                                Ok(n) => {
                                                    let mut data = Vec::with_capacity(carry.len() + n);
                                                    data.extend_from_slice(&carry);
                                                    data.extend_from_slice(&buf[..n]);
                                                    let safe_len =
                                                        data.len().saturating_sub(DSR_QUERY.len() - 1);
                                                    let mut out = Vec::with_capacity(n);
                                                    let mut i = 0usize;
                                                    while i < safe_len {
                                                        if i + DSR_QUERY.len() <= data.len()
                                                            && &data[i..i + DSR_QUERY.len()] == DSR_QUERY
                                                        {
                                                            let _ = tx.send(RelayEvent::TerminalDsr);
                                                            i += DSR_QUERY.len();
                                                            continue;
                                                        }
                                                        out.push(data[i]);
                                                        i += 1;
                                                    }
                                                    carry.clear();
                                                    if i < data.len() {
                                                        carry.extend_from_slice(&data[i..]);
                                                    }
                                                    if !out.is_empty() {
                                                        let _ = stdout.write_all(&out);
                                                        let _ = stdout.flush();
                                                    }
                                                }
                                                Err(_) => break,
                                            }
                                        }
                                        if !carry.is_empty() {
                                            let _ = stdout.write_all(&carry);
                                            let _ = stdout.flush();
                                        }
                                    });
                                }
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

                    // 1. 杀掉 codex 进程
                    kill_pid(codex_pid);

                    // 2. 关闭 PTY writer（触发子进程清理）
                    drop(writer.take());

                    // 3. 发送退出事件
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

                    // 4. 清理状态并退出 relay
                    codex_pid = -1;
                    last_stop_requested_by = None;
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
                            {
                                let tx = tx.clone();
                                thread::spawn(move || {
                                    const DSR_QUERY: &[u8] = b"\x1b[6n";
                                    let mut stdout = std::io::stdout();
                                    let mut buf = [0u8; 8192];
                                    let mut carry: Vec<u8> = Vec::new();
                                    loop {
                                        match r.read(&mut buf) {
                                            Ok(0) => break,
                                            Ok(n) => {
                                                let mut data = Vec::with_capacity(carry.len() + n);
                                                data.extend_from_slice(&carry);
                                                data.extend_from_slice(&buf[..n]);
                                                let safe_len =
                                                    data.len().saturating_sub(DSR_QUERY.len() - 1);
                                                let mut out = Vec::with_capacity(n);
                                                let mut i = 0usize;
                                                while i < safe_len {
                                                    if i + DSR_QUERY.len() <= data.len()
                                                        && &data[i..i + DSR_QUERY.len()] == DSR_QUERY
                                                    {
                                                        let _ = tx.send(RelayEvent::TerminalDsr);
                                                        i += DSR_QUERY.len();
                                                        continue;
                                                    }
                                                    out.push(data[i]);
                                                    i += 1;
                                                }
                                                carry.clear();
                                                if i < data.len() {
                                                    carry.extend_from_slice(&data[i..]);
                                                }
                                                if !out.is_empty() {
                                                    let _ = stdout.write_all(&out);
                                                    let _ = stdout.flush();
                                                }
                                            }
                                            Err(_) => break,
                                        }
                                    }
                                    if !carry.is_empty() {
                                        let _ = stdout.write_all(&carry);
                                        let _ = stdout.flush();
                                    }
                                });
                            }
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
