// skills.rs - Skills 管理模块
//
// 功能:
// - Skills 数据结构定义（ToolsConfig, Skill, SkillTrigger 等）
// - tools.yaml 配置读写
// - Skills 目录扫描与加载
// - 触发规则匹配

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command as ProcessCommand;

// ============================================================================
// 版本与常量
// ============================================================================

/// tools.yaml 配置版本
pub const TOOLS_CONFIG_VERSION: &str = "0.2.1";

// ============================================================================
// 枚举类型定义
// ============================================================================

/// Skill 类型
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum SkillType {
    /// 工作流类 - 流程指导
    Workflow,
    /// 领域类 - 专业知识
    Domain,
    /// 执行类 - 后端执行
    Execution,
}

impl Default for SkillType {
    fn default() -> Self {
        SkillType::Domain
    }
}

/// 触发强制级别
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum EnforcementLevel {
    /// 强制激活
    Require,
    /// 建议激活（默认）
    Suggest,
    /// 静默加载
    Silent,
}

impl Default for EnforcementLevel {
    fn default() -> Self {
        EnforcementLevel::Suggest
    }
}

/// 优先级
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum Priority {
    High,
    Medium,
    Low,
}

impl Default for Priority {
    fn default() -> Self {
        Priority::Medium
    }
}

// ============================================================================
// 触发规则
// ============================================================================

/// 触发配置
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct SkillTrigger {
    /// 关键词列表
    #[serde(default)]
    pub keywords: Vec<String>,

    /// 正则表达式模式
    #[serde(default)]
    pub patterns: Vec<String>,
}

// ============================================================================
// Skill 定义
// ============================================================================

/// Skill 定义
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Skill {
    /// 唯一标识符
    pub name: String,

    /// 语义化版本
    #[serde(default = "default_version")]
    pub version: String,

    /// Skill 类型
    #[serde(default, rename = "type")]
    pub skill_type: SkillType,

    /// 描述（用于触发匹配）
    #[serde(default)]
    pub description: String,

    /// 是否启用
    #[serde(default = "default_true")]
    pub enabled: bool,

    /// 用户 Skill 的本地路径
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source: Option<String>,

    /// 导入来源项目
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub imported_from: Option<String>,

    /// 导入时间 ISO8601
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub imported_at: Option<String>,

    /// Skill 主体内容（Markdown）
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub body: Option<String>,

    /// 触发规则
    #[serde(default)]
    pub triggers: SkillTrigger,
}

fn default_version() -> String {
    "1.0.0".to_string()
}

fn default_true() -> bool {
    true
}

// ============================================================================
// Command 定义（扩展）
// ============================================================================

/// Command 定义
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Command {
    /// 命令名（如 cc-spec-specify）
    pub name: String,

    /// 语义化版本
    #[serde(default = "default_version")]
    pub version: String,

    /// 工作流阶段（1-6）
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub stage: Option<u8>,

    /// 命令描述
    #[serde(default)]
    pub description: String,

    /// 显示图标
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub icon: Option<String>,

    /// 用户 Command 的文件路径
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source: Option<String>,

    /// 导入来源
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub imported_from: Option<String>,
}

// ============================================================================
// 设置结构
// ============================================================================

/// Skills 全局设置
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SkillsSettings {
    /// 是否自动建议匹配的 Skills
    #[serde(default = "default_true")]
    pub auto_suggest: bool,

    /// 同时激活的最大 Skills 数
    #[serde(default = "default_max_concurrent_skills")]
    pub max_concurrent_skills: u8,

    /// 启用渐进式加载
    #[serde(default = "default_true")]
    pub progressive_loading: bool,
}

fn default_max_concurrent_skills() -> u8 {
    3
}

impl Default for SkillsSettings {
    fn default() -> Self {
        Self {
            auto_suggest: true,
            max_concurrent_skills: 3,
            progressive_loading: true,
        }
    }
}

/// Commands 全局设置
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CommandsSettings {
    /// 命令前缀命名空间
    #[serde(default = "default_namespace")]
    pub namespace: String,

    /// 项目初始化时自动安装
    #[serde(default = "default_true")]
    pub auto_install: bool,
}

fn default_namespace() -> String {
    "cc-spec".to_string()
}

impl Default for CommandsSettings {
    fn default() -> Self {
        Self {
            namespace: "cc-spec".to_string(),
            auto_install: true,
        }
    }
}

/// 触发规则全局设置
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct TriggerSettings {
    /// 关键词大小写敏感
    #[serde(default)]
    pub case_sensitive: bool,

    /// 最小关键词长度
    #[serde(default = "default_min_keyword_length")]
    pub min_keyword_length: u8,

    /// 每次提示最多匹配数
    #[serde(default = "default_max_matches")]
    pub max_matches_per_prompt: u8,
}

fn default_min_keyword_length() -> u8 {
    2
}

fn default_max_matches() -> u8 {
    3
}

impl Default for TriggerSettings {
    fn default() -> Self {
        Self {
            case_sensitive: false,
            min_keyword_length: 2,
            max_matches_per_prompt: 3,
        }
    }
}

// ============================================================================
// Skills 配置容器
// ============================================================================

/// Skills 配置容器
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SkillsConfig {
    /// 全局设置
    #[serde(default)]
    pub settings: SkillsSettings,

    /// 内置 Skills（只读）
    #[serde(default)]
    pub builtin: Vec<Skill>,

    /// 用户 Skills（可编辑）
    #[serde(default)]
    pub user: Vec<Skill>,
}

impl Default for SkillsConfig {
    fn default() -> Self {
        Self {
            settings: SkillsSettings::default(),
            builtin: get_builtin_skills(),
            user: Vec::new(),
        }
    }
}

/// Commands 配置容器
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CommandsConfig {
    /// 全局设置
    #[serde(default)]
    pub settings: CommandsSettings,

    /// 内置 Commands
    #[serde(default)]
    pub builtin: Vec<Command>,

    /// 辅助 Commands
    #[serde(default)]
    pub auxiliary: Vec<Command>,

    /// 用户 Commands
    #[serde(default)]
    pub user: Vec<Command>,
}

impl Default for CommandsConfig {
    fn default() -> Self {
        Self {
            settings: CommandsSettings::default(),
            builtin: get_builtin_commands(),
            auxiliary: get_auxiliary_commands(),
            user: Vec::new(),
        }
    }
}

/// 触发规则配置容器
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct TriggerRulesConfig {
    /// 全局触发设置
    #[serde(default)]
    pub settings: TriggerSettings,

    /// 触发优先级顺序
    #[serde(default = "default_priority_order")]
    pub priority_order: Vec<String>,
}

fn default_priority_order() -> Vec<String> {
    vec![
        "workflow".to_string(),
        "execution".to_string(),
        "domain".to_string(),
    ]
}

