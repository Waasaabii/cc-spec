// projects.rs - Project registry and selection

use chrono::Utc;
use once_cell::sync::Lazy;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use std::sync::Mutex;
use uuid::Uuid;

static PROJECTS_LOCK: Lazy<Mutex<()>> = Lazy::new(|| Mutex::new(()));

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProjectRecord {
    pub id: String,
    pub name: String,
    pub path: String,
    pub description: Option<String>,
    pub created_at: String,
    pub updated_at: String,
    pub last_opened_at: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
struct ProjectsState {
    pub version: u32,
    pub updated_at: String,
    pub current_project_id: Option<String>,
    pub projects: Vec<ProjectRecord>,
}

impl Default for ProjectsState {
    fn default() -> Self {
        Self {
            version: 1,
            updated_at: String::new(),
            current_project_id: None,
            projects: Vec::new(),
        }
    }
}

fn now_iso() -> String {
    Utc::now().to_rfc3339()
}

fn app_data_dir() -> PathBuf {
    let base = std::env::var("LOCALAPPDATA")
        .or_else(|_| std::env::var("HOME"))
        .unwrap_or_else(|_| ".".to_string());
    PathBuf::from(base).join("cc-spec-tools")
}

fn projects_path() -> PathBuf {
    app_data_dir().join("projects.json")
}

fn legacy_app_data_dir() -> PathBuf {
    let base = std::env::var("LOCALAPPDATA")
        .or_else(|_| std::env::var("HOME"))
        .unwrap_or_else(|_| ".".to_string());
    PathBuf::from(base).join("cc-spec-viewer")
}

fn legacy_projects_path() -> PathBuf {
    legacy_app_data_dir().join("projects.json")
}

fn normalize_path(path: &str) -> Result<PathBuf, String> {
    let p = PathBuf::from(path);
    if !p.exists() {
        return Err("Project path does not exist".to_string());
    }
    let canonical = p.canonicalize()
        .map_err(|e| format!("Failed to normalize path: {}", e))?;
    
    // Windows 的 canonicalize() 会产生 \\?\ 前缀，需要移除
    #[cfg(windows)]
    {
        let path_str = canonical.to_string_lossy();
        if path_str.starts_with(r"\\?\") {
            return Ok(PathBuf::from(&path_str[4..]));
        }
    }
    
    Ok(canonical)
}

fn same_path(a: &str, b: &str) -> bool {
    if cfg!(windows) {
        a.eq_ignore_ascii_case(b)
    } else {
        a == b
    }
}

fn load_state() -> ProjectsState {
    let _guard = PROJECTS_LOCK.lock().unwrap();
    let path = projects_path();
    if !path.exists() {
        let legacy = legacy_projects_path();
        if legacy.exists() {
            if let Ok(raw) = fs::read_to_string(&legacy) {
                if let Ok(state) = serde_json::from_str::<ProjectsState>(&raw) {
                    let _ = save_state(state.clone());
                    return state;
                }
            }
        }
        return ProjectsState::default();
    }
    let raw = match fs::read_to_string(&path) {
        Ok(raw) => raw,
        Err(_) => return ProjectsState::default(),
    };
    serde_json::from_str(&raw).unwrap_or_default()
}

fn save_state(mut state: ProjectsState) -> Result<(), String> {
    let _guard = PROJECTS_LOCK.lock().unwrap();
    state.version = 1;
    state.updated_at = now_iso();
    let path = projects_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|e| format!("Failed to create project registry dir: {}", e))?;
    }
    let tmp = path.with_extension("json.tmp");
    fs::write(&tmp, serde_json::to_string_pretty(&state).unwrap())
        .map_err(|e| format!("Failed to write project registry: {}", e))?;
    fs::rename(&tmp, &path)
        .map_err(|e| format!("Failed to persist project registry: {}", e))?;
    Ok(())
}

fn find_project_by_path<'a>(
    state: &'a mut ProjectsState,
    path: &str,
) -> Option<&'a mut ProjectRecord> {
    state
        .projects
        .iter_mut()
        .find(|p| same_path(p.path.as_str(), path))
}

fn derive_name(path: &PathBuf) -> String {
    path.file_name()
        .and_then(|s| s.to_str())
        .map(|s| s.to_string())
        .unwrap_or_else(|| path.to_string_lossy().to_string())
}

