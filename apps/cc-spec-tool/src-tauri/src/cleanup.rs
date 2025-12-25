use std::collections::hash_map::DefaultHasher;
use std::fs;
use std::hash::{Hash, Hasher};
use std::path::{Path, PathBuf};

use crate::skills;

const MANAGED_START: &str = "<!-- CC-SPEC:START -->";
const MANAGED_END: &str = "<!-- CC-SPEC:END -->";

fn home_dir() -> PathBuf {
    std::env::var_os("USERPROFILE")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(PathBuf::from))
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")))
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

fn hash_project_path(project_path: &str) -> String {
    let mut hasher = DefaultHasher::new();
    project_path.hash(&mut hasher);
    format!("{:x}", hasher.finish())
}

fn try_remove_dir_all(path: &Path, errors: &mut Vec<String>) {
    if !path.exists() {
        return;
    }
    if let Err(e) = fs::remove_dir_all(path) {
        errors.push(format!("Failed to remove dir {}: {}", path.to_string_lossy(), e));
    }
}

fn try_remove_file(path: &Path, errors: &mut Vec<String>) {
    if !path.exists() {
        return;
    }
    if let Err(e) = fs::remove_file(path) {
        errors.push(format!("Failed to remove file {}: {}", path.to_string_lossy(), e));
    }
}

fn try_remove_empty_dir(path: &Path, errors: &mut Vec<String>) {
    if !path.exists() || !path.is_dir() {
        return;
    }
    let is_empty = match fs::read_dir(path) {
        Ok(mut it) => it.next().is_none(),
        Err(e) => {
            errors.push(format!(
                "Failed to read dir {}: {}",
                path.to_string_lossy(),
                e
            ));
            return;
        }
    };
    if !is_empty {
        return;
    }
    if let Err(e) = fs::remove_dir(path) {
        errors.push(format!(
            "Failed to remove empty dir {}: {}",
            path.to_string_lossy(),
            e
        ));
    }
}

fn remove_managed_block(content: &str) -> Option<String> {
    let start = content.find(MANAGED_START)?;
    let end = content.find(MANAGED_END)?;
    if end <= start {
        return None;
    }
    let end_inclusive = end + MANAGED_END.len();
    let before = &content[..start];
    let after = &content[end_inclusive..];
    let updated = format!("{}{}", before, after);
    Some(updated.trim().to_string())
}

fn cleanup_managed_file(path: &Path, errors: &mut Vec<String>) {
    if !path.exists() {
        return;
    }
    let raw = match fs::read_to_string(path) {
        Ok(v) => v,
        Err(e) => {
            errors.push(format!(
                "Failed to read managed file {}: {}",
                path.to_string_lossy(),
                e
            ));
            return;
        }
    };
    let Some(updated) = remove_managed_block(&raw) else {
        return;
    };
    if updated.trim().is_empty() {
        try_remove_file(path, errors);
        return;
    }
    if let Err(e) = fs::write(path, updated + "\n") {
        errors.push(format!(
            "Failed to write managed file {}: {}",
            path.to_string_lossy(),
            e
        ));
    }
}

fn cleanup_tools_config(project_path: &str, warnings: &mut Vec<String>) {
    let mut config = match skills::load_tools_config() {
        Ok(c) => c,
        Err(e) => {
            warnings.push(format!("Failed to load tools.yaml: {}", e));
            return;
        }
    };

    let mut removed_any = config.projects.remove(project_path).is_some();

    // Windows: remove case-insensitively to be robust across path case differences.
    #[cfg(windows)]
    if !removed_any {
        if let Some(key) = config
            .projects
            .keys()
            .find(|k| k.eq_ignore_ascii_case(project_path))
            .cloned()
        {
            removed_any = config.projects.remove(&key).is_some();
        }
    }

    if removed_any {
        if let Err(e) = skills::save_tools_config(&config) {
            warnings.push(format!("Failed to save tools.yaml: {}", e));
        }
    }
}

fn cleanup_local_history(project_path: &str, warnings: &mut Vec<String>) {
    let hash = hash_project_path(project_path);
    let tools_history = home_dir()
        .join(".cc-spec")
        .join("tools")
        .join(&hash)
        .join("history.json");
    let legacy_history = home_dir()
        .join(".cc-spec")
        .join("viewer")
        .join(&hash)
        .join("history.json");

    try_remove_file(&tools_history, warnings);
    try_remove_file(&legacy_history, warnings);

    if let Some(parent) = tools_history.parent() {
        try_remove_empty_dir(parent, warnings);
    }
    if let Some(parent) = legacy_history.parent() {
        try_remove_empty_dir(parent, warnings);
    }
}

/// 清理项目内所有 cc-spec 相关产物（备份需求不在此命令内）
///
/// 清理范围（尽量不影响非 cc-spec 文件）：
/// - `<project>/.cc-spec/`
/// - `<project>/.cc-specignore`
/// - `<project>/.claude/commands/cc-spec/`（cc-spec namespace 命令）
/// - `<project>/.claude/commands/cc-spec-*`（cc-spec-tool 安装的 commands 目录）
/// - `<project>/.claude/skills/cc-spec-standards/`
/// - `<project>/AGENTS.md` 中的 CC-SPEC managed block（若文件仅剩空内容则删除）
/// - `~/.cc-spec/tools/<hash>/history.json`（及 legacy viewer 目录）
/// - `~/.cc-spec/tools.yaml` 中的项目状态 entry
#[tauri::command]
pub async fn cleanup_project_ccspec(project_path: String) -> Result<Vec<String>, String> {
    let normalized = normalize_project_path(&project_path)?;
    let normalized_str = normalized.to_string_lossy().to_string();

    let mut errors: Vec<String> = Vec::new();
    let mut warnings: Vec<String> = Vec::new();

    // 1) Project-local artifacts
    let cc_spec_dir = normalized.join(".cc-spec");
    try_remove_dir_all(&cc_spec_dir, &mut errors);

    let ignore_path = normalized.join(".cc-specignore");
    try_remove_file(&ignore_path, &mut errors);

    let claude_commands_dir = normalized.join(".claude").join("commands");
    let cc_spec_namespace_dir = claude_commands_dir.join("cc-spec");
    try_remove_dir_all(&cc_spec_namespace_dir, &mut errors);

    if claude_commands_dir.exists() {
        match fs::read_dir(&claude_commands_dir) {
            Ok(entries) => {
                for entry in entries.flatten() {
                    let path = entry.path();
                    let name = path
                        .file_name()
                        .and_then(|n| n.to_str())
                        .unwrap_or_default();
                    if path.is_dir() && name.starts_with("cc-spec-") {
                        try_remove_dir_all(&path, &mut errors);
                    }
                }
            }
            Err(e) => errors.push(format!(
                "Failed to read commands dir {}: {}",
                claude_commands_dir.to_string_lossy(),
                e
            )),
        }
    }

    let cc_spec_standards_dir = normalized
        .join(".claude")
        .join("skills")
        .join("cc-spec-standards");
    try_remove_dir_all(&cc_spec_standards_dir, &mut errors);

    let agents_md = normalized.join("AGENTS.md");
    cleanup_managed_file(&agents_md, &mut warnings);

    // 2) Tool-local artifacts
    cleanup_local_history(&normalized_str, &mut warnings);
    cleanup_tools_config(&normalized_str, &mut warnings);

    if !errors.is_empty() {
        return Err(errors.join("\n"));
    }

    Ok(warnings)
}
