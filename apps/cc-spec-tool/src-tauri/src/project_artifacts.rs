use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_yaml::Value;
use std::cmp::Ordering;
use std::fs::{self, File};
use std::io::{BufRead, BufReader};
use std::path::{Component, Path, PathBuf};
use std::process::Command;

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ArtifactRoot {
    pub id: String,
    pub label: String,
    pub kind: String, // "dir" | "file"
    pub exists: bool,
    pub rel_path: String,
    pub abs_path: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ArtifactEntry {
    pub name: String,
    pub kind: String, // "dir" | "file"
    pub rel_path: String,
    pub abs_path: String,
    pub size: u64,
    pub modified_at: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TextPreview {
    pub content: String,
    pub start_line: u32,
    pub end_line: u32,
    pub truncated: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ChangeSummary {
    pub dir_name: String,
    pub change_name: Option<String>,
    pub current_stage: Option<String>,
    pub current_stage_status: Option<String>,
    pub created_at: Option<String>,
    pub updated_at: Option<String>,
}

fn normalize_project_path(project_path: &str) -> Result<PathBuf, String> {
    let path = PathBuf::from(project_path);
    if !path.exists() {
        return Err("Project path does not exist".to_string());
    }
    let canonical = path
        .canonicalize()
        .map_err(|e| format!("Failed to normalize path: {}", e))?;

    // Windows canonicalize() may add \\?\ prefix, remove it for consistency.
    #[cfg(windows)]
    {
        let path_str = canonical.to_string_lossy();
        if path_str.starts_with(r"\\?\") {
            return Ok(PathBuf::from(&path_str[4..]));
        }
    }

    Ok(canonical)
}

fn to_slash_path(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn safe_rel_path(rel: &str) -> Result<PathBuf, String> {
    let p = PathBuf::from(rel);
    if p.as_os_str().is_empty() {
        return Ok(PathBuf::new());
    }
    if p.is_absolute() {
        return Err("Absolute path is not allowed".to_string());
    }
    for comp in p.components() {
        match comp {
            Component::Normal(_) => {}
            Component::CurDir => {}
            Component::ParentDir => return Err("Parent dir '..' is not allowed".to_string()),
            Component::RootDir | Component::Prefix(_) => {
                return Err("Path prefix/root is not allowed".to_string())
            }
        }
    }
    Ok(p)
}

fn artifact_root_path(project_root: &Path, root_id: &str) -> Result<(PathBuf, String, String), String> {
    // returns (abs_path, kind, rel_path)
    match root_id {
        "cc_spec" => Ok((project_root.join(".cc-spec"), "dir".to_string(), ".cc-spec".to_string())),
        "cc_specignore" => Ok((
            project_root.join(".cc-specignore"),
            "file".to_string(),
            ".cc-specignore".to_string(),
        )),
        "agents_md" => Ok((project_root.join("AGENTS.md"), "file".to_string(), "AGENTS.md".to_string())),
        "claude_standards" => Ok((
            project_root
                .join(".claude")
                .join("skills")
                .join("cc-spec-standards"),
            "dir".to_string(),
            ".claude/skills/cc-spec-standards".to_string(),
        )),
        _ => Err(format!("Unknown root id: {}", root_id)),
    }
}

fn resolve_artifact_path(project_root: &Path, root_id: &str, rel_path: &str) -> Result<PathBuf, String> {
    let (root_path, kind, _root_rel) = artifact_root_path(project_root, root_id)?;
    if kind == "file" {
        let rel = safe_rel_path(rel_path)?;
        if !rel.as_os_str().is_empty() {
            return Err("File root does not accept rel_path".to_string());
        }
        return Ok(root_path);
    }
    let rel = safe_rel_path(rel_path)?;
    Ok(root_path.join(rel))
}

fn format_modified(metadata: &fs::Metadata) -> Option<String> {
    metadata.modified().ok().map(|t| {
        let dt: DateTime<Utc> = t.into();
        dt.to_rfc3339()
    })
}

#[tauri::command]
pub async fn list_project_artifact_roots(project_path: String) -> Result<Vec<ArtifactRoot>, String> {
    let project_root = normalize_project_path(&project_path)?;
    let roots = vec![
        ("cc_spec", ".cc-spec"),
        ("cc_specignore", ".cc-specignore"),
        ("agents_md", "AGENTS.md"),
        ("claude_standards", ".claude/skills/cc-spec-standards"),
    ];

    let mut result = Vec::new();
    for (id, label) in roots {
        let (path, kind, rel_path) = artifact_root_path(&project_root, id)?;
        result.push(ArtifactRoot {
            id: id.to_string(),
            label: label.to_string(),
            kind,
            exists: path.exists(),
            rel_path,
            abs_path: path.to_string_lossy().to_string(),
        });
    }
    Ok(result)
}

#[tauri::command]
pub async fn list_project_artifact_dir(
    project_path: String,
    root_id: String,
    rel_dir: String,
) -> Result<Vec<ArtifactEntry>, String> {
    let project_root = normalize_project_path(&project_path)?;
    let dir_path = resolve_artifact_path(&project_root, &root_id, &rel_dir)?;
    if !dir_path.exists() {
        return Ok(Vec::new());
    }
    if !dir_path.is_dir() {
        return Err("Not a directory".to_string());
    }

    let mut entries: Vec<ArtifactEntry> = Vec::new();
    let read_dir = fs::read_dir(&dir_path).map_err(|e| format!("Failed to read dir: {}", e))?;
    for entry in read_dir.flatten() {
        let path = entry.path();
        let name = path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("unknown")
            .to_string();
        let meta = entry.metadata().ok();
        let is_dir = meta.as_ref().map(|m| m.is_dir()).unwrap_or_else(|| path.is_dir());
        let kind = if is_dir { "dir" } else { "file" }.to_string();
        let size = meta.as_ref().map(|m| if m.is_file() { m.len() } else { 0 }).unwrap_or(0);
        let modified_at = meta.as_ref().and_then(format_modified);

        let rel_joined = if rel_dir.trim().is_empty() {
            PathBuf::from(&name)
        } else {
            PathBuf::from(&rel_dir).join(&name)
        };
        entries.push(ArtifactEntry {
            name,
            kind,
            rel_path: to_slash_path(&rel_joined),
            abs_path: path.to_string_lossy().to_string(),
            size,
            modified_at,
        });
    }

    entries.sort_by(|a, b| {
        match (a.kind.as_str(), b.kind.as_str()) {
            ("dir", "file") => Ordering::Less,
            ("file", "dir") => Ordering::Greater,
            _ => a.name.to_lowercase().cmp(&b.name.to_lowercase()),
        }
    });

    Ok(entries)
}

#[tauri::command]
pub async fn read_project_artifact_text(
    project_path: String,
    root_id: String,
    rel_file: String,
    start_line: Option<u32>,
    max_lines: Option<u32>,
) -> Result<TextPreview, String> {
    let project_root = normalize_project_path(&project_path)?;
    let file_path = resolve_artifact_path(&project_root, &root_id, &rel_file)?;
    if !file_path.exists() {
        return Err("File not found".to_string());
    }
    if !file_path.is_file() {
        return Err("Not a file".to_string());
    }

    let start = start_line.unwrap_or(1).max(1);
    let max = max_lines.unwrap_or(400).max(1).min(2000);

    let file = File::open(&file_path).map_err(|e| format!("Failed to open file: {}", e))?;
    let reader = BufReader::new(file);
    let mut current: u32 = 0;
    let mut lines: Vec<String> = Vec::new();
    let mut truncated = false;

    for line in reader.lines() {
        current += 1;
        if current < start {
            continue;
        }
        if current >= start && current < start + max {
            let text = line.unwrap_or_default();
            lines.push(text);
        } else {
            truncated = true;
            break;
        }
    }

    let end_line = if lines.is_empty() {
        start.saturating_sub(1)
    } else {
        start + (lines.len() as u32) - 1
    };

    Ok(TextPreview {
        content: lines.join("\n"),
        start_line: start,
        end_line,
        truncated,
    })
}

fn extract_yaml_str(value: &Value, key: &str) -> Option<String> {
    value
        .get(key)
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
}

fn extract_stage_status(doc: &Value, current_stage: &str) -> Option<String> {
    let stages = doc.get("stages")?;
    let stage = stages.get(current_stage)?;
    stage
        .get("status")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
}

#[tauri::command]
pub async fn list_project_changes(project_path: String) -> Result<Vec<ChangeSummary>, String> {
    let project_root = normalize_project_path(&project_path)?;
    let changes_dir = project_root.join(".cc-spec").join("changes");
    if !changes_dir.exists() || !changes_dir.is_dir() {
        return Ok(Vec::new());
    }

    let mut summaries: Vec<ChangeSummary> = Vec::new();
    let entries = fs::read_dir(&changes_dir).map_err(|e| format!("Failed to read changes dir: {}", e))?;
    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        let dir_name = path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("unknown")
            .to_string();
        let status_path = path.join("status.yaml");
        let mut change_name: Option<String> = None;
        let mut current_stage: Option<String> = None;
        let mut current_stage_status: Option<String> = None;
        let mut created_at: Option<String> = None;
        if status_path.exists() {
            if let Ok(raw) = fs::read_to_string(&status_path) {
                if let Ok(doc) = serde_yaml::from_str::<Value>(&raw) {
                    change_name = extract_yaml_str(&doc, "change_name");
                    created_at = extract_yaml_str(&doc, "created_at");
                    current_stage = extract_yaml_str(&doc, "current_stage");
                    if let Some(stage) = current_stage.as_deref() {
                        current_stage_status = extract_stage_status(&doc, stage);
                    }
                }
            }
        }
        let updated_at = entry
            .metadata()
            .ok()
            .and_then(|m| format_modified(&m));

        summaries.push(ChangeSummary {
            dir_name,
            change_name,
            current_stage,
            current_stage_status,
            created_at,
            updated_at,
        });
    }

    // newest first (by updated_at string, RFC3339 sorts lexicographically)
    summaries.sort_by(|a, b| b.updated_at.cmp(&a.updated_at));
    Ok(summaries)
}

#[tauri::command]
pub async fn open_project_artifact_in_vscode(
    project_path: String,
    root_id: String,
    rel_file: String,
    line: Option<u32>,
    col: Option<u32>,
) -> Result<(), String> {
    let project_root = normalize_project_path(&project_path)?;
    let file_path = resolve_artifact_path(&project_root, &root_id, &rel_file)?;
    if !file_path.exists() {
        return Err("File not found".to_string());
    }

    let mut cmd = Command::new("code");
    if let Some(line) = line {
        let col = col.unwrap_or(1).max(1);
        let target = format!("{}:{}:{}", file_path.to_string_lossy(), line.max(1), col);
        cmd.args(["-g", &target]);
    } else {
        cmd.arg(file_path.to_string_lossy().to_string());
    }

    // If code isn't available, fall back to default open (without line support).
    if cmd.spawn().is_ok() {
        return Ok(());
    }

    #[cfg(windows)]
    {
        Command::new("cmd")
            .args(["/C", "start", "", &file_path.to_string_lossy()])
            .spawn()
            .map_err(|e| format!("Failed to open file: {}", e))?;
        return Ok(());
    }

    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .arg(&file_path)
            .spawn()
            .map_err(|e| format!("Failed to open file: {}", e))?;
        return Ok(());
    }

    #[cfg(all(unix, not(target_os = "macos")))]
    {
        Command::new("xdg-open")
            .arg(&file_path)
            .spawn()
            .map_err(|e| format!("Failed to open file: {}", e))?;
        return Ok(());
    }
}

#[tauri::command]
pub async fn reveal_project_artifact_in_file_manager(
    project_path: String,
    root_id: String,
    rel_path: String,
) -> Result<(), String> {
    let project_root = normalize_project_path(&project_path)?;
    let target_path = resolve_artifact_path(&project_root, &root_id, &rel_path)?;
    if !target_path.exists() {
        return Err("Path not found".to_string());
    }

    #[cfg(windows)]
    {
        if target_path.is_dir() {
            Command::new("explorer.exe")
                .arg(&target_path)
                .spawn()
                .map_err(|e| format!("Failed to open explorer: {}", e))?;
        } else {
            Command::new("explorer.exe")
                .args(["/select,", &target_path.to_string_lossy()])
                .spawn()
                .map_err(|e| format!("Failed to open explorer: {}", e))?;
        }
        return Ok(());
    }

    #[cfg(target_os = "macos")]
    {
        if target_path.is_dir() {
            Command::new("open")
                .arg(&target_path)
                .spawn()
                .map_err(|e| format!("Failed to open: {}", e))?;
        } else {
            Command::new("open")
                .args(["-R", &target_path.to_string_lossy()])
                .spawn()
                .map_err(|e| format!("Failed to reveal: {}", e))?;
        }
        return Ok(());
    }

    #[cfg(all(unix, not(target_os = "macos")))]
    {
        let open_path = if target_path.is_dir() {
            target_path.to_path_buf()
        } else {
            target_path
                .parent()
                .map(|p| p.to_path_buf())
                .unwrap_or(target_path.to_path_buf())
        };
        Command::new("xdg-open")
            .arg(open_path)
            .spawn()
            .map_err(|e| format!("Failed to reveal: {}", e))?;
        Ok(())
    }
}