/// 从项目目录读取 README 文件并提取摘要
fn read_readme_description(project_path: &PathBuf) -> Option<String> {
    // 尝试多种 README 文件名
    let readme_names = ["README.md", "readme.md", "README.MD", "Readme.md", "README", "readme"];
    
    for name in readme_names {
        let readme_path = project_path.join(name);
        if readme_path.exists() {
            if let Ok(content) = fs::read_to_string(&readme_path) {
                return Some(extract_readme_summary(&content));
            }
        }
    }
    None
}

/// 从 README 内容中提取摘要（前几行非标题内容）
fn extract_readme_summary(content: &str) -> String {
    let mut lines: Vec<&str> = Vec::new();
    let mut char_count = 0;
    const MAX_CHARS: usize = 300; // 限制最大字符数
    
    for line in content.lines() {
        let trimmed = line.trim();
        
        // 跳过空行
        if trimmed.is_empty() {
            continue;
        }
        
        // 跳过一级标题（项目名通常在一级标题）
        if trimmed.starts_with("# ") {
            continue;
        }
        
        // 跳过徽章行（通常包含 ![...] 或 [!...）
        if trimmed.starts_with("[![") || trimmed.starts_with("![" ) {
            continue;
        }
        
        // 收集有意义的文本行
        let line_len = trimmed.len();
        if char_count + line_len > MAX_CHARS {
            // 截断到 MAX_CHARS
            let remaining = MAX_CHARS - char_count;
            if remaining > 20 {
                let truncated: String = trimmed.chars().take(remaining - 3).collect();
                lines.push(Box::leak(format!("{}...", truncated).into_boxed_str()));
            }
            break;
        }
        
        lines.push(trimmed);
        char_count += line_len;
        
        // 最多收集 3 行
        if lines.len() >= 3 {
            break;
        }
    }
    
    lines.join(" ")
}

#[tauri::command]
pub async fn import_project(path: String) -> Result<ProjectRecord, String> {
    let normalized = normalize_path(&path)?;
    let normalized_str = normalized.to_string_lossy().to_string();
    let mut state = load_state();
    let now = now_iso();

    if let Some(existing) = {
        let found = find_project_by_path(&mut state, &normalized_str);
        if let Some(existing) = found {
            existing.updated_at = now.clone();
            existing.last_opened_at = Some(now.clone());
            Some(existing.clone())
        } else {
            None
        }
    } {
        state.current_project_id = Some(existing.id.clone());
        save_state(state)?;
        return Ok(existing);
    }

    // 读取 README 描述 (作为 Description 的来源之一)
    let readme_description = read_readme_description(&normalized);

    // 智能识别项目元数据
    let (detected_name, detected_desc) = detect_project_metadata(&normalized);
    
    // 优先使用 README 的描述，如果没有则使用配置文件中的描述
    let final_description = readme_description.or(detected_desc);
    
    let record = ProjectRecord {
        id: Uuid::new_v4().to_string(),
        name: detected_name, // 使用智能识别的名称
        path: normalized_str,
        description: final_description,
        created_at: now.clone(),
        updated_at: now.clone(),
        last_opened_at: Some(now),
    };

    state.current_project_id = Some(record.id.clone());
    state.projects.push(record.clone());
    save_state(state)?;
    Ok(record)
}