impl Default for TriggerRulesConfig {
    fn default() -> Self {
        Self {
            settings: TriggerSettings::default(),
            priority_order: default_priority_order(),
        }
    }
}

// ============================================================================
// 项目状态
// ============================================================================

/// 项目安装状态
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProjectState {
    /// 初始化时间
    pub initialized_at: String,

    /// 安装的 Commands 版本
    #[serde(default)]
    pub commands_version: String,

    /// 已安装的 Skills 名称列表
    #[serde(default)]
    pub skills_installed: Vec<String>,

    /// 项目自定义覆盖的配置
    #[serde(default)]
    pub custom_overrides: Vec<String>,
}

// ============================================================================
// 顶层配置结构
// ============================================================================

/// tools.yaml 顶层配置
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ToolsConfig {
    /// 配置版本
    #[serde(default = "default_tools_version")]
    pub version: String,

    /// 最后更新时间
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub updated_at: Option<String>,

    /// Skills 配置
    #[serde(default)]
    pub skills: SkillsConfig,

    /// Commands 配置
    #[serde(default)]
    pub commands: CommandsConfig,

    /// 触发规则配置
    #[serde(default)]
    pub trigger_rules: TriggerRulesConfig,

    /// 项目安装状态
    #[serde(default)]
    pub projects: HashMap<String, ProjectState>,
}

fn default_tools_version() -> String {
    TOOLS_CONFIG_VERSION.to_string()
}

impl Default for ToolsConfig {
    fn default() -> Self {
        Self {
            version: TOOLS_CONFIG_VERSION.to_string(),
            updated_at: None,
            skills: SkillsConfig::default(),
            commands: CommandsConfig::default(),
            trigger_rules: TriggerRulesConfig::default(),
            projects: HashMap::new(),
        }
    }
}

// ============================================================================
// 内置 Skills 定义
// ============================================================================

