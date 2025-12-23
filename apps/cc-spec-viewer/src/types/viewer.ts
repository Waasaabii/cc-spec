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
        title: "Codex Stream Viewer",
        subtitle: "实时监控 Codex 执行输出",
        clearRuns: "清空",
        runs: "执行任务",
        waitingEvents: "等待 Codex 执行...",
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
        title: "Codex Stream Viewer",
        subtitle: "Real-time Codex execution monitor",
        clearRuns: "Clear",
        runs: "Runs",
        waitingEvents: "Waiting for Codex...",
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