/// 智能检测项目元数据 (Name, Description)
fn detect_project_metadata(path: &PathBuf) -> (String, Option<String>) {
    let folder_name = derive_name(path);
    let mut found_name = None;
    let mut found_desc = None;

    // Helper to check if name is meaningful
    let is_valid = |s: &str| !s.trim().is_empty();

    // Priority 1: package.json
    if let Ok(content) = fs::read_to_string(path.join("package.json")) {
        if let Ok(json) = serde_json::from_str::<serde_json::Value>(&content) {
            if let Some(n) = json["name"].as_str() {
                if is_valid(n) { found_name = Some(n.to_string()); }
            }
            if let Some(d) = json["description"].as_str() {
                if is_valid(d) { found_desc = Some(d.to_string()); }
            }
        }
    }

    // Priority 2: Cargo.toml (if package.json didn't yield a name)
    if found_name.is_none() {
        if let Ok(content) = fs::read_to_string(path.join("Cargo.toml")) {
            // 简单的 TOML 解析
            let mut in_package = false;
            for line in content.lines() {
                let trimmed = line.trim();
                if trimmed == "[package]" {
                    in_package = true;
                    continue;
                }
                if in_package {
                    if trimmed.starts_with("[") { break; } 
                    if trimmed.starts_with("name") {
                        if let Some(val) = parse_toml_string(trimmed) {
                            found_name = Some(val);
                        }
                    }
                    if trimmed.starts_with("description") && found_desc.is_none() {
                         if let Some(val) = parse_toml_string(trimmed) {
                            found_desc = Some(val);
                        }
                    }
                }
            }
        }
    }

    // Priority 3: pyproject.toml
    if found_name.is_none() {
         if let Ok(content) = fs::read_to_string(path.join("pyproject.toml")) {
             let mut in_project = false;
             let mut in_poetry = false;
             
            for line in content.lines() {
                let trimmed = line.trim();
                 if trimmed == "[project]" { in_project = true; in_poetry = false; continue; }
                 if trimmed == "[tool.poetry]" { in_project = false; in_poetry = true; continue; }
                 
                 if in_project || in_poetry {
                     if trimmed.starts_with("[") && trimmed != "[project]" && trimmed != "[tool.poetry]" { 
                         if trimmed.ends_with("]") {
                             in_project = false; 
                             in_poetry = false;
                         }
                     }
                     if trimmed.starts_with("name") {
                         if let Some(val) = parse_toml_string(trimmed) {
                             found_name = Some(val);
                         }
                     }
                      if trimmed.starts_with("description") && found_desc.is_none() {
                         if let Some(val) = parse_toml_string(trimmed) {
                            found_desc = Some(val);
                        }
                    }
                 }
            }
         }
    }

    (found_name.unwrap_or(folder_name), found_desc)
}

fn parse_toml_string(line: &str) -> Option<String> {
    if let Some(idx) = line.find('=') {
        let val_part = line[idx+1..].trim();
        if val_part.starts_with('"') && val_part.ends_with('"') {
            return Some(val_part[1..val_part.len()-1].to_string());
        }
        if val_part.starts_with('\'') && val_part.ends_with('\'') {
             return Some(val_part[1..val_part.len()-1].to_string());
        }
    }
    None
}

#[tauri::command]
pub async fn list_projects() -> Result<Vec<ProjectRecord>, String> {
    let mut state = load_state();
    let mut updated = false;
    
    // 为缺少 description 的项目自动读取 README
    for project in state.projects.iter_mut() {
        if project.description.is_none() {
            let path = PathBuf::from(&project.path);
            if path.exists() {
                project.description = read_readme_description(&path);
                if project.description.is_some() {
                    updated = true;
                }
            }
        }
    }
    
    // 如果有更新则保存
    if updated {
        let _ = save_state(state.clone());
    }
    
    Ok(state.projects)
}

#[tauri::command]
pub async fn get_current_project() -> Result<Option<ProjectRecord>, String> {
    let mut state = load_state();
    let current_id = match &state.current_project_id {
        Some(id) => id.clone(),
        None => return Ok(None),
    };

    // 先查找项目索引
    let project_index = state.projects.iter().position(|p| p.id == current_id);
    if let Some(idx) = project_index {
        // 检查是否需要更新 description
        let needs_update = state.projects[idx].description.is_none();
        let path = PathBuf::from(&state.projects[idx].path);

        if needs_update && path.exists() {
            if let Some(desc) = read_readme_description(&path) {
                state.projects[idx].description = Some(desc);
                let _ = save_state(state.clone());
            }
        }

        return Ok(Some(state.projects[idx].clone()));
    }
    Ok(None)
}

#[tauri::command]
pub async fn set_current_project(project_id: String) -> Result<Option<ProjectRecord>, String> {
    let mut state = load_state();
    let now = now_iso();
    let mut selected: Option<ProjectRecord> = None;
    for project in state.projects.iter_mut() {
        if project.id == project_id {
            project.last_opened_at = Some(now.clone());
            project.updated_at = now.clone();
            selected = Some(project.clone());
            break;
        }
    }
    if selected.is_none() {
        return Ok(None);
    }
    state.current_project_id = selected.as_ref().map(|p| p.id.clone());
    save_state(state)?;
    Ok(selected)
}

#[tauri::command]
pub async fn remove_project(project_id: String) -> Result<bool, String> {
    let mut state = load_state();
    let before = state.projects.len();
    state.projects.retain(|p| p.id != project_id);
    let removed = state.projects.len() != before;
    if removed {
        if state.current_project_id.as_deref() == Some(project_id.as_str()) {
            state.current_project_id = None;
        }
        save_state(state)?;
    }
    Ok(removed)
}