/// 获取内置 Skills
fn get_builtin_skills() -> Vec<Skill> {
    vec![
        Skill {
            name: "cc-spec-workflow".to_string(),
            version: "1.0.0".to_string(),
            skill_type: SkillType::Workflow,
            description: "cc-spec 7步工作流指导。在用户讨论需求变更、功能开发、代码重构时自动激活。".to_string(),
            enabled: true,
            source: None,
            imported_from: None,
            imported_at: None,
            body: Some(r#"# cc-spec 7步工作流

## 概述
cc-spec 是一个规范驱动的 AI 辅助开发工作流，包含 7 个标准步骤。

## 工作流步骤

### 1. Specify (规格化)
- 创建变更提案 `proposal.md`
- 定义需求范围和目标
- 使用 `/cc-spec-specify` 命令

### 2. Clarify (澄清)
- 与用户确认需求细节
- 解决歧义和疑问
- 使用 `/cc-spec-clarify` 命令

### 3. Plan (计划)
- 生成执行计划 `tasks.yaml`
- 分解为 Wave/Task 结构
- 使用 `/cc-spec-plan` 命令

### 4. Apply (执行)
- 使用 SubAgent 并发执行任务
- 最多 10 个并发 SubAgent
- 使用 `/cc-spec-apply` 命令

### 5. Checklist (验收)
- 执行验收检查清单
- 评分 ≥80 分通过
- 使用 `/cc-spec-checklist` 命令

### 6. Accept (接受)
- 用户最终确认
- 标记变更完成

### 7. Archive (归档)
- 归档已完成变更
- 更新项目状态
- 使用 `/cc-spec-archive` 命令

## Delta 格式
- `ADDED:` 新增文件
- `MODIFIED:` 修改文件
- `REMOVED:` 删除文件
- `RENAMED: old → new` 重命名文件
"#.to_string()),
            triggers: SkillTrigger {
                keywords: vec![
                    "cc-spec".to_string(),
                    "变更流程".to_string(),
                    "需求分析".to_string(),
                    "proposal".to_string(),
                    "clarify".to_string(),
                ],
                patterns: vec![
                    "(specify|plan|apply|checklist|archive)".to_string(),
                    "变更.*流程".to_string(),
                ],
            },
        },
        Skill {
            name: "subagent-coordinator".to_string(),
            version: "1.0.0".to_string(),
            skill_type: SkillType::Execution,
            description: "SubAgent 并发协调器。在执行多任务 Wave/Task 时自动激活，协调最多10个并发 SubAgent。".to_string(),
            enabled: true,
            source: None,
            imported_from: None,
            imported_at: None,
            body: Some(r#"# SubAgent 并发协调器

## 概述
协调多个 SubAgent 并发执行任务，支持 Wave/Task 结构。

## Task ID 格式
- `W<wave>-T<task>` 格式
- 例如: W1-T1, W1-T2, W2-T1

## Wave 执行规则
1. 同一 Wave 内的 Task 可并发执行
2. 不同 Wave 按顺序执行
3. 前一个 Wave 全部完成后才执行下一个

## 并发限制
- Claude Code: 最多 10 个并发 SubAgent
- Codex: 最多 5 个并发

## 使用示例
```yaml
waves:
  - wave: 1
    tasks:
      - id: W1-T1
        description: "创建数据模型"
      - id: W1-T2
        description: "创建 API 路由"
  - wave: 2
    tasks:
      - id: W2-T1
        description: "编写单元测试"
```
"#.to_string()),
            triggers: SkillTrigger {
                keywords: vec![
                    "subagent".to_string(),
                    "并发执行".to_string(),
                    "wave".to_string(),
                    "task".to_string(),
                ],
                patterns: vec![
                    r"W\d+-T\d+".to_string(),
                    "(parallel|concurrent).*task".to_string(),
                ],
            },
        },
        Skill {
            name: "delta-tracker".to_string(),
            version: "1.0.0".to_string(),
            skill_type: SkillType::Domain,
            description: "Delta 变更追踪专家。在讨论代码变更、文件修改时激活，确保 Delta 格式规范。".to_string(),
            enabled: true,
            source: None,
            imported_from: None,
            imported_at: None,
            body: Some(r#"# Delta 变更追踪

## 概述
追踪和记录代码变更，使用标准化的 Delta 格式。

## Delta 格式规范

### 文件操作类型
| 前缀 | 含义 | 示例 |
|------|------|------|
| `ADDED:` | 新增文件 | `ADDED: src/new_file.py` |
| `MODIFIED:` | 修改文件 | `MODIFIED: src/existing.py` |
| `REMOVED:` | 删除文件 | `REMOVED: src/old_file.py` |
| `RENAMED:` | 重命名文件 | `RENAMED: old.py → new.py` |

### 示例
```
ADDED: src/models/user.py
ADDED: src/api/users.py
MODIFIED: src/main.py
MODIFIED: pyproject.toml
REMOVED: src/deprecated.py
RENAMED: src/utils.py → src/helpers.py
```

## 变更记录位置
- `proposal.md` 中的 Delta 区域
- Git commit 信息中引用
- 检查清单验证

## 最佳实践
1. 每个变更都要记录
2. 保持格式一致
3. 文件路径使用相对路径
4. 重命名使用 `→` 分隔
"#.to_string()),
            triggers: SkillTrigger {
                keywords: vec![
                    "delta".to_string(),
                    "变更记录".to_string(),
                    "ADDED".to_string(),
                    "MODIFIED".to_string(),
                    "REMOVED".to_string(),
                ],
                patterns: vec![
                    "(ADDED|MODIFIED|REMOVED|RENAMED):".to_string(),
                ],
            },
        },
    ]
}

// ============================================================================
// 内置 Commands 定义
// ============================================================================

/// 获取内置 Commands（工作流）
fn get_builtin_commands() -> Vec<Command> {
    vec![
        Command {
            name: "cc-spec-specify".to_string(),
            version: "1.0.0".to_string(),
            stage: Some(1),
            description: "specify 阶段，与用户确认需求，输出 proposal.md".to_string(),
            icon: Some("📝".to_string()),
            source: None,
            imported_from: None,
        },
        Command {
            name: "cc-spec-clarify".to_string(),
            version: "1.0.0".to_string(),
            stage: Some(2),
            description: "clarify 阶段，CC↔CX 讨论或用户审查".to_string(),
            icon: Some("🔍".to_string()),
            source: None,
            imported_from: None,
        },
        Command {
            name: "cc-spec-plan".to_string(),
            version: "1.0.0".to_string(),
            stage: Some(3),
            description: "plan 阶段，用户确认后生成 tasks.yaml".to_string(),
            icon: Some("📋".to_string()),
            source: None,
            imported_from: None,
        },
        Command {
            name: "cc-spec-apply".to_string(),
            version: "1.0.0".to_string(),
            stage: Some(4),
            description: "apply 阶段，使用 SubAgent 执行任务".to_string(),
            icon: Some("🚀".to_string()),
            source: None,
            imported_from: None,
        },
        Command {
            name: "cc-spec-accept".to_string(),
            version: "1.0.0".to_string(),
            stage: Some(5),
            description: "accept 阶段，端到端验收".to_string(),
            icon: Some("✅".to_string()),
            source: None,
            imported_from: None,
        },
        Command {
            name: "cc-spec-archive".to_string(),
            version: "1.0.0".to_string(),
            stage: Some(6),
            description: "archive 阶段，归档变更".to_string(),
            icon: Some("📦".to_string()),
            source: None,
            imported_from: None,
        },
    ]
}

/// 获取辅助 Commands
fn get_auxiliary_commands() -> Vec<Command> {
    vec![
        Command {
            name: "cc-spec:init".to_string(),
            version: "1.0.0".to_string(),
            stage: None,
            description: "初始化/更新知识库（RAG）".to_string(),
            icon: Some("🔧".to_string()),
            source: None,
            imported_from: None,
        },
        Command {
            name: "cc-spec:list".to_string(),
            version: "1.0.0".to_string(),
            stage: None,
            description: "列出变更、任务、规格或归档".to_string(),
            icon: Some("📋".to_string()),
            source: None,
            imported_from: None,
        },
        Command {
            name: "cc-spec:goto".to_string(),
            version: "1.0.0".to_string(),
            stage: None,
            description: "跳转到指定变更或任务".to_string(),
            icon: Some("🔗".to_string()),
            source: None,
            imported_from: None,
        },
        Command {
            name: "cc-spec:quick-delta".to_string(),
            version: "1.0.0".to_string(),
            stage: None,
            description: "快速记录简单变更".to_string(),
            icon: Some("⚡".to_string()),
            source: None,
            imported_from: None,
        },
        Command {
            name: "cc-spec:update".to_string(),
            version: "1.0.0".to_string(),
            stage: None,
            description: "更新配置与模板".to_string(),
            icon: Some("🔄".to_string()),
            source: None,
            imported_from: None,
        },
    ]
}

// ============================================================================
// 配置文件路径
// ============================================================================

/// 获取用户主目录
fn home_dir() -> PathBuf {
    std::env::var_os("USERPROFILE")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(PathBuf::from))
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")))
}

/// 获取 tools.yaml 配置路径
pub fn tools_config_path() -> PathBuf {
    home_dir().join(".cc-spec").join("tools.yaml")
}

/// 获取用户 Skills 目录路径
pub fn user_skills_dir() -> PathBuf {
    home_dir().join(".cc-spec").join("skills")
}

/// 获取旧版配置路径（用于迁移）
fn legacy_tools_json_path() -> PathBuf {
    home_dir().join(".cc-spec").join("tools.json")
}

// ============================================================================
// 配置迁移
// ============================================================================

/// 迁移结果
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct MigrationResult {
    pub migrated: bool,
    pub from_version: Option<String>,
    pub to_version: String,
    pub message: String,
}

/// 检测并执行配置迁移
///
/// 迁移场景：
/// 1. 从 tools.json (JSON 格式) 迁移到 tools.yaml (YAML 格式)
/// 2. 未来版本升级迁移
fn migrate_config_if_needed() -> Result<Option<MigrationResult>, String> {
    let yaml_path = tools_config_path();
    let json_path = legacy_tools_json_path();

    // 如果 YAML 配置已存在，不需要迁移
    if yaml_path.exists() {
        return Ok(None);
    }

    // 检查是否有旧的 JSON 配置需要迁移
    if json_path.exists() {
        return migrate_from_json(&json_path, &yaml_path);
    }

    // 没有需要迁移的配置
    Ok(None)
}

/// 从 JSON 格式迁移到 YAML 格式
fn migrate_from_json(json_path: &PathBuf, yaml_path: &PathBuf) -> Result<Option<MigrationResult>, String> {
    // 读取旧的 JSON 配置
    let json_content = fs::read_to_string(json_path)
        .map_err(|e| format!("读取旧配置失败: {}", e))?;

    // 尝试解析为 ToolsConfig
    // 注意：JSON 和 YAML 的 serde 序列化是兼容的
    let old_config: Result<ToolsConfig, _> = serde_json::from_str(&json_content);

    let config = match old_config {
        Ok(mut config) => {
            // 更新版本号
            config.version = TOOLS_CONFIG_VERSION.to_string();
            config.updated_at = Some(chrono::Utc::now().to_rfc3339());
            config
        }
        Err(_) => {
            // 无法解析旧配置，使用默认配置
            ToolsConfig::default()
        }
    };

    // 确保目录存在
    if let Some(parent) = yaml_path.parent() {
        fs::create_dir_all(parent)
            .map_err(|e| format!("创建配置目录失败: {}", e))?;
    }

    // 保存为 YAML
    let yaml_content = serde_yaml::to_string(&config)
        .map_err(|e| format!("序列化配置失败: {}", e))?;

    fs::write(yaml_path, yaml_content)
        .map_err(|e| format!("写入新配置失败: {}", e))?;

    // 备份旧配置（添加 .bak 后缀）
    let backup_path = json_path.with_extension("json.bak");
    let _ = fs::rename(json_path, &backup_path);

    Ok(Some(MigrationResult {
        migrated: true,
        from_version: Some("json".to_string()),
        to_version: TOOLS_CONFIG_VERSION.to_string(),
        message: format!(
            "配置已从 JSON 迁移到 YAML 格式，旧配置备份为 {}",
            backup_path.display()
        ),
    }))
}

/// 检测配置版本并升级（未来扩展用）
fn upgrade_config_version(config: &mut ToolsConfig) -> bool {
    let current_version = &config.version;

    // 版本比较逻辑（简化版）
    if current_version == TOOLS_CONFIG_VERSION {
        return false; // 无需升级
    }

    // 未来版本升级逻辑占位
    // match current_version.as_str() {
    //     "0.1.0" => upgrade_from_0_1_0(config),
    //     "0.2.0" => upgrade_from_0_2_0(config),
    //     _ => {}
    // }

    config.version = TOOLS_CONFIG_VERSION.to_string();
    true
}

// ============================================================================
// Skill 目录扫描
// ============================================================================

/// 扫描结果
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SkillScanResult {
    /// 扫描到的 Skills
    pub skills: Vec<Skill>,
    /// 扫描错误（目录名 → 错误信息）
    pub errors: Vec<SkillScanError>,
    /// 扫描的目录路径
    pub scanned_path: String,
}

/// 扫描错误
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SkillScanError {
    pub dir_name: String,
    pub error: String,
}

/// SKILL.md Frontmatter 解析结果
#[derive(Clone, Debug, Serialize, Deserialize)]
struct SkillFrontmatter {
    name: Option<String>,
    version: Option<String>,
    #[serde(rename = "type")]
    skill_type: Option<String>,
    description: Option<String>,
    triggers: Option<SkillTrigger>,
    dependencies: Option<Vec<String>>,
}

/// 扫描用户 Skills 目录
///
/// 扫描 ~/.cc-spec/skills/ 目录下的所有 Skill
/// 每个 Skill 是一个目录，包含 SKILL.md 文件
pub fn scan_user_skills_dir() -> Result<SkillScanResult, String> {
    let skills_dir = user_skills_dir();

    if !skills_dir.exists() {
        // 目录不存在，返回空结果
        return Ok(SkillScanResult {
            skills: Vec::new(),
            errors: Vec::new(),
            scanned_path: skills_dir.to_string_lossy().to_string(),
        });
    }

    let mut skills = Vec::new();
    let mut errors = Vec::new();

    // 读取目录
    let entries = fs::read_dir(&skills_dir)
        .map_err(|e| format!("读取 Skills 目录失败: {}", e))?;

    for entry in entries {
        let entry = match entry {
            Ok(e) => e,
            Err(e) => {
                errors.push(SkillScanError {
                    dir_name: "unknown".to_string(),
                    error: format!("读取目录条目失败: {}", e),
                });
                continue;
            }
        };

        let path = entry.path();

        // 只处理目录
        if !path.is_dir() {
            continue;
        }

        let dir_name = path.file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("unknown")
            .to_string();

        // 检查 SKILL.md 是否存在
        let skill_md_path = path.join("SKILL.md");
        if !skill_md_path.exists() {
            errors.push(SkillScanError {
                dir_name: dir_name.clone(),
                error: "缺少 SKILL.md 文件".to_string(),
            });
            continue;
        }

        // 解析 SKILL.md
        match parse_skill_md(&skill_md_path, &dir_name, &path) {
            Ok(skill) => skills.push(skill),
            Err(e) => {
                errors.push(SkillScanError {
                    dir_name,
                    error: e,
                });
            }
        }
    }

    Ok(SkillScanResult {
        skills,
        errors,
        scanned_path: skills_dir.to_string_lossy().to_string(),
    })
}

/// 解析 SKILL.md 文件
fn parse_skill_md(path: &PathBuf, dir_name: &str, skill_dir: &PathBuf) -> Result<Skill, String> {
    let content = fs::read_to_string(path)
        .map_err(|e| format!("读取 SKILL.md 失败: {}", e))?;

    // 提取 frontmatter (YAML between --- lines)
    let frontmatter = extract_frontmatter(&content)?;

    // 解析 frontmatter
    let fm: SkillFrontmatter = serde_yaml::from_str(&frontmatter)
        .map_err(|e| format!("解析 frontmatter 失败: {}", e))?;

    // 构建 Skill
    let skill_type = match fm.skill_type.as_deref() {
        Some("workflow") => SkillType::Workflow,
        Some("execution") => SkillType::Execution,
        _ => SkillType::Domain,
    };

    Ok(Skill {
        name: fm.name.unwrap_or_else(|| dir_name.to_string()),
        version: fm.version.unwrap_or_else(|| "1.0.0".to_string()),
        skill_type,
        description: fm.description.unwrap_or_default(),
        enabled: true,
        source: Some(skill_dir.to_string_lossy().to_string()),
        imported_from: None,
        imported_at: None,
        body: None,
        triggers: fm.triggers.unwrap_or_default(),
    })
}

/// 从 Markdown 内容中提取 YAML frontmatter
fn extract_frontmatter(content: &str) -> Result<String, String> {
    let lines: Vec<&str> = content.lines().collect();

    // 检查是否以 --- 开头
    if lines.is_empty() || lines[0].trim() != "---" {
        return Err("SKILL.md 缺少 frontmatter（应以 --- 开头）".to_string());
    }

    // 查找结束的 ---
    let mut end_index = None;
    for (i, line) in lines.iter().enumerate().skip(1) {
        if line.trim() == "---" {
            end_index = Some(i);
            break;
        }
    }

    let end = end_index.ok_or_else(|| "frontmatter 未正确闭合（缺少结束的 ---）".to_string())?;

    // 提取 frontmatter 内容
    let frontmatter = lines[1..end].join("\n");

    Ok(frontmatter)
}

/// 扫描项目 Skills 目录
///
/// 扫描项目内的 .claude/skills/ 或 .codex/skills/ 目录
pub fn scan_project_skills_dir(project_path: &str) -> Result<SkillScanResult, String> {
    let project_dir = PathBuf::from(project_path);

    // 优先检查 .claude/skills/
    let claude_skills_dir = project_dir.join(".claude").join("skills");
    if claude_skills_dir.exists() {
        return scan_skills_in_dir(&claude_skills_dir);
    }

    // 其次检查 .codex/skills/
    let codex_skills_dir = project_dir.join(".codex").join("skills");
    if codex_skills_dir.exists() {
        return scan_skills_in_dir(&codex_skills_dir);
    }

    // 都不存在，返回空结果
    Ok(SkillScanResult {
        skills: Vec::new(),
        errors: Vec::new(),
        scanned_path: claude_skills_dir.to_string_lossy().to_string(),
    })
}

/// 扫描指定目录中的 Skills
fn scan_skills_in_dir(skills_dir: &PathBuf) -> Result<SkillScanResult, String> {
    let mut skills = Vec::new();
    let mut errors = Vec::new();

    let entries = fs::read_dir(skills_dir)
        .map_err(|e| format!("读取 Skills 目录失败: {}", e))?;

    for entry in entries {
        let entry = match entry {
            Ok(e) => e,
            Err(e) => {
                errors.push(SkillScanError {
                    dir_name: "unknown".to_string(),
                    error: format!("读取目录条目失败: {}", e),
                });
                continue;
            }
        };

        let path = entry.path();

        if !path.is_dir() {
            continue;
        }

        let dir_name = path.file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("unknown")
            .to_string();

        let skill_md_path = path.join("SKILL.md");
        if !skill_md_path.exists() {
            errors.push(SkillScanError {
                dir_name: dir_name.clone(),
                error: "缺少 SKILL.md 文件".to_string(),
            });
            continue;
        }

        match parse_skill_md(&skill_md_path, &dir_name, &path) {
            Ok(skill) => skills.push(skill),
            Err(e) => {
                errors.push(SkillScanError {
                    dir_name,
                    error: e,
                });
            }
        }
    }

    Ok(SkillScanResult {
        skills,
        errors,
        scanned_path: skills_dir.to_string_lossy().to_string(),
    })
}

// ============================================================================
// 触发匹配算法
// ============================================================================

/// 匹配结果
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SkillMatch {
    /// 匹配的 Skill
    pub skill: Skill,
    /// 匹配分数（越高越好）
    pub score: u32,
    /// 匹配的关键词
    pub matched_keywords: Vec<String>,
    /// 匹配的模式
    pub matched_patterns: Vec<String>,
}

/// 匹配结果集合
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct MatchResult {
    /// 匹配到的 Skills（按分数降序排列）
    pub matches: Vec<SkillMatch>,
    /// 原始输入
    pub input: String,
    /// 是否大小写敏感
    pub case_sensitive: bool,
}

/// 匹配 Skills
///
/// 根据用户输入，匹配所有启用的 Skills
/// 返回按分数排序的匹配结果
pub fn match_skills(input: &str, skills: &[Skill], settings: &TriggerSettings) -> MatchResult {
    let mut matches = Vec::new();

    let input_lower = if settings.case_sensitive {
        input.to_string()
    } else {
        input.to_lowercase()
    };

    for skill in skills {
        // 跳过未启用的 Skills
        if !skill.enabled {
            continue;
        }

        let mut score = 0u32;
        let mut matched_keywords = Vec::new();
        let mut matched_patterns = Vec::new();

        // 关键词匹配（每个关键词 10 分）
        for keyword in &skill.triggers.keywords {
            // 检查关键词长度
            if keyword.len() < settings.min_keyword_length as usize {
                continue;
            }

            let keyword_match = if settings.case_sensitive {
                input.contains(keyword)
            } else {
                input_lower.contains(&keyword.to_lowercase())
            };

            if keyword_match {
                score += 10;
                matched_keywords.push(keyword.clone());
            }
        }

        // 正则模式匹配（每个模式 20 分）
        for pattern in &skill.triggers.patterns {
            let regex_flags = if settings.case_sensitive {
                ""
            } else {
                "(?i)"
            };

            let full_pattern = format!("{}{}", regex_flags, pattern);

            match regex::Regex::new(&full_pattern) {
                Ok(re) => {
                    if re.is_match(input) {
                        score += 20;
                        matched_patterns.push(pattern.clone());
                    }
                }
                Err(_) => {
                    // 无效的正则表达式，跳过
                    continue;
                }
            }
        }

        // 只有匹配到才加入结果
        if score > 0 {
            matches.push(SkillMatch {
                skill: skill.clone(),
                score,
                matched_keywords,
                matched_patterns,
            });
        }
    }

    // 按分数降序排序，分数相同按类型优先级排序
    matches.sort_by(|a, b| {
        // 先按分数降序
        let score_cmp = b.score.cmp(&a.score);
        if score_cmp != std::cmp::Ordering::Equal {
            return score_cmp;
        }

        // 分数相同，按类型优先级：workflow > execution > domain
        let type_priority = |t: &SkillType| -> u8 {
            match t {
                SkillType::Workflow => 0,
                SkillType::Execution => 1,
                SkillType::Domain => 2,
            }
        };

        type_priority(&a.skill.skill_type).cmp(&type_priority(&b.skill.skill_type))
    });

    // 限制返回数量
    let max_matches = settings.max_matches_per_prompt as usize;
    if matches.len() > max_matches {
        matches.truncate(max_matches);
    }

    MatchResult {
        matches,
        input: input.to_string(),
        case_sensitive: settings.case_sensitive,
    }
}

/// 从配置中加载所有 Skills 并匹配
pub fn match_skills_from_config(input: &str) -> Result<MatchResult, String> {
    let config = load_tools_config()?;

    // 合并 builtin 和 user skills
    let mut all_skills = config.skills.builtin.clone();
    all_skills.extend(config.skills.user.clone());

    let settings = &config.trigger_rules.settings;
    Ok(match_skills(input, &all_skills, settings))
}

// ============================================================================
// 渐进式加载（Progressive Disclosure）
// ============================================================================

/// L1 元数据 - 轻量级 Skill 信息（始终在 context）
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SkillMetadata {
    pub name: String,
    pub description: String,
    pub skill_type: SkillType,
    pub enabled: bool,
    /// 是否有 L2 主体内容可加载
    pub has_body: bool,
    /// 是否有 L3 资源可加载
    pub has_resources: bool,
}

/// L2 主体内容 - SKILL.md body（触发时加载）
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SkillBody {
    pub name: String,
    /// Markdown 主体内容（去除 frontmatter）
    pub content: String,
    /// 字数统计
    pub word_count: usize,
}

/// L3 资源信息 - references/scripts/assets（按需加载）
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SkillResource {
    pub name: String,
    pub path: String,
    pub resource_type: ResourceType,
    /// 文件大小（字节）
    pub size: u64,
}

/// 资源类型
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ResourceType {
    Reference,
    Script,
    Asset,
}

/// L3 资源列表
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SkillResources {
    pub skill_name: String,
    pub references: Vec<SkillResource>,
    pub scripts: Vec<SkillResource>,
    pub assets: Vec<SkillResource>,
}

/// 加载的资源内容
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct LoadedResource {
    pub path: String,
    pub content: String,
    pub resource_type: ResourceType,
}

/// 获取所有 Skills 的 L1 元数据
pub fn get_all_skill_metadata() -> Result<Vec<SkillMetadata>, String> {
    let config = load_tools_config()?;
    let mut metadata = Vec::new();

    // 处理内置 Skills
    for skill in &config.skills.builtin {
        metadata.push(SkillMetadata {
            name: skill.name.clone(),
            description: skill.description.clone(),
            skill_type: skill.skill_type.clone(),
            enabled: skill.enabled,
            has_body: false, // 内置 Skills 没有外部文件
            has_resources: false,
        });
    }

    // 处理用户 Skills
    for skill in &config.skills.user {
        let (has_body, has_resources) = if let Some(source) = &skill.source {
            let skill_dir = PathBuf::from(source);
            let skill_md = skill_dir.join("SKILL.md");
            let refs_dir = skill_dir.join("references");
            let scripts_dir = skill_dir.join("scripts");
            let assets_dir = skill_dir.join("assets");

            let has_body = skill_md.exists();
            let has_resources = refs_dir.exists() || scripts_dir.exists() || assets_dir.exists();

            (has_body, has_resources)
        } else {
            (false, false)
        };

        metadata.push(SkillMetadata {
            name: skill.name.clone(),
            description: skill.description.clone(),
            skill_type: skill.skill_type.clone(),
            enabled: skill.enabled,
            has_body,
            has_resources,
        });
    }

    Ok(metadata)
}

/// 加载 L2 主体内容
pub fn load_skill_body(skill_name: &str) -> Result<SkillBody, String> {
    let config = load_tools_config()?;

    // 先在用户 Skill 中查找，再在内置 Skill 中查找
    let skill = config.skills.user.iter()
        .find(|s| s.name == skill_name)
        .or_else(|| config.skills.builtin.iter().find(|s| s.name == skill_name))
        .ok_or_else(|| format!("Skill '{}' 不存在", skill_name))?;

    // 优先使用 skill.body（内置 Skills 和已编辑的 Skills）
    if let Some(body_content) = &skill.body {
        let word_count = body_content.split_whitespace().count();
        return Ok(SkillBody {
            name: skill_name.to_string(),
            content: body_content.clone(),
            word_count,
        });
    }

    // 如果配置中没有 body，尝试从内置模板获取默认内容
    // （这解决了从 YAML 加载后内置 Skill 丢失 body 的问题）
    let builtin_skills = get_builtin_skills();
    if let Some(builtin_skill) = builtin_skills.iter().find(|s| s.name == skill_name) {
        if let Some(default_body) = &builtin_skill.body {
            let word_count = default_body.split_whitespace().count();
            return Ok(SkillBody {
                name: skill_name.to_string(),
                content: default_body.clone(),
                word_count,
            });
        }
    }

    // 如果没有 body，尝试从文件加载
    let source = skill.source.as_ref()
        .ok_or_else(|| format!("Skill '{}' 没有内容可加载", skill_name))?;

    let skill_md_path = PathBuf::from(source).join("SKILL.md");

    if !skill_md_path.exists() {
        return Err(format!("SKILL.md 不存在: {}", skill_md_path.display()));
    }

    let content = fs::read_to_string(&skill_md_path)
        .map_err(|e| format!("读取 SKILL.md 失败: {}", e))?;

    // 提取 body（去除 frontmatter）
    let body = extract_body(&content)?;
    let word_count = body.split_whitespace().count();

    Ok(SkillBody {
        name: skill_name.to_string(),
        content: body,
        word_count,
    })
}

/// 从 Markdown 内容中提取 body（去除 frontmatter）
fn extract_body(content: &str) -> Result<String, String> {
    let lines: Vec<&str> = content.lines().collect();

    // 检查是否以 --- 开头
    if lines.is_empty() || lines[0].trim() != "---" {
        // 没有 frontmatter，整个内容都是 body
        return Ok(content.to_string());
    }

    // 查找结束的 ---
    let mut end_index = None;
    for (i, line) in lines.iter().enumerate().skip(1) {
        if line.trim() == "---" {
            end_index = Some(i);
            break;
        }
    }

    let end = end_index.ok_or_else(|| "frontmatter 未正确闭合".to_string())?;

    // 提取 body（frontmatter 之后的内容）
    let body = lines[(end + 1)..].join("\n");
    Ok(body.trim().to_string())
}

/// 获取 L3 资源列表
pub fn get_skill_resources(skill_name: &str) -> Result<SkillResources, String> {
    let config = load_tools_config()?;

    // 先在用户 Skill 中查找，再在内置 Skill 中查找
    let skill = config.skills.user.iter()
        .find(|s| s.name == skill_name)
        .or_else(|| config.skills.builtin.iter().find(|s| s.name == skill_name))
        .ok_or_else(|| format!("Skill '{}' 不存在", skill_name))?;

    let source = skill.source.as_ref()
        .ok_or_else(|| format!("Skill '{}' 没有源路径", skill_name))?;

    let skill_dir = PathBuf::from(source);

    let references = scan_resource_dir(&skill_dir.join("references"), ResourceType::Reference);
    let scripts = scan_resource_dir(&skill_dir.join("scripts"), ResourceType::Script);
    let assets = scan_resource_dir(&skill_dir.join("assets"), ResourceType::Asset);

    Ok(SkillResources {
        skill_name: skill_name.to_string(),
        references,
        scripts,
        assets,
    })
}

/// 扫描资源目录
fn scan_resource_dir(dir: &PathBuf, resource_type: ResourceType) -> Vec<SkillResource> {
    let mut resources = Vec::new();

    if !dir.exists() {
        return resources;
    }

    if let Ok(entries) = fs::read_dir(dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_file() {
                let size = fs::metadata(&path).map(|m| m.len()).unwrap_or(0);
                resources.push(SkillResource {
                    name: path.file_name()
                        .and_then(|n| n.to_str())
                        .unwrap_or("unknown")
                        .to_string(),
                    path: path.to_string_lossy().to_string(),
                    resource_type: resource_type.clone(),
                    size,
                });
            }
        }
    }

    resources
}

/// 加载 L3 资源内容
pub fn load_skill_resource(resource_path: &str) -> Result<LoadedResource, String> {
    let path = PathBuf::from(resource_path);

    if !path.exists() {
        return Err(format!("资源不存在: {}", resource_path));
    }

    let content = fs::read_to_string(&path)
        .map_err(|e| format!("读取资源失败: {}", e))?;

    // 根据父目录名判断资源类型
    let resource_type = path.parent()
        .and_then(|p| p.file_name())
        .and_then(|n| n.to_str())
        .map(|name| match name {
            "references" => ResourceType::Reference,
            "scripts" => ResourceType::Script,
            "assets" => ResourceType::Asset,
            _ => ResourceType::Reference,
        })
        .unwrap_or(ResourceType::Reference);

    Ok(LoadedResource {
        path: resource_path.to_string(),
        content,
        resource_type,
    })
}

// ============================================================================
// 配置读写
// ============================================================================

/// 加载 tools.yaml 配置
///
/// 加载流程：
/// 1. 检查并执行配置迁移（JSON → YAML）
/// 2. 加载 YAML 配置文件
/// 3. 检查并执行版本升级
/// 4. 返回配置
pub fn load_tools_config() -> Result<ToolsConfig, String> {
    // 1. 检查并执行配置迁移
    let _migration = migrate_config_if_needed()?;

    let path = tools_config_path();

    if !path.exists() {
        // 配置文件不存在，返回默认配置
        return Ok(ToolsConfig::default());
    }

    let content = fs::read_to_string(&path)
        .map_err(|e| format!("读取配置文件失败: {}", e))?;

    let mut config: ToolsConfig = serde_yaml::from_str(&content)
        .map_err(|e| format!("解析配置文件失败: {}", e))?;

    // 3. 检查并执行版本升级
    if upgrade_config_version(&mut config) {
        // 版本已升级，保存配置
        let _ = save_tools_config(&config);
    }

    Ok(config)
}

/// 保存 tools.yaml 配置
pub fn save_tools_config(config: &ToolsConfig) -> Result<(), String> {
    let path = tools_config_path();

    // 确保目录存在
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|e| format!("创建配置目录失败: {}", e))?;
    }

    // 更新时间戳
    let mut config = config.clone();
    config.updated_at = Some(chrono::Utc::now().to_rfc3339());

    let content = serde_yaml::to_string(&config)
        .map_err(|e| format!("序列化配置失败: {}", e))?;

    fs::write(&path, content)
        .map_err(|e| format!("写入配置文件失败: {}", e))?;

    Ok(())
}

