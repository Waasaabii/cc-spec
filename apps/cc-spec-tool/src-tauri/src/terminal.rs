// terminal.rs - 系统终端启动 Claude Code（非内嵌）

use std::env;
use std::process::Command;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NEW_CONSOLE: u32 = 0x00000010;

pub fn launch_claude_terminal(
    project_path: String,
    viewer_host: String,
    viewer_port: u16,
    session_id: Option<String>,
) -> Result<(), String> {
    let terminal_cmd = env::var("CC_SPEC_TERMINAL").unwrap_or_default();
    let codex_runner = "rust";

    if cfg!(windows) {
        let command_line = "claude".to_string();
        let programs = if terminal_cmd.trim().is_empty() {
            vec!["pwsh".to_string(), "powershell".to_string()]
        } else {
            vec![terminal_cmd]
        };

        let mut last_err: Option<String> = None;
        for program in programs {
            let mut cmd = Command::new(&program);
            cmd.current_dir(&project_path);
            cmd.args(["-NoExit", "-Command"]).arg(&command_line);
            #[cfg(windows)]
            cmd.creation_flags(CREATE_NEW_CONSOLE);
            cmd.env("CC_SPEC_PROJECT_ROOT", &project_path);
            cmd.env("CC_SPEC_VIEWER_URL", format!("http://{}:{}", viewer_host, viewer_port));
            cmd.env("CC_SPEC_CODEX_RUNNER", codex_runner);
            cmd.env("CC_SPEC_CODEX_SSE_HOST", &viewer_host);
            cmd.env("CC_SPEC_CODEX_SSE_PORT", viewer_port.to_string());
            if let Some(sid) = session_id.as_deref() {
                cmd.env("CC_SPEC_SESSION_ID", sid);
            }

            match cmd.spawn() {
                Ok(_) => return Ok(()),
                Err(e) => {
                    last_err = Some(format!("{}: {}", program, e));
                    continue;
                }
            }
        }

        return Err(format!(
            "启动终端失败: {}",
            last_err.unwrap_or_else(|| "unknown error".to_string())
        ));
    }

    // 非 Windows：默认使用 bash -lc（可能不会弹出图形终端）
    let program = if terminal_cmd.trim().is_empty() {
        "bash".to_string()
    } else {
        terminal_cmd
    };
    let command_line = format!("cd \"{}\" && claude", project_path);
    let mut cmd = Command::new(program);
    cmd.args(["-lc", &command_line]);
    cmd.env("CC_SPEC_PROJECT_ROOT", &project_path);
    cmd.env("CC_SPEC_VIEWER_URL", format!("http://{}:{}", viewer_host, viewer_port));
    cmd.env("CC_SPEC_CODEX_RUNNER", codex_runner);
    cmd.env("CC_SPEC_CODEX_SSE_HOST", &viewer_host);
    cmd.env("CC_SPEC_CODEX_SSE_PORT", viewer_port.to_string());
    if let Some(sid) = session_id {
        cmd.env("CC_SPEC_SESSION_ID", sid);
    }
    cmd.spawn()
        .map_err(|e| format!("启动终端失败: {}", e))?;
    Ok(())
}
