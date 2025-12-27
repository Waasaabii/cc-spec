// types/commands.ts - Commands 管理类型定义

import { translations, type Language } from "./viewer";

/**
 * 单个 Command 状态
 */
export interface CommandStatus {
    /** Command 名称 */
    name: string;
    /** 是否已安装 */
    installed: boolean;
    /** 安装的版本 */
    version: string | null;
    /** 安装路径 */
    path: string | null;
}

/**
 * Commands 安装结果
 */
export interface CommandsInstallResult {
    /** 是否成功 */
    success: boolean;
    /** 安装的 command 数量 */
    installed_count: number;
    /** 跳过的 command 数量 (已是最新) */
    skipped_count: number;
    /** 错误列表 */
    errors: string[];
    /** 各 command 状态 */
    commands: CommandStatus[];
}

/**
 * Commands 列表
 */
export const COMMAND_NAMES = [
    "cc-spec:specify",
    "cc-spec:clarify",
    "cc-spec:plan",
    "cc-spec:apply",
    "cc-spec:accept",
    "cc-spec:archive",
] as const;

export type CommandName = typeof COMMAND_NAMES[number];

/**
 * Command 阶段映射
 */
export const COMMAND_STAGE_MAP: Record<CommandName, string> = {
    "cc-spec:specify": "specify",
    "cc-spec:clarify": "clarify",
    "cc-spec:plan": "plan",
    "cc-spec:apply": "apply",
    "cc-spec:accept": "accept",
    "cc-spec:archive": "archive",
};

/**
 * Command 使用说明
 */
export interface CommandUsageInfo {
    /** Command 名称 */
    name: CommandName;
    /** 阶段名称 */
    stage: string;
    /** 描述 */
    description: string;
    /** 使用示例 */
    example: string;
    /** 使用技巧 */
    tips: string[];
}

/**
 * 获取 Commands 使用信息（支持国际化）
 */
export function getCommandUsageInfo(lang: Language): CommandUsageInfo[] {
    const t = translations[lang];
    return [
        {
            name: "cc-spec:specify",
            stage: "specify",
            description: t.cmdSpecifyDesc,
            example: "/cc-spec:specify 实现用户登录功能",
            tips: [t.cmdSpecifyTip1, t.cmdSpecifyTip2, t.cmdSpecifyTip3],
        },
        {
            name: "cc-spec:clarify",
            stage: "clarify",
            description: t.cmdClarifyDesc,
            example: "/cc-spec:clarify",
            tips: [t.cmdClarifyTip1, t.cmdClarifyTip2, t.cmdClarifyTip3],
        },
        {
            name: "cc-spec:plan",
            stage: "plan",
            description: t.cmdPlanDesc,
            example: "/cc-spec:plan",
            tips: [t.cmdPlanTip1, t.cmdPlanTip2, t.cmdPlanTip3],
        },
        {
            name: "cc-spec:apply",
            stage: "apply",
            description: t.cmdApplyDesc,
            example: "/cc-spec:apply W1-T1",
            tips: [t.cmdApplyTip1, t.cmdApplyTip2, t.cmdApplyTip3],
        },
        {
            name: "cc-spec:accept",
            stage: "accept",
            description: t.cmdAcceptDesc,
            example: "/cc-spec:accept",
            tips: [t.cmdAcceptTip1, t.cmdAcceptTip2, t.cmdAcceptTip3],
        },
        {
            name: "cc-spec:archive",
            stage: "archive",
            description: t.cmdArchiveDesc,
            example: "/cc-spec:archive",
            tips: [t.cmdArchiveTip1, t.cmdArchiveTip2, t.cmdArchiveTip3],
        },
    ];
}

/**
 * Commands 使用信息（已废弃，请使用 getCommandUsageInfo）
 * @deprecated 使用 getCommandUsageInfo(lang) 代替
 */
export const COMMAND_USAGE_INFO: CommandUsageInfo[] = getCommandUsageInfo("zh");