fn strip_windows_extended_prefix(path: &Path) -> String {
    let s = path.to_string_lossy().to_string();
    #[cfg(windows)]
    {
        if s.starts_with(r"\\?\") {
            return s[4..].to_string();
        }
    }
    s
}

fn open_in_vscode(path: &Path, line: Option<u32>, col: Option<u32>) -> Result<(), String> {
    let mut cmd = ProcessCommand::new("code");
    if let Some(line) = line {
        let col = col.unwrap_or(1).max(1);
        let target = format!("{}:{}:{}", strip_windows_extended_prefix(path), line.max(1), col);
        cmd.args(["-g", &target]);
    } else {
        cmd.arg(strip_windows_extended_prefix(path));
    }

    if cmd.spawn().is_ok() {
        return Ok(());
    }

    #[cfg(windows)]
    {
        ProcessCommand::new("cmd")
            .args(["/C", "start", "", &strip_windows_extended_prefix(path)])
            .spawn()
            .map_err(|e| format!("Failed to open file: {}", e))?;
        return Ok(());
    }

    #[cfg(target_os = "macos")]
    {
        ProcessCommand::new("open")
            .arg(path)
            .spawn()
            .map_err(|e| format!("Failed to open file: {}", e))?;
        return Ok(());
    }

    #[cfg(all(unix, not(target_os = "macos")))]
    {
        ProcessCommand::new("xdg-open")
            .arg(path)
            .spawn()
            .map_err(|e| format!("Failed to open file: {}", e))?;
        return Ok(());
    }
}

