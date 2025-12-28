use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::process::Stdio;
use tauri::Emitter;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;
use uuid::Uuid;

use crate::sidecar::{prepare_ccspec_command, SidecarResult};
use crate::skills::{scan_project_skills_dir, load_tools_config, save_tools_config, ProjectState};

async fn run_ccspec_stage(
    args: Vec<String>,
    working_dir: Option<String>,
    run_id: &str,
    stage: &str,
    app_handle: &tauri::AppHandle,
) -> Result<SidecarResult, String> {
    let prepared = prepare_ccspec_command(args, working_dir, app_handle)?;
    let stage_name = stage.to_string();
    let run_id = run_id.to_string();
    let command_display = format!("{} {}", prepared.program, prepared.args.join(" "));

    let _ = app_handle.emit(
        "index:init:stage",
        serde_json::json!({
            "run_id": &run_id,
            "stage": &stage_name,
            "state": "started",
            "command": command_display,
        }),
    );

    let mut command = Command::new(&prepared.program);
    command.args(&prepared.args);

    // 统一 Python 输出编码：避免 Windows GBK 控制台下 Rich 输出 unicode 触发 UnicodeEncodeError
    command.env("PYTHONIOENCODING", "utf-8");
    command.env("PYTHONUTF8", "1");

    command.stdout(Stdio::piped());
    command.stderr(Stdio::piped());

    if let Some(dir) = prepared.cwd {
        command.current_dir(dir);
    }

    let mut child = match command.spawn() {
        Ok(child) => child,
        Err(e) => {
            let _ = app_handle.emit(
                "index:init:log",
                serde_json::json!({
                    "run_id": &run_id,
                    "stage": &stage_name,
                    "stream": "system",
                    "line": format!("Failed to start command: {}", e),
                }),
            );
            let _ = app_handle.emit(
                "index:init:stage",
                serde_json::json!({
                    "run_id": &run_id,
                    "stage": &stage_name,
                    "state": "failed",
                    "error": format!("{}", e),
                }),
            );
            return Err(format!("Failed to start cc-spec command: {}", e));
        }
    };

    let stdout_task = if let Some(stdout) = child.stdout.take() {
        let handle = app_handle.clone();
        let stage = stage_name.clone();
        let run_id = run_id.clone();
        Some(tokio::spawn(async move {
            let reader = BufReader::new(stdout);
            let mut lines = reader.lines();
            let mut collected: Vec<String> = Vec::new();
            while let Ok(Some(line)) = lines.next_line().await {
                collected.push(line.clone());
                let _ = handle.emit(
                    "index:init:log",
                    serde_json::json!({
                        "run_id": &run_id,
                        "stage": &stage,
                        "stream": "stdout",
                        "line": line,
                    }),
                );
            }
            collected
        }))
    } else {
        None
    };

    let stderr_task = if let Some(stderr) = child.stderr.take() {
        let handle = app_handle.clone();
        let stage = stage_name.clone();
        let run_id = run_id.clone();
        Some(tokio::spawn(async move {
            let reader = BufReader::new(stderr);
            let mut lines = reader.lines();
            let mut collected: Vec<String> = Vec::new();
            while let Ok(Some(line)) = lines.next_line().await {
                collected.push(line.clone());
                let _ = handle.emit(
                    "index:init:log",
                    serde_json::json!({
                        "run_id": &run_id,
                        "stage": &stage,
                        "stream": "stderr",
                        "line": line,
                    }),
                );
            }
            collected
        }))
    } else {
        None
    };

    let status = match child.wait().await {
        Ok(status) => status,
        Err(e) => {
            let _ = app_handle.emit(
                "index:init:log",
                serde_json::json!({
                    "run_id": &run_id,
                    "stage": &stage_name,
                    "stream": "system",
                    "line": format!("Failed to wait for command: {}", e),
                }),
            );
            let _ = app_handle.emit(
                "index:init:stage",
                serde_json::json!({
                    "run_id": &run_id,
                    "stage": &stage_name,
                    "state": "failed",
                    "error": format!("{}", e),
                }),
            );
            return Err(format!("Failed to wait for cc-spec command: {}", e));
        }
    };

    let stdout_lines = match stdout_task {
        Some(task) => task.await.unwrap_or_default(),
        None => Vec::new(),
    };
    let stderr_lines = match stderr_task {
        Some(task) => task.await.unwrap_or_default(),
        None => Vec::new(),
    };

    let stdout = stdout_lines.join("\n");
    let stderr = stderr_lines.join("\n");
    let success = status.success();
    let exit_code = status.code();

    let _ = app_handle.emit(
        "index:init:stage",
        serde_json::json!({
            "run_id": &run_id,
            "stage": &stage_name,
            "state": if success { "completed" } else { "failed" },
            "exit_code": exit_code,
        }),
    );

    Ok(SidecarResult {
        success,
        stdout,
        stderr,
        exit_code,
    })
}

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
    let run_id = format!("idx_{}_{}", chrono::Utc::now().timestamp_millis(), Uuid::new_v4());

    // 通知前端索引初始化开始
    let _ = app_handle.emit(
        "index:init:started",
        serde_json::json!({
            "run_id": &run_id,
            "project_path": &project_path,
            "levels": &levels,
        }),
    );

    // 0) 先确保 stage1 bootstrap（生成 standards/commands/config）
    // 使用 --force 实现增量更新，确保获取最新的模板和配置
    let bootstrap = run_ccspec_stage(
        vec!["init".into(), "--force".into()],
        Some(project_path.clone()),
        &run_id,
        "bootstrap",
        &app_handle,
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
        let _ = app_handle.emit(
            "index:init:completed",
            serde_json::json!({
                "run_id": &run_id,
                "project_path": &project_path,
                "success": false,
                "stage": "bootstrap",
                "stdout": &bootstrap.stdout,
                "stderr": &bootstrap.stderr,
            }),
        );
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

    // 1) 多级索引为必选：生成 PROJECT_INDEX / FOLDER_INDEX（默认推荐 L1+L2）
    let mut index_args: Vec<String> = vec!["init-index".into()];
    for lvl in &levels {
        index_args.push("--level".into());
        index_args.push(lvl.clone());
    }

    let index_res = run_ccspec_stage(
        index_args,
        Some(project_path.clone()),
        &run_id,
        "index",
        &app_handle,
    )
    .await?;
    if !index_res.success {
        let error_msg = if !index_res.stderr.is_empty() {
            index_res.stderr.clone()
        } else if !index_res.stdout.is_empty() {
            index_res.stdout.clone()
        } else {
            format!("exit code: {:?}", index_res.exit_code)
        };
        let _ = app_handle.emit(
            "index:init:completed",
            serde_json::json!({
                "run_id": &run_id,
                "project_path": &project_path,
                "success": false,
                "stage": "index",
                "stdout": &index_res.stdout,
                "stderr": &index_res.stderr,
            }),
        );
        return Err(format!("Index init failed (index): {}", error_msg));
    }

    // 3) 写入 `.cc-spec/index/status.json` 哨兵文件（供 UI 判定“已完成”）
    let _ = app_handle.emit(
        "index:init:stage",
        serde_json::json!({
            "run_id": &run_id,
            "stage": "finalize",
            "state": "started",
        }),
    );
    let cc_spec_dir = PathBuf::from(&project_path).join(".cc-spec");
    let index_dir = cc_spec_dir.join("index");
    std::fs::create_dir_all(&index_dir)
        .map_err(|e| format!("Failed to create index dir: {}", e))?;

    let manifest_path = index_dir.join("manifest.json");
    let file_count = std::fs::read_to_string(&manifest_path)
        .ok()
        .and_then(|raw| serde_json::from_str::<serde_json::Value>(&raw).ok())
        .and_then(|v| v.get("files").and_then(|f| f.as_array()).map(|a| a.len() as u32))
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
    let _ = app_handle.emit(
        "index:init:stage",
        serde_json::json!({
            "run_id": &run_id,
            "stage": "finalize",
            "state": "completed",
        }),
    );

    // 4) 自动扫描并注册项目 Skills（cc-spec init 会生成 .claude/skills/cc-spec-standards/）
    if let Ok(scan_result) = scan_project_skills_dir(&project_path) {
        if !scan_result.skills.is_empty() {
            let skill_names: Vec<String> = scan_result.skills.iter().map(|s| s.name.clone()).collect();

            // 更新 tools.yaml 中的项目状态
            if let Ok(mut config) = load_tools_config() {
                let state = config.projects.entry(project_path.clone()).or_insert_with(|| ProjectState {
                    initialized_at: chrono::Utc::now().to_rfc3339(),
                    commands_version: "0.2.2".to_string(),
                    skills_installed: Vec::new(),
                    custom_overrides: Vec::new(),
                });

                // 合并已有的和新扫描到的 skills（去重）
                for name in skill_names {
                    if !state.skills_installed.contains(&name) {
                        state.skills_installed.push(name);
                    }
                }

                let _ = save_tools_config(&config);
            }
        }
    }

    let _ = app_handle.emit(
        "index:init:completed",
        serde_json::json!({
            "run_id": &run_id,
            "project_path": &project_path,
            "success": true,
            "stdout": format!("{}\n{}", bootstrap.stdout, index_res.stdout),
            "stderr": format!("{}\n{}", bootstrap.stderr, index_res.stderr),
        }),
    );

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

    // 当前 update 语义：复用 init_index 的最新逻辑（bootstrap + multi-level index）
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
