use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use tauri::Emitter;

use crate::sidecar::run_ccspec_command;

#[derive(Clone, Debug, Serialize, Deserialize, Default)]
pub struct IndexStatus {
    pub initialized: bool,
    pub last_updated: Option<String>,
    pub file_count: u32,
    pub index_version: Option<String>,
    pub levels: Option<IndexLevels>,
}

#[derive(Clone, Debug, Serialize, Deserialize, Default)]
pub struct IndexLevels {
    pub l1_summary: bool,
    pub l2_symbols: bool,
    pub l3_details: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct IndexInitRequest {
    pub project_path: String,
    pub levels: Vec<String>,
    pub force: bool,
}

#[tauri::command]
pub async fn get_index_status(project_path: String) -> Result<IndexStatus, String> {
    let status_path = PathBuf::from(&project_path)
        .join(".cc-spec")
        .join("index")
        .join("status.json");

    if !status_path.exists() {
        return Ok(IndexStatus::default());
    }

    let raw = std::fs::read_to_string(&status_path)
        .map_err(|e| format!("Failed to read index status: {}", e))?;

    serde_json::from_str(&raw)
        .map_err(|e| format!("Failed to parse index status: {}", e))
}

#[tauri::command]
pub async fn check_index_exists(project_path: String) -> Result<bool, String> {
    let index_dir = PathBuf::from(&project_path)
        .join(".cc-spec")
        .join("index");
    Ok(index_dir.exists())
}

#[tauri::command]
pub async fn init_index(
    project_path: String,
    levels: Vec<String>,
    app_handle: tauri::AppHandle,
) -> Result<(), String> {
    // 通知前端索引初始化开始
    let _ = app_handle.emit("index.init.started", serde_json::json!({
        "project_path": &project_path,
        "levels": &levels,
    }));

    // 通过 sidecar 模块调用 cc-spec init --force
    // 使用 --force 实现增量更新，确保获取最新的模板和配置
    let result = run_ccspec_command(
        vec!["init".into(), "--force".into()],
        Some(project_path.clone()),
        app_handle.clone(),
    )
    .await?;

    // 通知前端索引初始化完成
    let _ = app_handle.emit("index.init.completed", serde_json::json!({
        "project_path": &project_path,
        "success": result.success,
        "stdout": &result.stdout,
        "stderr": &result.stderr,
    }));

    if result.success {
        Ok(())
    } else {
        // 包含 stdout 和 stderr 以便调试
        let error_msg = if !result.stderr.is_empty() {
            result.stderr
        } else if !result.stdout.is_empty() {
            result.stdout
        } else {
            format!("exit code: {:?}", result.exit_code)
        };
        Err(format!("Index init failed: {}", error_msg))
    }
}

#[tauri::command]
pub async fn update_index(
    project_path: String,
    app_handle: tauri::AppHandle,
) -> Result<(), String> {
    let _ = app_handle.emit("index.update.started", serde_json::json!({
        "project_path": &project_path,
    }));

    // 通过 sidecar 模块调用 cc-spec init --force（强制重新初始化）
    let result = run_ccspec_command(
        vec!["init".into(), "--force".into()],
        Some(project_path.clone()),
        app_handle.clone(),
    )
    .await?;

    let _ = app_handle.emit("index.update.completed", serde_json::json!({
        "project_path": &project_path,
        "success": result.success,
    }));

    if result.success {
        Ok(())
    } else {
        let error_msg = if !result.stderr.is_empty() {
            result.stderr
        } else if !result.stdout.is_empty() {
            result.stdout
        } else {
            format!("exit code: {:?}", result.exit_code)
        };
        Err(format!("Index update failed: {}", error_msg))
    }
}

#[tauri::command]
pub async fn get_index_settings_prompt_dismissed(project_path: String) -> Result<bool, String> {
    let settings_path = PathBuf::from(&project_path)
        .join(".cc-spec")
        .join("tools-settings.json");
    let legacy_settings_path = PathBuf::from(&project_path)
        .join(".cc-spec")
        .join("viewer-settings.json");

    if !settings_path.exists() {
        if !legacy_settings_path.exists() {
            return Ok(false);
        }
    }

    let raw = std::fs::read_to_string(&settings_path)
        .or_else(|_| std::fs::read_to_string(&legacy_settings_path))
        .map_err(|e| format!("Failed to read settings: {}", e))?;

    let settings: serde_json::Value = serde_json::from_str(&raw)
        .map_err(|e| format!("Failed to parse settings: {}", e))?;

    Ok(settings.get("index_prompt_dismissed")
        .and_then(|v| v.as_bool())
        .unwrap_or(false))
}

#[tauri::command]
pub async fn set_index_settings_prompt_dismissed(
    project_path: String,
    dismissed: bool,
) -> Result<(), String> {
    let settings_path = PathBuf::from(&project_path)
        .join(".cc-spec")
        .join("tools-settings.json");

    let mut settings: serde_json::Value = if settings_path.exists() {
        let raw = std::fs::read_to_string(&settings_path)
            .map_err(|e| format!("Failed to read settings: {}", e))?;
        serde_json::from_str(&raw).unwrap_or(serde_json::json!({}))
    } else {
        serde_json::json!({})
    };

    settings["index_prompt_dismissed"] = serde_json::json!(dismissed);

    std::fs::create_dir_all(settings_path.parent().unwrap())
        .map_err(|e| format!("Failed to create settings dir: {}", e))?;

    std::fs::write(&settings_path, serde_json::to_string_pretty(&settings).unwrap())
        .map_err(|e| format!("Failed to write settings: {}", e))?;

    Ok(())
}
