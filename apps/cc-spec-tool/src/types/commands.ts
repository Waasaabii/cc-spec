// types/commands.ts - Commands 管理类型定义

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
    "cc-spec-specify",
    "cc-spec-clarify",
    "cc-spec-plan",
    "cc-spec-apply",
    "cc-spec-accept",
    "cc-spec-archive",
] as const;

export type CommandName = typeof COMMAND_NAMES[number];

/**
 * Command 阶段映射
 */
export const COMMAND_STAGE_MAP: Record<CommandName, string> = {
    "cc-spec-specify": "specify",
    "cc-spec-clarify": "clarify",
    "cc-spec-plan": "plan",
    "cc-spec-apply": "apply",
    "cc-spec-accept": "accept",
    "cc-spec-archive": "archive",
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
 * Commands 使用信息
 */
export const COMMAND_USAGE_INFO: CommandUsageInfo[] = [
    {
        name: "cc-spec-specify",
        stage: "specify",
        description: "与用户确认需求，输出 proposal.md",
        example: "/cc-spec-specify 实现用户登录功能",
        tips: [
            "在开始新功能开发前使用",
            "会生成 proposal.md 作为需求文档",
            "建议先描述清楚功能目标和范围",
        ],
    },
    {
        name: "cc-spec-clarify",
        stage: "clarify",
        description: "CC↔CX 讨论或用户审查",
        example: "/cc-spec-clarify",
        tips: [
            "用于审查任务执行结果",
            "可以标记返工项",
            "支持评分验收",
        ],
    },
    {
        name: "cc-spec-plan",
        stage: "plan",
        description: "用户确认后生成 tasks.yaml",
        example: "/cc-spec-plan",
        tips: [
            "根据 proposal.md 生成执行计划",
            "每个任务包含明确的验收标准",
            "支持 Wave 分组并行执行",
        ],
    },
    {
        name: "cc-spec-apply",
        stage: "apply",
        description: "使用 SubAgent 执行任务",
        example: "/cc-spec-apply W1-T1",
        tips: [
            "可以指定具体任务 ID 执行",
            "支持批量执行整个 Wave",
            "执行结果会自动记录",
        ],
    },
    {
        name: "cc-spec-accept",
        stage: "accept",
        description: "端到端验收",
        example: "/cc-spec-accept",
        tips: [
            "验收所有任务完成情况",
            "生成最终验收报告",
            "通过后可以归档变更",
        ],
    },
    {
        name: "cc-spec-archive",
        stage: "archive",
        description: "归档已完成的变更",
        example: "/cc-spec-archive",
        tips: [
            "将变更移动到 archive 目录",
            "保留完整的变更历史",
            "支持后续回溯查询",
        ],
    },
];