fn ensure_tools_yaml_exists() -> Result<PathBuf, String> {
    let path = tools_config_path();
    if path.exists() {
        return Ok(path);
    }
    let config = ToolsConfig::default();
    save_tools_config(&config)?;
    Ok(path)
}

fn find_tools_yaml_line_for_skill(path: &Path, skill_name: &str) -> Option<u32> {
    let content = fs::read_to_string(path).ok()?;
    let needle = format!("name: {}", skill_name);
    let mut in_skills_section = false;

    for (idx, line) in content.lines().enumerate() {
        let trimmed = line.trim();
        if trimmed == "skills:" {
            in_skills_section = true;
            continue;
        }
        if in_skills_section && trimmed.ends_with(':') && !trimmed.starts_with('-') && !trimmed.starts_with("skills:") {
            // Leaving skills section when another top-level key starts.
            if !line.starts_with(' ') && !line.starts_with('\t') {
                in_skills_section = false;
            }
        }
        if in_skills_section && trimmed.contains(&needle) {
            return Some((idx + 1) as u32);
        }
    }

    // fallback: search whole file
    for (idx, line) in content.lines().enumerate() {
        if line.trim().contains(&needle) {
            return Some((idx + 1) as u32);
        }
    }
    None
}

// ============================================================================
// Tauri Commands
// ============================================================================

