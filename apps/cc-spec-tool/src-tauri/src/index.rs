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
    // 以 `.cc-spec/index/status.json` 作为“初始化/索引已完成”的哨兵文件。
    // 注意：`.cc-spec/` 目录可能被 runtime/settings 提前创建，不能作为可靠判定。
    let status_path = PathBuf::from(&project_path)
        .join(".cc-spec")
        .join("index")
        .join("status.json");
    if !status_path.exists() {
        return Ok(false);
    }
    let raw = std::fs::read_to_string(&status_path).unwrap_or_default();
    let parsed: Result<IndexStatus, _> = serde_json::from_str(&raw);
    Ok(parsed.map(|s| s.initialized).unwrap_or(false))
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

    // 0) 先确保 stage1 bootstrap（生成 standards/commands/config）
    // 使用 --force 实现增量更新，确保获取最新的模板和配置
    let bootstrap = run_ccspec_command(
        vec!["init".into(), "--force".into()],
        Some(project_path.clone()),
        app_handle.clone(),
    )
    .await?;

    if !bootstrap.success {
        let error_msg = if !bootstrap.stderr.is_empty() {
            bootstrap.stderr.clone()
        } else if !bootstrap.stdout.is_empty() {
            bootstrap.stdout.clone()
        } else {
            format!("exit code: {:?}", bootstrap.exit_code)
        };
        let _ = app_handle.emit("index.init.completed", serde_json::json!({
            "project_path": &project_path,
            "success": false,
            "stdout": &bootstrap.stdout,
            "stderr": &bootstrap.stderr,
        }));
        return Err(format!("Index init failed (bootstrap): {}", error_msg));
    }

    // 0.5) Commands 版本文件（tool 用于展示/更新判定；实际内容由 cc-spec init 受管理区块更新）
    // 备注：与 `src-tauri/src/commands.rs` 中的 COMMANDS_VERSION 保持一致。
    let commands_dir = PathBuf::from(&project_path)
        .join(".claude")
        .join("commands")
        .join("cc-spec");
    let _ = std::fs::create_dir_all(&commands_dir);
    let _ = std::fs::write(commands_dir.join("VERSION"), "0.2.2\n");

    // 1) KB 为必选：根据当前状态决定 init vs update
    let kb_status = run_ccspec_command(
        vec!["kb".into(), "status".into(), "--json".into()],
        Some(project_path.clone()),
        app_handle.clone(),
    )
    .await?;

    let mut has_manifest = false;
    if kb_status.success {
        if let Ok(value) = serde_json::from_str::<serde_json::Value>(&kb_status.stdout) {
            if let Some(items) = value.get("条目").and_then(|v| v.as_array()) {
                for item in items {
                    let key = item.get("键").and_then(|v| v.as_str()).unwrap_or_default();
                    let exists = item.get("存在").and_then(|v| v.as_bool()).unwrap_or(false);
                    if key == "manifest" && exists {
                        has_manifest = true;
                        break;
                    }
                }
            }
        }
    }

    // 2) levels -> KB 参数（当前策略：L3 视为“更重/更全”）
    let has_l3 = levels.iter().any(|x| x == "l3");
    let reference_mode = if has_l3 { "full" } else { "index" };
    let chunking_strategy = if has_l3 { "smart" } else { "ast-only" };

    let mut kb_args: Vec<String> = vec!["kb".into()];
    kb_args.push(if has_manifest { "update".into() } else { "init".into() });
    kb_args.push("--reference-mode".into());
    kb_args.push(reference_mode.into());
    kb_args.push("--chunking-strategy".into());
    kb_args.push(chunking_strategy.into());

    let kb = run_ccspec_command(kb_args, Some(project_path.clone()), app_handle.clone()).await?;
    if !kb.success {
        let error_msg = if !kb.stderr.is_empty() {
            kb.stderr.clone()
        } else if !kb.stdout.is_empty() {
            kb.stdout.clone()
        } else {
            format!("exit code: {:?}", kb.exit_code)
        };
        let _ = app_handle.emit("index.init.completed", serde_json::json!({
            "project_path": &project_path,
            "success": false,
            "stdout": &kb.stdout,
            "stderr": &kb.stderr,
        }));
        return Err(format!("Index init failed (kb): {}", error_msg));
    }

    // 3) 写入 `.cc-spec/index/status.json` 哨兵文件（供 UI 判定“已完成”）
    let cc_spec_dir = PathBuf::from(&project_path).join(".cc-spec");
    let index_dir = cc_spec_dir.join("index");
    std::fs::create_dir_all(&index_dir)
        .map_err(|e| format!("Failed to create index dir: {}", e))?;

    let manifest_path = cc_spec_dir.join("kb.manifest.json");
    let file_count = std::fs::read_to_string(&manifest_path)
        .ok()
        .and_then(|raw| serde_json::from_str::<serde_json::Value>(&raw).ok())
        .and_then(|v| v.get("files").and_then(|f| f.as_object()).map(|o| o.len() as u32))
        .unwrap_or(0);

    let status = IndexStatus {
        initialized: true,
        last_updated: Some(chrono::Utc::now().to_rfc3339()),
        file_count,
        index_version: Some("0.2.2".to_string()),
        levels: Some(IndexLevels {
            l1_summary: levels.iter().any(|x| x == "l1"),
            l2_symbols: levels.iter().any(|x| x == "l2"),
            l3_details: levels.iter().any(|x| x == "l3"),
        }),
    };

    let status_path = index_dir.join("status.json");
    std::fs::write(&status_path, serde_json::to_string_pretty(&status).unwrap())
        .map_err(|e| format!("Failed to write index status: {}", e))?;

    // 通知前端索引初始化完成
    let _ = app_handle.emit("index.init.completed", serde_json::json!({
        "project_path": &project_path,
        "success": true,
        "stdout": format!("{}\n{}", bootstrap.stdout, kb.stdout),
        "stderr": format!("{}\n{}", bootstrap.stderr, kb.stderr),
    }));

    Ok(())
}

#[tauri::command]
pub async fn update_index(
    project_path: String,
    app_handle: tauri::AppHandle,
) -> Result<(), String> {
    let _ = app_handle.emit("index.update.started", serde_json::json!({
        "project_path": &project_path,
    }));

    // 当前 update 语义：复用 init_index 的最新逻辑（bootstrap + KB）
    // 备注：levels 暂时使用默认推荐值（l1/l2）
    let _ = init_index(project_path.clone(), vec!["l1".into(), "l2".into()], app_handle.clone()).await?;

    let _ = app_handle.emit("index.update.completed", serde_json::json!({
        "project_path": &project_path,
        "success": true,
    }));

    Ok(())
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
