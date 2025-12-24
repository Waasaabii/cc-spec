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
    p.canonicalize()
        .map_err(|e| format!("Failed to normalize path: {}", e))
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

    let record = ProjectRecord {
        id: Uuid::new_v4().to_string(),
        name: derive_name(&normalized),
        path: normalized_str,
        created_at: now.clone(),
        updated_at: now.clone(),
        last_opened_at: Some(now),
    };

    state.current_project_id = Some(record.id.clone());
    state.projects.push(record.clone());
    save_state(state)?;
    Ok(record)
}

#[tauri::command]
pub async fn list_projects() -> Result<Vec<ProjectRecord>, String> {
    let state = load_state();
    Ok(state.projects)
}

#[tauri::command]
pub async fn get_current_project() -> Result<Option<ProjectRecord>, String> {
    let state = load_state();
    if let Some(ref current_id) = state.current_project_id {
        let project = state.projects.into_iter().find(|p| p.id == *current_id);
        return Ok(project);
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