/// 检查并执行配置迁移
#[tauri::command]
pub async fn check_config_migration() -> Result<Option<MigrationResult>, String> {
    migrate_config_if_needed()
}

/// 扫描用户 Skills 目录
#[tauri::command]
pub async fn scan_user_skills() -> Result<SkillScanResult, String> {
    scan_user_skills_dir()
}

/// 扫描项目 Skills 目录
#[tauri::command]
pub async fn scan_project_skills(project_path: String) -> Result<SkillScanResult, String> {
    scan_project_skills_dir(&project_path)
}

/// 匹配 Skills
///
/// 根据输入文本匹配所有启用的 Skills
#[tauri::command]
pub async fn match_skills_cmd(input: String) -> Result<MatchResult, String> {
    match_skills_from_config(&input)
}

/// 获取所有 Skills 的 L1 元数据（轻量级）
#[tauri::command]
pub async fn get_skill_metadata_list() -> Result<Vec<SkillMetadata>, String> {
    get_all_skill_metadata()
}

/// 加载 Skill 的 L2 主体内容
#[tauri::command]
pub async fn load_skill_body_cmd(skill_name: String) -> Result<SkillBody, String> {
    load_skill_body(&skill_name)
}

/// 获取 Skill 的 L3 资源列表
#[tauri::command]
pub async fn get_skill_resources_cmd(skill_name: String) -> Result<SkillResources, String> {
    get_skill_resources(&skill_name)
}

