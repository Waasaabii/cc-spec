// terminal.rs - 系统终端启动 Claude Code（非内嵌）

use std::env;
use std::path::PathBuf;
use std::process::Command;

pub fn launch_claude_terminal(
    project_path: String,
    viewer_host: String,
    viewer_port: u16,
    session_id: Option<String>,
    app_handle: &tauri::AppHandle,
    codex_bin: Option<String>,
) -> Result<(), String> {
    let terminal_cmd = env::var("CC_SPEC_TERMINAL").unwrap_or_default();
    let codex_runner = "rust";

    // 构建环境变量
    let env_vars = vec![
        ("CC_SPEC_PROJECT_ROOT", project_path.clone()),
        ("CC_SPEC_VIEWER_URL", format!("http://{}:{}", viewer_host, viewer_port)),
        ("CC_SPEC_CODEX_RUNNER", codex_runner.to_string()),
        ("CC_SPEC_CODEX_SSE_HOST", viewer_host.clone()),
        ("CC_SPEC_CODEX_SSE_PORT", viewer_port.to_string()),
    ];

    if cfg!(windows) {
        // 使用 cmd /c start 来启动新的终端窗口
        // 这样可以正确继承用户的 PATH 环境变量
        let mut cmd = Command::new("cmd");

        // 选择 shell
        let shell = if terminal_cmd.trim().is_empty() {
            "pwsh".to_string()
        } else {
            terminal_cmd
        };

        // 构建 PowerShell 命令
        // 使用 -Command 执行 cd 和 claude --verbose
        let ps_command = format!(
            "cd '{}'; claude --verbose",
            project_path.replace('\'', "''")
        );

        // cmd /c start "" pwsh -NoExit -Command "cd 'path'; claude"
        cmd.args(["/c", "start", "", &shell, "-NoExit", "-Command", &ps_command]);

        // 设置环境变量
        for (key, value) in &env_vars {
            cmd.env(key, value);
        }
        // 统一 Python 输出编码：避免 Windows GBK 控制台下 Rich 输出 unicode（如 ✓）直接崩溃。
        cmd.env("PYTHONIOENCODING", "utf-8");
        cmd.env("PYTHONUTF8", "1");
        if let Some(sid) = session_id.as_deref() {
            cmd.env("CC_SPEC_SESSION_ID", sid);
        }
        if let Some(codex) = codex_bin.as_deref() {
            cmd.env("CODEX_PATH", codex);
        }

        // 确保 Claude 的 Bash 能直接找到 `cc-spec`（sidecar/shim）和 `codex`（可选）
        if let Some(new_path) = build_augmented_path(app_handle, codex_bin.as_deref()) {
            cmd.env("PATH", new_path);
        }

        match cmd.spawn() {
            Ok(_) => return Ok(()),
            Err(e) => {
                return Err(format!("启动终端失败: {}", e));
            }
        }
    }

    // 非 Windows：默认使用 bash -lc（可能不会弹出图形终端）
    let program = if terminal_cmd.trim().is_empty() {
        "bash".to_string()
    } else {
        terminal_cmd
    };
    let command_line = format!("cd \"{}\" && claude --verbose", project_path);
    let mut cmd = Command::new(program);
    cmd.args(["-lc", &command_line]);

    // 设置环境变量
    for (key, value) in &env_vars {
        cmd.env(key, value);
    }
    cmd.env("PYTHONIOENCODING", "utf-8");
    cmd.env("PYTHONUTF8", "1");
    if let Some(sid) = session_id {
        cmd.env("CC_SPEC_SESSION_ID", sid);
    }
    if let Some(codex) = codex_bin.as_deref() {
        cmd.env("CODEX_PATH", codex);
    }
    if let Some(new_path) = build_augmented_path(app_handle, codex_bin.as_deref()) {
        cmd.env("PATH", new_path);
    }

    cmd.spawn()
        .map_err(|e| format!("启动终端失败: {}", e))?;
    Ok(())
}

fn app_data_dir() -> PathBuf {
    let base = env::var("LOCALAPPDATA")
        .or_else(|_| env::var("HOME"))
        .unwrap_or_else(|_| ".".to_string());
    PathBuf::from(base).join("cc-spec-tools")
}

#[cfg(debug_assertions)]
fn dev_ccspec_repo_root() -> Result<PathBuf, String> {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .parent()
        .and_then(|p| p.parent())
        .and_then(|p| p.parent())
        .map(|p| p.to_path_buf())
        .ok_or_else(|| "Failed to resolve cc-spec repo root from CARGO_MANIFEST_DIR".to_string())
}

#[cfg(debug_assertions)]
fn ensure_dev_ccspec_shim() -> Result<PathBuf, String> {
    if !cfg!(windows) {
        return Err("dev shim only implemented for windows".to_string());
    }

    let repo_root = dev_ccspec_repo_root()?;
    let shim_dir = app_data_dir().join("dev-shim").join("bin");
    std::fs::create_dir_all(&shim_dir)
        .map_err(|e| format!("Failed to create shim dir: {}", e))?;

    let shim_path = shim_dir.join("cc-spec.cmd");
    let repo = repo_root.to_string_lossy().to_string();
    let content = format!(
        "@echo off\r\nset PYTHONIOENCODING=utf-8\r\nset PYTHONUTF8=1\r\nuv run --project \"{}\" --directory \"%CD%\" -m cc_spec %*\r\n",
        repo.replace('"', "\"\"")
    );

    let needs_write = match std::fs::read_to_string(&shim_path) {
        Ok(existing) => existing != content,
        Err(_) => true,
    };
    if needs_write {
        std::fs::write(&shim_path, content)
            .map_err(|e| format!("Failed to write cc-spec shim: {}", e))?;
    }

    Ok(shim_dir)
}

#[cfg(not(debug_assertions))]
fn resolve_release_sidecar_dir(app_handle: &tauri::AppHandle) -> Option<PathBuf> {
    use tauri::Manager;

    let resource_dir = app_handle.path().resource_dir().ok()?;
    let dir = resource_dir.join("sidecar");
    if dir.exists() {
        Some(dir)
    } else {
        None
    }
}

fn build_augmented_path(
    app_handle: &tauri::AppHandle,
    codex_bin: Option<&str>,
) -> Option<String> {
    let mut extra_dirs: Vec<PathBuf> = Vec::new();

    // 1) cc-spec 可执行（release：sidecar；debug：shim）
    #[cfg(debug_assertions)]
    {
        if let Ok(dir) = ensure_dev_ccspec_shim() {
            extra_dirs.push(dir);
        }
    }
    #[cfg(not(debug_assertions))]
    {
        if let Some(dir) = resolve_release_sidecar_dir(app_handle) {
            extra_dirs.push(dir);
        }
    }

    // 2) codex 可执行目录（可选）
    if let Some(codex) = codex_bin {
        let p = PathBuf::from(codex);
        if let Some(parent) = p.parent() {
            extra_dirs.push(parent.to_path_buf());
        }
    }

    // 没有需要注入的内容就不覆盖 PATH
    if extra_dirs.is_empty() {
        return None;
    }

    let sep = if cfg!(windows) { ";" } else { ":" };
    let existing = env::var_os("PATH").unwrap_or_default();
    let mut segments: Vec<String> = extra_dirs
        .into_iter()
        .filter_map(|d| d.to_str().map(|s| s.to_string()))
        .filter(|s| !s.trim().is_empty())
        .collect();

    let existing_str = existing.to_string_lossy().to_string();
    if !existing_str.trim().is_empty() {
        segments.push(existing_str);
    }

    Some(segments.join(sep))
}
