// types/skills.ts - Skills 管理类型定义

/**
 * 单个 Skill 状态
 */
export interface SkillStatus {
    /** Skill 名称 */
    name: string;
    /** 是否已安装 */
    installed: boolean;
    /** 安装的版本 */
    version: string | null;
    /** 安装路径 */
    path: string | null;
}

/**
 * Skills 安装结果
 */
export interface SkillsInstallResult {
    /** 是否成功 */
    success: boolean;
    /** 安装的 skill 数量 */
    installed_count: number;
    /** 跳过的 skill 数量 (已是最新) */
    skipped_count: number;
    /** 错误列表 */
    errors: string[];
    /** 各 skill 状态 */
    skills: SkillStatus[];
}

/**
 * Skills 列表
 */
export const SKILL_NAMES = [
    "cc-spec-specify",
    "cc-spec-clarify",
    "cc-spec-plan",
    "cc-spec-apply",
    "cc-spec-accept",
    "cc-spec-archive",
] as const;

export type SkillName = typeof SKILL_NAMES[number];

/**
 * Skill 阶段映射
 */
export const SKILL_STAGE_MAP: Record<SkillName, string> = {
    "cc-spec-specify": "specify",
    "cc-spec-clarify": "clarify",
    "cc-spec-plan": "plan",
    "cc-spec-apply": "apply",
    "cc-spec-accept": "accept",
    "cc-spec-archive": "archive",
};