/// 加载 L3 资源内容
#[tauri::command]
pub async fn load_skill_resource_cmd(resource_path: String) -> Result<LoadedResource, String> {
    load_skill_resource(&resource_path)
}

/// 获取 tools 配置
#[tauri::command]
pub async fn get_tools_config() -> Result<ToolsConfig, String> {
    load_tools_config()
}

/// 保存 tools 配置
#[tauri::command]
pub async fn set_tools_config(config: ToolsConfig) -> Result<ToolsConfig, String> {
    save_tools_config(&config)?;
    Ok(config)
}

/// 获取所有 Skills（内置 + 用户）
#[tauri::command]
pub async fn list_skills() -> Result<Vec<Skill>, String> {
    let config = load_tools_config()?;
    let mut skills = config.skills.builtin.clone();
    skills.extend(config.skills.user.clone());
    Ok(skills)
}

/// 获取所有 Commands（内置 + 辅助 + 用户）
#[tauri::command]
pub async fn list_all_commands() -> Result<Vec<Command>, String> {
    let config = load_tools_config()?;
    let mut commands = config.commands.builtin.clone();
    commands.extend(config.commands.auxiliary.clone());
    commands.extend(config.commands.user.clone());
    Ok(commands)
}

/// 添加用户 Skill
#[tauri::command]
pub async fn add_user_skill(skill: Skill) -> Result<ToolsConfig, String> {
    let mut config = load_tools_config()?;

    // 检查是否已存在
    if config.skills.user.iter().any(|s| s.name == skill.name) {
        return Err(format!("Skill '{}' 已存在", skill.name));
    }

    config.skills.user.push(skill);
    save_tools_config(&config)?;
    Ok(config)
}

