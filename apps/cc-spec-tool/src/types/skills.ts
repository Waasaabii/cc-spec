// types/skills.ts - Skills 管理类型定义

// ============================================================================
// 枚举类型
// ============================================================================

export type SkillType = "workflow" | "domain" | "execution";
export type EnforcementLevel = "require" | "suggest" | "silent";
export type Priority = "high" | "medium" | "low";
export type ResourceType = "reference" | "script" | "asset";

// ============================================================================
// 触发规则
// ============================================================================

export interface SkillTrigger {
  keywords: string[];
  patterns: string[];
}

// ============================================================================
// Skill 定义
// ============================================================================

export interface Skill {
  name: string;
  version: string;
  skill_type: SkillType;
  description: string;
  enabled: boolean;
  source?: string;
  imported_from?: string;
  imported_at?: string;
  body?: string;
  triggers: SkillTrigger;
}

// ============================================================================
// Command 定义
// ============================================================================

export interface Command {
  name: string;
  version: string;
  stage?: number;
  description: string;
  icon?: string;
  source?: string;
  imported_from?: string;
}

// ============================================================================
// 设置
// ============================================================================

export interface SkillsSettings {
  auto_suggest: boolean;
  max_concurrent_skills: number;
  progressive_loading: boolean;
}

export interface CommandsSettings {
  namespace: string;
  auto_install: boolean;
}

export interface TriggerSettings {
  case_sensitive: boolean;
  min_keyword_length: number;
  max_matches_per_prompt: number;
}

// ============================================================================
// 配置容器
// ============================================================================

export interface SkillsConfig {
  settings: SkillsSettings;
  builtin: Skill[];
  user: Skill[];
}

export interface CommandsConfig {
  settings: CommandsSettings;
  builtin: Command[];
  auxiliary: Command[];
  user: Command[];
}

export interface TriggerRulesConfig {
  settings: TriggerSettings;
  priority_order: string[];
}

export interface ProjectState {
  initialized_at: string;
  commands_version: string;
  skills_installed: string[];
  custom_overrides: string[];
}

// ============================================================================
// 顶层配置
// ============================================================================

export interface ToolsConfig {
  version: string;
  updated_at?: string;
  skills: SkillsConfig;
  commands: CommandsConfig;
  trigger_rules: TriggerRulesConfig;
  projects: Record<string, ProjectState>;
}

// ============================================================================
// 扫描结果
// ============================================================================

export interface SkillScanError {
  dir_name: string;
  error: string;
}

export interface SkillScanResult {
  skills: Skill[];
  errors: SkillScanError[];
  scanned_path: string;
}

// ============================================================================
// 匹配结果
// ============================================================================

export interface SkillMatch {
  skill: Skill;
  score: number;
  matched_keywords: string[];
  matched_patterns: string[];
}

export interface MatchResult {
  matches: SkillMatch[];
  input: string;
  case_sensitive: boolean;
}

// ============================================================================
// 渐进式加载
// ============================================================================

export interface SkillMetadata {
  name: string;
  description: string;
  skill_type: SkillType;
  enabled: boolean;
  has_body: boolean;
  has_resources: boolean;
}

export interface SkillBody {
  name: string;
  content: string;
  word_count: number;
}

export interface SkillResource {
  name: string;
  path: string;
  resource_type: ResourceType;
  size: number;
}

export interface SkillResources {
  skill_name: string;
  references: SkillResource[];
  scripts: SkillResource[];
  assets: SkillResource[];
}

export interface LoadedResource {
  path: string;
  content: string;
  resource_type: ResourceType;
}

// ============================================================================
// 迁移结果
// ============================================================================

export interface MigrationResult {
  migrated: boolean;
  from_version?: string;
  to_version: string;
  message: string;
}
