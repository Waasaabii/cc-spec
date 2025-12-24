// terminal.rs - 系统终端启动 Claude Code（非内嵌）

use std::env;
use std::process::Command;

pub fn launch_claude_terminal(
    project_path: String,
    viewer_host: String,
    viewer_port: u16,
    session_id: Option<String>,
) -> Result<(), String> {
    let terminal_cmd = env::var("CC_SPEC_TERMINAL").unwrap_or_default();
    let codex_runner = "rust";

    if cfg!(windows) {
        let program = if terminal_cmd.trim().is_empty() {
            "powershell".to_string()
        } else {
            terminal_cmd
        };

        let command_line = format!("cd \"{}\"; claude", project_path);
        let mut cmd = Command::new(program);
        cmd.args(["-NoExit", "-Command", &command_line]);
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
        return Ok(());
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
