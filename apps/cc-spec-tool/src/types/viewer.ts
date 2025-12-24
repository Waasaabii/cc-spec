// types/viewer.ts - Viewer 核心类型定义

export const MAX_LINES = 500;
export const DEFAULT_PORT = 38888;
export const TOOL_CALL_MAX_LINES = 5;
export const HISTORY_SAVE_DEBOUNCE_MS = 800;

export type LayoutMode = "list" | "grid";
export type RunStatus = "running" | "completed" | "error";
export type ConnectionState = "connecting" | "connected" | "error";
export type Language = "zh" | "en";
export type Theme = "dark" | "light";

export type StreamLine = {
    type: "user" | "agent" | "tool_start" | "tool_end" | "output" | "thinking" | "error" | "info" | "file_op";
    content: string;
    status?: "running" | "success" | "failed";
    duration?: string;
};

export type CodeChanges = {
    filesChanged: number;
    linesAdded: number;
    linesRemoved: number;
};

export type RunState = {
    id: string;
    runIds: string[];
    projectRoot?: string;
    sessionId?: string | null;
    status: RunStatus;
    startedAt?: string;
    completedAt?: string;
    success?: boolean;
    exitCode?: number;
    errorType?: string;
    duration?: number;
    turnCount: number;
    thinkingStartTime?: number;
    lines: StreamLine[];
    codeChanges: CodeChanges;
};

export type ViewerSettings = { port: number };

export const translations = {
    zh: {
        title: "cc-spec tools",
        subtitle: "项目管理与执行监控",
        clearRuns: "清空",
        runs: "执行任务",
        waitingEvents: "等待 Codex 执行...",
        projects: "项目",
        projectHint: "导入本地项目，作为会话、索引与技能的管理入口",
        currentProject: "当前项目",
        noProjectSelected: "尚未选择项目",
        projectPathPlaceholder: "输入项目路径（例如 C:\\develop\\cc-spec）",
        projectPathRequired: "请先输入项目路径",
        importProject: "导入项目",
        refresh: "刷新",
        projectList: "项目列表",
        setCurrent: "设为当前",
        removeProject: "移除",
        noProjects: "暂无项目记录",
        openClaudeTerminal: "打开 Claude 终端",
        loading: "加载中",
        projectNotFound: "项目不存在或已被移除",
        confirmRemoveProject: "确认从列表移除此项目？",
        selectProjectHint: "先导入并选择项目，运行记录将按项目归档显示。",
        projectEmpty: "暂无运行记录",
        projectEmptyHint: "当前项目还没有 Codex 运行记录。",
        navProjects: "项目中心",
        navRuns: "运行列表",
        skillsTitle: "Commands 管理",
        skillsHint: "将 cc-spec commands 安装到当前项目的 .claude/commands",
        skillsVersion: "内置版本",
        skillsUpdateNeeded: "需要更新",
        skillsUpToDate: "已是最新",
        skillsInstall: "安装/更新",
        skillsUninstall: "卸载",
        skillsRefresh: "刷新状态",
        skillsNoProject: "请选择项目后管理 Commands",
        skillsEmpty: "暂无 Commands 状态，请刷新或安装",
        skillsInstalled: "已安装",
        skillsMissing: "未安装",
        active: "活跃",
        completed: "已完成",
        statusLive: "Running",
        statusDone: "Done",
        statusFailed: "Failed",
        statusIdle: "Idle",
        started: "开始",
        finished: "结束",
        duration: "耗时",
        exitCode: "退出码",
        errorType: "错误",
        noOutput: "暂无输出",
        connecting: "连接中...",
        connected: "已连接",
        connectionError: "断开重连中...",
        port: "端口",
        langMode: "English",
        copy: "复制",
        copied: "已复制",
        darkMode: "深色",
        lightMode: "浅色",
        stop: "停止",
        stopping: "停止中...",
    },
    en: {
        title: "cc-spec tools",
        subtitle: "Project hub and execution monitor",
        clearRuns: "Clear",
        runs: "Runs",
        waitingEvents: "Waiting for Codex...",
        projects: "Projects",
        projectHint: "Import a local project to manage sessions, indexes, and skills.",
        currentProject: "Current Project",
        noProjectSelected: "No project selected",
        projectPathPlaceholder: "Enter project path (e.g. C:\\develop\\cc-spec)",
        projectPathRequired: "Please enter a project path",
        importProject: "Import Project",
        refresh: "Refresh",
        projectList: "Project List",
        setCurrent: "Set Current",
        removeProject: "Remove",
        noProjects: "No projects yet",
        openClaudeTerminal: "Open Claude Terminal",
        loading: "Loading",
        projectNotFound: "Project not found or removed",
        confirmRemoveProject: "Remove this project from the list?",
        selectProjectHint: "Import and select a project to view runs grouped by project.",
        projectEmpty: "No runs yet",
        projectEmptyHint: "There are no Codex runs for the current project.",
        navProjects: "Projects",
        navRuns: "Runs",
        skillsTitle: "Commands Manager",
        skillsHint: "Install cc-spec commands into .claude/commands for this project.",
        skillsVersion: "Bundled Version",
        skillsUpdateNeeded: "Update Needed",
        skillsUpToDate: "Up to Date",
        skillsInstall: "Install/Update",
        skillsUninstall: "Uninstall",
        skillsRefresh: "Refresh",
        skillsNoProject: "Select a project to manage commands.",
        skillsEmpty: "No commands status yet. Refresh or install.",
        skillsInstalled: "Installed",
        skillsMissing: "Missing",
        active: "Active",
        completed: "Done",
        statusLive: "Running",
        statusDone: "Done",
        statusFailed: "Failed",
        statusIdle: "Idle",
        started: "Started",
        finished: "Finished",
        duration: "Duration",
        exitCode: "Exit",
        errorType: "Error",
        noOutput: "No output",
        connecting: "Connecting...",
        connected: "Connected",
        connectionError: "Reconnecting...",
        port: "Port",
        langMode: "中文",
        copy: "Copy",
        copied: "Copied",
        darkMode: "Dark",
        lightMode: "Light",
        stop: "Stop",
        stopping: "Stopping...",
    },
};

export const BG_IMAGES = [
    '122.png',
    '6fc129ee-5c9e-4f10-804b-0f73f198347b.png',
    'A8430D51D6F00D3A6CE72F04DC47C8FE.gif',
    'miao.gif',
    'ScreenShot_2025-12-17_175919_945.png',
    'wu.jpg'
];
