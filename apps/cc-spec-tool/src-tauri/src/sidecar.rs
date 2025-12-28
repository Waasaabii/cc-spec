// sidecar.rs - cc-spec sidecar 调用模块

use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::process::Stdio;
use tauri::Emitter;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;

#[cfg(debug_assertions)]
fn dev_project_root() -> Result<PathBuf, String> {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .parent()
        .and_then(|p| p.parent())
        .and_then(|p| p.parent())
        .map(|p| p.to_path_buf())
        .ok_or_else(|| "Failed to resolve cc-spec repo root from CARGO_MANIFEST_DIR".to_string())
}

#[cfg(not(debug_assertions))]
fn dev_project_root() -> Result<PathBuf, String> {
    Err("dev_mode".to_string())
}

/// Sidecar 命令执行结果
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SidecarResult {
    pub success: bool,
    pub stdout: String,
    pub stderr: String,
    pub exit_code: Option<i32>,
}

/// 预处理后的 cc-spec 命令（可用于 streaming / 自定义读取 stdout/stderr）
#[derive(Clone, Debug)]
pub struct PreparedCcspecCommand {
    pub program: String,
    pub args: Vec<String>,
    pub cwd: Option<String>,
}

/// 获取 sidecar 可执行文件路径
fn get_sidecar_path(_app_handle: &tauri::AppHandle) -> Result<PathBuf, String> {
    // 开发模式：使用 uv run -m cc_spec
    #[cfg(debug_assertions)]
    {
        // 在开发模式下返回 None，使用系统命令
        return Err("dev_mode".to_string());
    }

    // 生产模式：使用打包的 sidecar
    #[cfg(not(debug_assertions))]
    {
        use tauri::Manager;

        let sidecar_name = if cfg!(windows) {
            "cc-spec.exe"
        } else {
            "cc-spec"
        };

        _app_handle
            .path()
            .resource_dir()
            .map_err(|e| format!("Failed to get resource directory: {}", e))?
            .join("sidecar")
            .join(sidecar_name)
            .canonicalize()
            .map_err(|e| format!("Sidecar path not found: {}", e))
    }
}

/// 解析 cc-spec 调用方式（dev: `uv run -m cc_spec`；release: sidecar 可执行），并返回可直接 spawn 的 program/args/cwd。
pub fn prepare_ccspec_command(
    args: Vec<String>,
    working_dir: Option<String>,
    app_handle: &tauri::AppHandle,
) -> Result<PreparedCcspecCommand, String> {
    match get_sidecar_path(app_handle) {
        Ok(path) => Ok(PreparedCcspecCommand {
            program: path.to_string_lossy().to_string(),
            args,
            cwd: working_dir,
        }),
        Err(e) if e == "dev_mode" => {
            // 开发模式：uv run 需要显式指定 cc-spec 项目目录，否则在目标项目目录会变成“直接 spawn cc-spec”
            // 目标：让 uv 使用 cc-spec 仓库作为 project，同时让 cc-spec 在 working_dir 下运行。
            let project_root = dev_project_root()?;
            let mut all_args = vec![
                "run".to_string(),
                "--project".to_string(),
                project_root.to_string_lossy().to_string(),
            ];
            if let Some(dir) = &working_dir {
                all_args.push("--directory".to_string());
                all_args.push(dir.clone());
            }
            // 兼容 Windows：避免某些环境下 `cc-spec` 被当作外部可执行文件而触发 os error 193
            all_args.push("-m".to_string());
            all_args.push("cc_spec".to_string());
            all_args.extend(args);

            Ok(PreparedCcspecCommand {
                program: "uv".to_string(),
                args: all_args,
                cwd: Some(project_root.to_string_lossy().to_string()),
            })
        }
        Err(e) => Err(e),
    }
}

/// 执行 cc-spec 命令（同步）
#[tauri::command]
pub async fn run_ccspec_command(
    args: Vec<String>,
    working_dir: Option<String>,
    app_handle: tauri::AppHandle,
) -> Result<SidecarResult, String> {
    let prepared = prepare_ccspec_command(args, working_dir, &app_handle)?;
    let program = prepared.program;
    let cmd_args = prepared.args;
    let command_cwd = prepared.cwd;

    let mut command = Command::new(&program);
    command.args(&cmd_args);
    
    // 设置 UTF-8 编码环境变量，修复 Windows 上中文乱码问题
    command.env("PYTHONIOENCODING", "utf-8");
    command.env("PYTHONUTF8", "1");
    
    command.stdout(Stdio::piped());
    command.stderr(Stdio::piped());

    if let Some(dir) = command_cwd {
        command.current_dir(dir);
    }

    let output = command
        .output()
        .await
        .map_err(|e| format!("Command execution failed: {}", e))?;

    Ok(SidecarResult {
        success: output.status.success(),
        stdout: String::from_utf8_lossy(&output.stdout).to_string(),
        stderr: String::from_utf8_lossy(&output.stderr).to_string(),
        exit_code: output.status.code(),
    })
}

