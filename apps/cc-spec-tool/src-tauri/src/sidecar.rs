// sidecar.rs - cc-spec sidecar 调用模块

use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::process::Stdio;
use tauri::Emitter;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;

/// Sidecar 命令执行结果
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SidecarResult {
    pub success: bool,
    pub stdout: String,
    pub stderr: String,
    pub exit_code: Option<i32>,
}

/// 获取 sidecar 可执行文件路径
fn get_sidecar_path(_app_handle: &tauri::AppHandle) -> Result<PathBuf, String> {
    // 开发模式：使用 uv run cc-spec
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
            .map_err(|e| format!("获取资源目录失败: {}", e))?
            .join("sidecar")
            .join(sidecar_name)
            .canonicalize()
            .map_err(|e| format!("sidecar 路径不存在: {}", e))
    }
}

/// 执行 cc-spec 命令（同步）
#[tauri::command]
pub async fn run_ccspec_command(
    args: Vec<String>,
    working_dir: Option<String>,
    app_handle: tauri::AppHandle,
) -> Result<SidecarResult, String> {
    let (program, cmd_args) = match get_sidecar_path(&app_handle) {
        Ok(path) => (path.to_string_lossy().to_string(), args),
        Err(e) if e == "dev_mode" => {
            // 开发模式使用 uv run cc-spec
            let mut all_args = vec!["run".to_string(), "cc-spec".to_string()];
            all_args.extend(args);
            ("uv".to_string(), all_args)
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

    if let Some(dir) = working_dir {
        command.current_dir(dir);
    }

    let output = command
        .output()
        .await
        .map_err(|e| format!("执行命令失败: {}", e))?;

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
    let (program, cmd_args) = match get_sidecar_path(&app_handle) {
        Ok(path) => (path.to_string_lossy().to_string(), args),
        Err(e) if e == "dev_mode" => {
            let mut all_args = vec!["run".to_string(), "cc-spec".to_string()];
            all_args.extend(args);
            ("uv".to_string(), all_args)
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

    if let Some(dir) = working_dir {
        command.current_dir(dir);
    }

    let mut child = command
        .spawn()
        .map_err(|e| format!("启动命令失败: {}", e))?;

    let stdout = child.stdout.take().ok_or("无法获取 stdout")?;
    let stderr = child.stderr.take().ok_or("无法获取 stderr")?;

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
        .map_err(|e| format!("等待进程失败: {}", e))?;

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
            // 开发模式检查 uv 是否可用
            let output = Command::new("uv")
                .args(["run", "cc-spec", "--version"])
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