/// 移除用户 Skill
#[tauri::command]
pub async fn remove_user_skill(name: String) -> Result<ToolsConfig, String> {
    let mut config = load_tools_config()?;

    let original_len = config.skills.user.len();
    config.skills.user.retain(|s| s.name != name);

    if config.skills.user.len() == original_len {
        return Err(format!("Skill '{}' 不存在", name));
    }

    save_tools_config(&config)?;
    Ok(config)
}

/// 更新 Skill 启用状态
#[tauri::command]
pub async fn toggle_skill_enabled(name: String, enabled: bool) -> Result<ToolsConfig, String> {
    let mut config = load_tools_config()?;

    // 先在 user skills 中查找
    for skill in &mut config.skills.user {
        if skill.name == name {
            skill.enabled = enabled;
            save_tools_config(&config)?;
            return Ok(config);
        }
    }

    // 再在 builtin skills 中查找（内置 skill 也可以禁用）
    for skill in &mut config.skills.builtin {
        if skill.name == name {
            skill.enabled = enabled;
            save_tools_config(&config)?;
            return Ok(config);
        }
    }

    Err(format!("Skill '{}' 不存在", name))
}

/// 更新 Skill 触发规则
#[tauri::command]
pub async fn update_skill_triggers(
    skill_name: String,
    triggers: SkillTrigger,
) -> Result<ToolsConfig, String> {
    let mut config = load_tools_config()?;

    // 先在 user skills 中查找
    for skill in &mut config.skills.user {
        if skill.name == skill_name {
            skill.triggers = triggers;
            save_tools_config(&config)?;
            return Ok(config);
        }
    }

    // 再在 builtin skills 中查找
    for skill in &mut config.skills.builtin {
        if skill.name == skill_name {
            skill.triggers = triggers;
            save_tools_config(&config)?;
            return Ok(config);
        }
    }

    Err(format!("Skill '{}' 不存在", skill_name))
}

/// 更新 Skill 的 body 内容（支持 Markdown 编辑）
#[tauri::command]
pub async fn update_skill_body(
    skill_name: String,
    body: String,
) -> Result<ToolsConfig, String> {
    let mut config = load_tools_config()?;

    // 先在 user skills 中查找
    for skill in &mut config.skills.user {
        if skill.name == skill_name {
            skill.body = Some(body);
            save_tools_config(&config)?;
            return Ok(config);
        }
    }

    // 再在 builtin skills 中查找
    for skill in &mut config.skills.builtin {
        if skill.name == skill_name {
            skill.body = Some(body);
            save_tools_config(&config)?;
            return Ok(config);
        }
    }

    Err(format!("Skill '{}' 不存在", skill_name))
}

/// 在 VS Code 中打开 tools.yaml（只打开，不在工具内编辑）
#[tauri::command]
pub async fn open_tools_config_in_vscode() -> Result<(), String> {
    let path = ensure_tools_yaml_exists()?;
    open_in_vscode(&path, Some(1), Some(1))
}

/// 在 VS Code 中打开 Skill 对应的编辑位置
///
/// - `target = "skill_md"`：打开 `<source>/SKILL.md`（用于编辑内容/frontmatter）
/// - `target = "tools_yaml"`：打开 `~/.cc-spec/tools.yaml` 并定位到该 Skill（用于编辑触发器等）
#[tauri::command]
pub async fn open_skill_in_vscode(skill_name: String, target: Option<String>) -> Result<(), String> {
    let config = load_tools_config()?;
    let skill = config
        .skills
        .user
        .iter()
        .find(|s| s.name == skill_name)
        .or_else(|| config.skills.builtin.iter().find(|s| s.name == skill_name))
        .ok_or_else(|| format!("Skill '{}' 不存在", skill_name))?;

    let target = target.unwrap_or_else(|| "tools_yaml".to_string());
    if target == "skill_md" {
        let source = skill
            .source
            .as_ref()
            .ok_or_else(|| "该 Skill 没有 source 路径（可能是内置 Skill）".to_string())?;
        let skill_md = PathBuf::from(source).join("SKILL.md");
        if !skill_md.exists() {
            return Err(format!("SKILL.md 不存在: {}", skill_md.display()));
        }
        return open_in_vscode(&skill_md, Some(1), Some(1));
    }

    let tools_yaml = ensure_tools_yaml_exists()?;
    let line = find_tools_yaml_line_for_skill(&tools_yaml, &skill_name).unwrap_or(1);
    open_in_vscode(&tools_yaml, Some(line), Some(1))
}

/// 获取项目 Skills 安装状态
#[tauri::command]
pub async fn get_project_skills_status(project_path: String) -> Result<Option<ProjectState>, String> {
    let config = load_tools_config()?;
    Ok(config.projects.get(&project_path).cloned())
}

/// 更新项目 Skills 安装状态
#[tauri::command]
pub async fn update_project_skills_status(
    project_path: String,
    skills_installed: Vec<String>,
) -> Result<ToolsConfig, String> {
    let mut config = load_tools_config()?;

    let state = config.projects.entry(project_path).or_insert_with(|| ProjectState {
        initialized_at: chrono::Utc::now().to_rfc3339(),
        commands_version: String::new(),
        skills_installed: Vec::new(),
        custom_overrides: Vec::new(),
    });

    state.skills_installed = skills_installed;

    save_tools_config(&config)?;
    Ok(config)
}
