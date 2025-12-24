// export.rs - 对话历史导出功能

use serde::{Deserialize, Serialize};
use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::PathBuf;
use tauri::Emitter;
use zip::write::FileOptions;
use zip::ZipWriter;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ExportMetadata {
    pub version: String,
    pub exported_at: String,
    pub project_path: String,
    pub session_count: usize,
    pub total_events: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ImportResult {
    pub success: bool,
    pub sessions_imported: usize,
    pub sessions_skipped: usize,
    pub message: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ConflictResolution {
    pub strategy: String, // "skip" | "overwrite" | "merge"
}

fn get_history_dir(project_path: &str) -> PathBuf {
    PathBuf::from(project_path)
        .join(".cc-spec")
        .join("tools-history")
}

fn legacy_history_dir(project_path: &str) -> PathBuf {
    PathBuf::from(project_path)
        .join(".cc-spec")
        .join("viewer-history")
}

fn resolve_history_dir(project_path: &str) -> PathBuf {
    let new_dir = get_history_dir(project_path);
    let legacy_dir = legacy_history_dir(project_path);
    if !new_dir.exists() && legacy_dir.exists() {
        return legacy_dir;
    }
    new_dir
}

#[tauri::command]
pub async fn export_history(
    project_path: String,
    output_path: String,
    app_handle: tauri::AppHandle,
) -> Result<String, String> {
    let history_dir = resolve_history_dir(&project_path);

    if !history_dir.exists() {
        return Err("No history found to export".to_string());
    }

    let _ = app_handle.emit("export.started", serde_json::json!({
        "project_path": &project_path,
    }));

    // 收集所有 ndjson 文件
    let mut session_files: Vec<PathBuf> = Vec::new();
    let mut total_events = 0usize;

    if let Ok(entries) = fs::read_dir(&history_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().map(|e| e == "ndjson").unwrap_or(false) {
                // 计算事件数
                if let Ok(content) = fs::read_to_string(&path) {
                    total_events += content.lines().count();
                }
                session_files.push(path);
            }
        }
    }

    if session_files.is_empty() {
        return Err("No session files found".to_string());
    }

    // 创建 ZIP 文件
    let zip_path = PathBuf::from(&output_path);
    let file = File::create(&zip_path)
        .map_err(|e| format!("Failed to create export file: {}", e))?;

    let mut zip = ZipWriter::new(file);
    let options = FileOptions::default()
        .compression_method(zip::CompressionMethod::Deflated)
        .unix_permissions(0o644);

    // 写入 metadata.json
    let metadata = ExportMetadata {
        version: "1.0".to_string(),
        exported_at: chrono::Utc::now().to_rfc3339(),
        project_path: project_path.clone(),
        session_count: session_files.len(),
        total_events,
    };

    zip.start_file("metadata.json", options)
        .map_err(|e| format!("Failed to write metadata: {}", e))?;
    zip.write_all(serde_json::to_string_pretty(&metadata).unwrap().as_bytes())
        .map_err(|e| format!("Failed to write metadata: {}", e))?;

    // 写入会话文件
    for (i, session_path) in session_files.iter().enumerate() {
        let file_name = session_path
            .file_name()
            .unwrap()
            .to_string_lossy()
            .to_string();

        let _ = app_handle.emit("export.progress", serde_json::json!({
            "current": i + 1,
            "total": session_files.len(),
            "file": &file_name,
        }));

        let mut content = Vec::new();
        File::open(session_path)
            .map_err(|e| format!("Failed to read session file: {}", e))?
            .read_to_end(&mut content)
            .map_err(|e| format!("Failed to read session file: {}", e))?;

        zip.start_file(format!("sessions/{}", file_name), options)
            .map_err(|e| format!("Failed to add session to archive: {}", e))?;
        zip.write_all(&content)
            .map_err(|e| format!("Failed to write session to archive: {}", e))?;
    }

    zip.finish()
        .map_err(|e| format!("Failed to finalize archive: {}", e))?;

    let _ = app_handle.emit("export.completed", serde_json::json!({
        "success": true,
        "path": &output_path,
        "session_count": session_files.len(),
    }));

    Ok(output_path)
}

#[tauri::command]
pub async fn import_history(
    project_path: String,
    import_path: String,
    conflict_resolution: ConflictResolution,
    app_handle: tauri::AppHandle,
) -> Result<ImportResult, String> {
    let zip_path = PathBuf::from(&import_path);

    if !zip_path.exists() {
        return Err("Import file not found".to_string());
    }

    let _ = app_handle.emit("import.started", serde_json::json!({
        "path": &import_path,
    }));

    let file = File::open(&zip_path)
        .map_err(|e| format!("Failed to open import file: {}", e))?;

    let mut archive = zip::ZipArchive::new(file)
        .map_err(|e| format!("Failed to read archive: {}", e))?;

    // 读取 metadata
    let metadata: ExportMetadata = {
        let mut meta_file = archive
            .by_name("metadata.json")
            .map_err(|_| "Invalid archive: missing metadata.json")?;
        let mut content = String::new();
        meta_file
            .read_to_string(&mut content)
            .map_err(|e| format!("Failed to read metadata: {}", e))?;
        serde_json::from_str(&content)
            .map_err(|e| format!("Invalid metadata: {}", e))?
    };

    let history_dir = get_history_dir(&project_path);
    fs::create_dir_all(&history_dir)
        .map_err(|e| format!("Failed to create history directory: {}", e))?;

    let mut imported = 0usize;
    let mut skipped = 0usize;

    // 导入会话文件
    for i in 0..archive.len() {
        let mut file = archive.by_index(i).map_err(|e| format!("Archive error: {}", e))?;
        let name = file.name().to_string();

        if !name.starts_with("sessions/") || name.ends_with('/') {
            continue;
        }

        let file_name = name.strip_prefix("sessions/").unwrap();
        let dest_path = history_dir.join(file_name);

        let _ = app_handle.emit("import.progress", serde_json::json!({
            "current": imported + skipped + 1,
            "total": metadata.session_count,
            "file": file_name,
        }));

        // 处理冲突
        if dest_path.exists() {
            match conflict_resolution.strategy.as_str() {
                "skip" => {
                    skipped += 1;
                    continue;
                }
                "overwrite" => {
                    // 继续写入
                }
                "merge" => {
                    // 合并：读取现有内容并追加
                    let mut existing = fs::read_to_string(&dest_path).unwrap_or_default();
                    let mut new_content = String::new();
                    file.read_to_string(&mut new_content)
                        .map_err(|e| format!("Failed to read session: {}", e))?;

                    // 追加新内容
                    existing.push_str(&new_content);
                    fs::write(&dest_path, existing)
                        .map_err(|e| format!("Failed to write merged session: {}", e))?;
                    imported += 1;
                    continue;
                }
                _ => {
                    skipped += 1;
                    continue;
                }
            }
        }

        // 写入文件
        let mut content = Vec::new();
        file.read_to_end(&mut content)
            .map_err(|e| format!("Failed to read session: {}", e))?;

        fs::write(&dest_path, content)
            .map_err(|e| format!("Failed to write session: {}", e))?;

        imported += 1;
    }

    let result = ImportResult {
        success: true,
        sessions_imported: imported,
        sessions_skipped: skipped,
        message: format!(
            "Imported {} sessions, skipped {} ({})",
            imported,
            skipped,
            conflict_resolution.strategy
        ),
    };

    let _ = app_handle.emit("import.completed", serde_json::json!({
        "success": true,
        "imported": imported,
        "skipped": skipped,
    }));

    Ok(result)
}

#[tauri::command]
pub async fn get_export_size_estimate(project_path: String) -> Result<u64, String> {
    let history_dir = resolve_history_dir(&project_path);

    if !history_dir.exists() {
        return Ok(0);
    }

    let mut total_size = 0u64;

    if let Ok(entries) = fs::read_dir(&history_dir) {
        for entry in entries.flatten() {
            if let Ok(metadata) = entry.metadata() {
                total_size += metadata.len();
            }
        }
    }

    Ok(total_size)
}
