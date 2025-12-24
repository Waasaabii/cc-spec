// skills.rs - Commands 管理模块
//
// 功能:
// - 安装 cc-spec commands 到项目 .claude/commands/ 目录
// - 版本检查和更新
// - Commands 状态查询

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use tauri::Manager;

/// Skills 版本
const SKILLS_VERSION: &str = "1.0.0";

/// Skills 列表
const SKILL_NAMES: &[&str] = &[
    "cc-spec-specify",
    "cc-spec-clarify",
    "cc-spec-plan",
    "cc-spec-apply",
    "cc-spec-accept",
    "cc-spec-archive",
];

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SkillStatus {
    pub name: String,
    pub installed: bool,
    pub version: Option<String>,
    pub path: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SkillsInstallResult {
    pub success: bool,
    pub installed_count: usize,
    pub skipped_count: usize,
    pub errors: Vec<String>,
    pub skills: Vec<SkillStatus>,
}

/// 获取资源目录 (打包后的 skills 位置)
fn get_resource_skills_dir(app_handle: &tauri::AppHandle) -> Option<PathBuf> {
    app_handle
        .path()
        .resource_dir()
        .ok()
        .map(|p| p.join("resources").join("skills"))
}

/// 获取项目 commands 目标目录
fn get_project_skills_dir(project_path: &str) -> PathBuf {
    PathBuf::from(project_path)
        .join(".claude")
        .join("commands")
}

/// 读取 skill 版本文件
fn read_skill_version(skill_dir: &PathBuf) -> Option<String> {
    let version_file = skill_dir.join("VERSION");
    fs::read_to_string(version_file).ok()
        .map(|s| s.trim().to_string())
}

/// 写入 skill 版本文件
fn write_skill_version(skill_dir: &PathBuf, version: &str) -> Result<(), String> {
    let version_file = skill_dir.join("VERSION");
    fs::write(version_file, version)
        .map_err(|e| format!("写入版本文件失败: {}", e))
}

/// 复制目录 (递归)
fn copy_dir_all(src: &PathBuf, dst: &PathBuf) -> Result<(), String> {
    fs::create_dir_all(dst)
        .map_err(|e| format!("创建目录失败: {}", e))?;

    for entry in fs::read_dir(src)
        .map_err(|e| format!("读取目录失败: {}", e))? {
        let entry = entry.map_err(|e| format!("读取条目失败: {}", e))?;
        let src_path = entry.path();
        let dst_path = dst.join(entry.file_name());

        if src_path.is_dir() {
            copy_dir_all(&src_path, &dst_path)?;
        } else {
            fs::copy(&src_path, &dst_path)
                .map_err(|e| format!("复制文件失败: {}", e))?;
        }
    }
    Ok(())
}

/// 检查项目 skills 状态
#[tauri::command]
pub async fn check_skills_status(project_path: String) -> Result<Vec<SkillStatus>, String> {
    let skills_dir = get_project_skills_dir(&project_path);

    let statuses: Vec<SkillStatus> = SKILL_NAMES.iter()
        .map(|name| {
            let skill_dir = skills_dir.join(name);
            let installed = skill_dir.exists() && skill_dir.join("SKILL.md").exists();
            let version = if installed {
                read_skill_version(&skill_dir)
            } else {
                None
            };
            let path = if installed {
                Some(skill_dir.to_string_lossy().to_string())
            } else {
                None
            };
            SkillStatus {
                name: name.to_string(),
                installed,
                version,
                path,
            }
        })
        .collect();

    Ok(statuses)
}

/// 安装 skills 到项目
#[tauri::command]
pub async fn install_skills(
    project_path: String,
    force: Option<bool>,
    app_handle: tauri::AppHandle,
) -> Result<SkillsInstallResult, String> {
    let force = force.unwrap_or(false);
    let target_dir = get_project_skills_dir(&project_path);

    // 获取资源目录
    let resource_dir = get_resource_skills_dir(&app_handle)
        .ok_or_else(|| "无法获取资源目录".to_string())?;

    if !resource_dir.exists() {
        // 开发模式：尝试从源代码目录读取
        let dev_skills_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("resources")
            .join("skills");
        
        if !dev_skills_dir.exists() {
            return Err("Skills 资源目录不存在".to_string());
        }
    }

    // 确定实际的源目录
    let source_dir = if resource_dir.exists() {
        resource_dir
    } else {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("resources")
            .join("skills")
    };

    // 创建目标目录
    fs::create_dir_all(&target_dir)
        .map_err(|e| format!("创建 skills 目录失败: {}", e))?;

    let mut installed_count = 0;
    let mut skipped_count = 0;
    let mut errors: Vec<String> = Vec::new();
    let mut skills: Vec<SkillStatus> = Vec::new();

    for name in SKILL_NAMES {
        let src_skill_dir = source_dir.join(name);
        let dst_skill_dir = target_dir.join(name);

        // 检查源是否存在
        if !src_skill_dir.exists() {
            errors.push(format!("源 skill 不存在: {}", name));
            skills.push(SkillStatus {
                name: name.to_string(),
                installed: false,
                version: None,
                path: None,
            });
            continue;
        }

        // 检查是否需要安装/更新
        let existing_version = read_skill_version(&dst_skill_dir);
        let needs_install = force 
            || !dst_skill_dir.exists() 
            || existing_version.as_deref() != Some(SKILLS_VERSION);

        if !needs_install {
            skipped_count += 1;
            skills.push(SkillStatus {
                name: name.to_string(),
                installed: true,
                version: existing_version,
                path: Some(dst_skill_dir.to_string_lossy().to_string()),
            });
            continue;
        }

        // 执行安装
        match copy_dir_all(&src_skill_dir, &dst_skill_dir) {
            Ok(()) => {
                // 写入版本文件
                let _ = write_skill_version(&dst_skill_dir, SKILLS_VERSION);
                installed_count += 1;
                skills.push(SkillStatus {
                    name: name.to_string(),
                    installed: true,
                    version: Some(SKILLS_VERSION.to_string()),
                    path: Some(dst_skill_dir.to_string_lossy().to_string()),
                });
            }
            Err(e) => {
                errors.push(format!("安装 {} 失败: {}", name, e));
                skills.push(SkillStatus {
                    name: name.to_string(),
                    installed: false,
                    version: None,
                    path: None,
                });
            }
        }
    }

    Ok(SkillsInstallResult {
        success: errors.is_empty(),
        installed_count,
        skipped_count,
        errors,
        skills,
    })
}

/// 卸载项目 skills
#[tauri::command]
pub async fn uninstall_skills(project_path: String) -> Result<(), String> {
    let skills_dir = get_project_skills_dir(&project_path);

    for name in SKILL_NAMES {
        let skill_dir = skills_dir.join(name);
        if skill_dir.exists() {
            fs::remove_dir_all(&skill_dir)
                .map_err(|e| format!("删除 {} 失败: {}", name, e))?;
        }
    }

    Ok(())
}

/// 获取 skills 版本
#[tauri::command]
pub async fn get_skills_version() -> Result<String, String> {
    Ok(SKILLS_VERSION.to_string())
}

/// 检查 skills 是否需要更新
#[tauri::command]
pub async fn check_skills_update_needed(project_path: String) -> Result<bool, String> {
    let skills_dir = get_project_skills_dir(&project_path);

    for name in SKILL_NAMES {
        let skill_dir = skills_dir.join(name);
        if !skill_dir.exists() {
            return Ok(true);
        }
        let version = read_skill_version(&skill_dir);
        if version.as_deref() != Some(SKILLS_VERSION) {
            return Ok(true);
        }
    }

    Ok(false)
}
