// commands.rs - Claude Commands 管理（/cc-spec:<cmd>）
//
// 目标：以 cc-spec CLI 生成的 `.claude/commands/cc-spec/*.md` 为准，
// 由 tool 负责检测与一键生成/更新（通过 `cc-spec init --force`）。

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

use crate::sidecar::run_ccspec_command;

/// Commands 版本（用于 tool 的展示/更新判定）
///
/// 说明：这里使用 tool 版本号即可；实际 command 内容由 `cc-spec init` 生成并受管理区块更新。
const COMMANDS_VERSION: &str = "0.2.2";

/// `/cc-spec:<cmd>` 列表（与 `src/cc_spec/core/command_generator.py` 的 CC_SPEC_COMMANDS 对齐）
const COMMANDS: &[&str] = &[
    "init",
    "init-index",
    "update-index",
    "check-index",
    "specify",
    "clarify",
    "plan",
    "apply",
    "accept",
    "archive",
    "quick-delta",
    "list",
    "goto",
    "update",
];

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CommandStatus {
    pub name: String,
    pub installed: bool,
    pub version: Option<String>,
    pub path: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CommandsInstallResult {
    pub success: bool,
    pub installed_count: usize,
    pub skipped_count: usize,
    pub errors: Vec<String>,
    pub commands: Vec<CommandStatus>,
}

fn get_project_commands_dir(project_path: &str) -> PathBuf {
    PathBuf::from(project_path)
        .join(".claude")
        .join("commands")
        .join("cc-spec")
}

fn read_commands_version(commands_dir: &PathBuf) -> Option<String> {
    fs::read_to_string(commands_dir.join("VERSION"))
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
}

fn write_commands_version(commands_dir: &PathBuf, version: &str) -> Result<(), String> {
    fs::create_dir_all(commands_dir)
        .map_err(|e| format!("Failed to create commands directory: {}", e))?;
    fs::write(commands_dir.join("VERSION"), version)
        .map_err(|e| format!("Failed to write commands VERSION: {}", e))
}

#[tauri::command]
pub async fn check_commands_status(project_path: String) -> Result<Vec<CommandStatus>, String> {
    let commands_dir = get_project_commands_dir(&project_path);
    let shared_version = read_commands_version(&commands_dir);

    let statuses = COMMANDS
        .iter()
        .map(|cmd| {
            let file_name = format!("{}.md", cmd);
            let path = commands_dir.join(file_name);
            let installed = path.exists();
            CommandStatus {
                name: format!("/cc-spec:{}", cmd),
                installed,
                version: shared_version.clone(),
                path: installed.then(|| path.to_string_lossy().to_string()),
            }
        })
        .collect();

    Ok(statuses)
}

#[tauri::command]
pub async fn install_commands(
    project_path: String,
    force: Option<bool>,
    app_handle: tauri::AppHandle,
) -> Result<CommandsInstallResult, String> {
    let force = force.unwrap_or(false);

    // 通过 cc-spec init 生成/更新 commands（受管理区块）
    // - 这里始终使用 --force：确保模板/commands/standards 都是最新
    // - 未来如果需要更精细控制，可将 force 映射为是否携带 --force
    let args = if force {
        vec!["init".into(), "--force".into()]
    } else {
        vec!["init".into(), "--force".into()]
    };

    let result = run_ccspec_command(args, Some(project_path.clone()), app_handle).await?;
    if !result.success {
        let error_msg = if !result.stderr.is_empty() {
            result.stderr
        } else if !result.stdout.is_empty() {
            result.stdout
        } else {
            format!("exit code: {:?}", result.exit_code)
        };
        return Err(format!("Failed to run cc-spec init: {}", error_msg));
    }

    // 写入 VERSION（tool 展示用；也用于 update_needed 判定）
    let commands_dir = get_project_commands_dir(&project_path);
    let _ = write_commands_version(&commands_dir, COMMANDS_VERSION);

    let commands = check_commands_status(project_path).await?;
    let installed_count = commands.iter().filter(|c| c.installed).count();
    let mut errors: Vec<String> = Vec::new();
    for cmd in &commands {
        if !cmd.installed {
            errors.push(format!("Missing command file: {}", cmd.name));
        }
    }

    Ok(CommandsInstallResult {
        success: errors.is_empty(),
        installed_count,
        skipped_count: 0,
        errors,
        commands,
    })
}

#[tauri::command]
pub async fn uninstall_commands(project_path: String) -> Result<(), String> {
    let commands_dir = get_project_commands_dir(&project_path);
    if commands_dir.exists() {
        fs::remove_dir_all(&commands_dir)
            .map_err(|e| format!("Failed to delete commands dir: {}", e))?;
    }
    Ok(())
}

#[tauri::command]
pub async fn get_commands_version() -> Result<String, String> {
    Ok(COMMANDS_VERSION.to_string())
}

#[tauri::command]
pub async fn check_commands_update_needed(project_path: String) -> Result<bool, String> {
    let commands_dir = get_project_commands_dir(&project_path);
    let version = read_commands_version(&commands_dir);
    if version.as_deref() != Some(COMMANDS_VERSION) {
        return Ok(true);
    }

    for cmd in COMMANDS {
        let path = commands_dir.join(format!("{}.md", cmd));
        if !path.exists() {
            return Ok(true);
        }
    }

    Ok(false)
}