/// 执行 cc-spec 命令并流式输出（通过事件）
#[tauri::command]
pub async fn run_ccspec_stream(
    args: Vec<String>,
    working_dir: Option<String>,
    event_id: String,
    app_handle: tauri::AppHandle,
) -> Result<(), String> {
    let (program, cmd_args, command_cwd) = match get_sidecar_path(&app_handle) {
        Ok(path) => (
            path.to_string_lossy().to_string(),
            args,
            working_dir.clone(),
        ),
        Err(e) if e == "dev_mode" => {
            let project_root = dev_project_root()?;
            let mut all_args = vec![
                "run".to_string(),
                "--project".to_string(),
                project_root.to_string_lossy().to_string(),
            ];
            if let Some(dir) = &working_dir {
                all_args.push("--directory".to_string());
                all_args.push(dir.clone());
            }
            all_args.push("-m".to_string());
            all_args.push("cc_spec".to_string());
            all_args.extend(args);
            ("uv".to_string(), all_args, Some(project_root.to_string_lossy().to_string()))
        }
        Err(e) => return Err(e),
    };

    let mut command = Command::new(&program);
    command.args(&cmd_args);
    
    // 设置 UTF-8 编码环境变量，修复 Windows 上中文乱码问题
    command.env("PYTHONIOENCODING", "utf-8");
    command.env("PYTHONUTF8", "1");
    
    command.stdout(Stdio::piped());
    command.stderr(Stdio::piped());

    if let Some(dir) = command_cwd {
        command.current_dir(dir);
    }

    let mut child = command
        .spawn()
        .map_err(|e| format!("Failed to start command: {}", e))?;

    let stdout = child.stdout.take().ok_or("Failed to capture stdout")?;
    let stderr = child.stderr.take().ok_or("Failed to capture stderr")?;

    let event_id_clone = event_id.clone();
    let app_handle_clone = app_handle.clone();

    // 读取 stdout
    let stdout_handle = tokio::spawn(async move {
        let reader = BufReader::new(stdout);
        let mut lines = reader.lines();
        while let Ok(Some(line)) = lines.next_line().await {
            let _ = app_handle_clone.emit(
                &format!("ccspec:stdout:{}", event_id_clone),
                line,
            );
        }
    });

    let event_id_clone2 = event_id.clone();
    let app_handle_clone2 = app_handle.clone();

    // 读取 stderr
    let stderr_handle = tokio::spawn(async move {
        let reader = BufReader::new(stderr);
        let mut lines = reader.lines();
        while let Ok(Some(line)) = lines.next_line().await {
            let _ = app_handle_clone2.emit(
                &format!("ccspec:stderr:{}", event_id_clone2),
                line,
            );
        }
    });

    // 等待进程完成
    let status = child
        .wait()
        .await
        .map_err(|e| format!("Failed to wait for process: {}", e))?;

    // 等待输出读取完成
    let _ = stdout_handle.await;
    let _ = stderr_handle.await;

    // 发送完成事件
    let _ = app_handle.emit(
        &format!("ccspec:done:{}", event_id),
        status.code().unwrap_or(-1),
    );

    Ok(())
}

/// 检查 cc-spec sidecar 是否可用
#[tauri::command]
pub async fn check_sidecar_available(app_handle: tauri::AppHandle) -> Result<bool, String> {
    match get_sidecar_path(&app_handle) {
        Ok(path) => Ok(path.exists()),
        Err(e) if e == "dev_mode" => {
            // 开发模式检查 uv + cc-spec 项目是否可用
            let project_root = dev_project_root()?;
            let project_root_str = project_root.to_string_lossy().to_string();
            let output = Command::new("uv")
                .args([
                    "run",
                    "--project",
                    &project_root_str,
                    "-m",
                    "cc_spec",
                    "--version",
                ])
                .current_dir(project_root)
                .output()
                .await;
            Ok(output.is_ok() && output.unwrap().status.success())
        }
        Err(_) => Ok(false),
    }
}

/// 获取 cc-spec 版本
#[tauri::command]
pub async fn get_ccspec_version(app_handle: tauri::AppHandle) -> Result<String, String> {
    let result = run_ccspec_command(vec!["--version".to_string()], None, app_handle).await?;
    if result.success {
        Ok(result.stdout.trim().to_string())
    } else {
        Err(result.stderr)
    }
}
