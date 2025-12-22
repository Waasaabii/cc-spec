import { useEffect, useRef, useState, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark, oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import Ansi from "ansi-to-react";

const MAX_LINES = 500;
const DEFAULT_PORT = 38888;
const TOOL_CALL_MAX_LINES = 5; // 工具输出最多显示行数（参考codex TUI设计）
const HISTORY_SAVE_DEBOUNCE_MS = 800;

type LayoutMode = "list" | "grid";
type RunStatus = "running" | "completed" | "error";

type StreamLine = {
    type: "user" | "agent" | "tool_start" | "tool_end" | "output" | "thinking" | "error" | "info" | "file_op";
    content: string;
    status?: "running" | "success" | "failed"; // for tool_end
    duration?: string; // for tool_end
};

type CodeChanges = {
    filesChanged: number;
    linesAdded: number;
    linesRemoved: number;
};

type RunState = {
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

// 截断输出到指定行数，超过则显示省略信息
const truncateOutputLines = (output: string, maxLines: number): string => {
    const lines = output.split('\n');
    if (lines.length <= maxLines * 2) {
        return output;
    }
    // 显示头部和尾部各 maxLines 行
    const head = lines.slice(0, maxLines);
    const tail = lines.slice(-maxLines);
    const omitted = lines.length - maxLines * 2;
    return [...head, `  ... (${omitted} lines omitted) ...`, ...tail].join('\n');
};

// 解析代码变动统计
const parseCodeChanges = (raw: string): CodeChanges | null => {
    try {
        const obj = JSON.parse(raw);
        if (obj.type === "item.completed") {
            const item = obj.item;
            if (item?.type === "file_edit" || item?.type === "file_change") {
                let added = 0, removed = 0, files = 0;

                if (item.changes && Array.isArray(item.changes)) {
                    files = item.changes.length;
                    for (const c of item.changes) {
                        added += c.lines_added || c.insertions || 0;
                        removed += c.lines_removed || c.deletions || 0;
                    }
                } else {
                    files = 1;
                    added = item.lines_added || item.insertions || 0;
                    removed = item.lines_removed || item.deletions || 0;
                }

                if (files > 0) {
                    return { filesChanged: files, linesAdded: added, linesRemoved: removed };
                }
            }
        }
        return null;
    } catch {
        return null;
    }
};

// 紧凑化JSON输出（参考codex format_json_compact）
const formatJsonCompact = (text: string): string | null => {
    try {
        const json = JSON.parse(text);
        return JSON.stringify(json, null, 0)
            .replace(/,/g, ', ')
            .replace(/:/g, ': ');
    } catch {
        return null;
    }
};

// ... Parsing Logic ...
const parseCodeBlocks = (text: string): Array<{ type: "text" | "code"; content: string; lang?: string }> => {
    const parts: Array<{ type: "text" | "code"; content: string; lang?: string }> = [];
    const codeBlockRegex = /```(\w*)\n?([\s\S]*?)```/g;
    let lastIndex = 0;
    let match;

    while ((match = codeBlockRegex.exec(text)) !== null) {
        if (match.index > lastIndex) {
            const before = text.slice(lastIndex, match.index).trim();
            if (before) parts.push({ type: "text", content: before });
        }
        parts.push({ type: "code", content: match[2].trim(), lang: match[1] || "text" });
        lastIndex = match.index + match[0].length;
    }

    if (lastIndex < text.length) {
        const after = text.slice(lastIndex).trim();
        if (after) parts.push({ type: "text", content: after });
    }
    return parts.length > 0 ? parts : [{ type: "text", content: text }];
};

// 提取短文件名
const shortFileName = (path: string): string => path.split(/[/\\]/).slice(-2).join('/');

// 提取短命令
const shortCommand = (cmd: string, maxLen = 60): string => {
    const cleaned = cmd.replace(/^bash\s+-lc\s+/, '').replace(/^['"]|['"]$/g, '');
    return cleaned.length > maxLen ? cleaned.slice(0, maxLen) + "..." : cleaned;
};

const historyKey = (run: RunState): string => run.sessionId || run.id;

const mergeHistoryRuns = (current: RunState[], loaded: RunState[]): RunState[] => {
    if (loaded.length === 0) return current;
    const existing = new Set(current.map(historyKey));
    const merged = [...current];
    let added = false;
    for (const run of loaded) {
        const key = historyKey(run);
        if (!existing.has(key)) {
            merged.push(run);
            existing.add(key);
            added = true;
        }
    }
    return added ? merged : current;
};

const normalizeHistoryRuns = (runs: RunState[]): RunState[] => runs.map((run) => {
    const runIds = Array.isArray(run.runIds) ? run.runIds : [];
    return {
        ...run,
        runIds: runIds.length > 0 ? runIds : [run.id],
        lines: Array.isArray(run.lines) ? run.lines.slice(-MAX_LINES) : [],
        turnCount: run.turnCount ?? 1,
        codeChanges: run.codeChanges ?? { filesChanged: 0, linesAdded: 0, linesRemoved: 0 },
    };
});

const parseHistoryPayload = (raw: string): RunState[] | null => {
    try {
        const data = JSON.parse(raw) as RunState[];
        if (!Array.isArray(data)) return null;
        return normalizeHistoryRuns(data);
    } catch {
        return null;
    }
};

const groupRunsByProject = (runs: RunState[]): Map<string, RunState[]> => {
    const grouped = new Map<string, RunState[]>();
    for (const run of runs) {
        if (!run.projectRoot) continue;
        const list = grouped.get(run.projectRoot);
        if (list) {
            list.push(run);
        } else {
            grouped.set(run.projectRoot, [run]);
        }
    }
    return grouped;
};

// Prompt-style parsing (参考 codex TUI 设计)
const parseStreamLine = (raw: string): StreamLine | null => {
    try {
        const obj = JSON.parse(raw);
        const type = obj.type;

        // item.started -> tool_start
        if (type === "item.started") {
            const item = obj.item;
            if (item?.type === "command_execution") {
                return { type: "tool_start", content: shortCommand(item.command || ""), status: "running" };
            }
            if (item?.type === "file_edit" || item?.type === "file_write") {
                return { type: "tool_start", content: `Edit ${shortFileName(item.file_path || item.path || "")}`, status: "running" };
            }
            if (item?.type === "file_read") {
                return { type: "tool_start", content: `Read ${shortFileName(item.file_path || item.path || "")}`, status: "running" };
            }
        }

        // item.completed
        if (type === "item.completed") {
            const item = obj.item;

            // 推理/思考
            if (item?.type === "reasoning" && item?.text) {
                return { type: "thinking", content: item.text };
            }

            // Agent 消息
            if (item?.type === "agent_message" && item?.text) {
                return { type: "agent", content: item.text };
            }

            // 命令执行完成
            if (item?.type === "command_execution") {
                const cmd = item.command || "";
                const output = item.aggregated_output || "";
                const exitCode = item.exit_code;
                const duration = item.duration_s;
                const durationStr = duration ? `${duration.toFixed(1)}s` : "";
                const isSuccess = exitCode === 0;

                // 读取命令只显示摘要
                const isReadCmd = /Get-Content|cat |head |tail |less |more |type /i.test(cmd);
                if (isReadCmd && isSuccess) {
                    const lineCount = output.split('\n').length;
                    return {
                        type: "tool_end",
                        content: `Read ${lineCount} lines`,
                        status: "success",
                        duration: durationStr
                    };
                }

                // 其他命令显示输出
                const truncated = truncateOutputLines(output, TOOL_CALL_MAX_LINES);
                const formatted = formatJsonCompact(truncated) || truncated;
                return {
                    type: "tool_end",
                    content: shortCommand(cmd),
                    status: isSuccess ? "success" : "failed",
                    duration: durationStr
                };
            }

            // 文件编辑完成
            if (item?.type === "file_edit" || item?.type === "file_change") {
                if (item.changes && Array.isArray(item.changes)) {
                    const fileList = item.changes.map((c: { path?: string; kind?: string }) =>
                        `${c.kind || "edit"} ${shortFileName(c.path || "")}`
                    ).join(", ");
                    return { type: "file_op", content: fileList, status: "success" };
                }
                return { type: "file_op", content: `Edit ${shortFileName(item.file_path || item.path || "")}`, status: "success" };
            }

            // 文件读取完成
            if (item?.type === "file_read") {
                return { type: "file_op", content: `Read ${shortFileName(item.file_path || item.path || "")}`, status: "success" };
            }
        }

        // 错误
        if (type === "error") {
            const msg = obj.message || obj.error || "unknown error";
            return { type: "error", content: msg };
        }

        return null;
    } catch {
        // 非JSON文本作为agent消息
        if (raw.trim()) return { type: "agent", content: raw };
        return null;
    }
};

type ConnectionState = "connecting" | "connected" | "error";
type Language = "zh" | "en";
type Theme = "dark" | "light";
type ViewerSettings = { port: number };

const translations = {
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

const formatDuration = (duration?: number) => {
    if (!duration && duration !== 0) return "-";
    if (duration < 1) return `${Math.round(duration * 1000)}ms`;
    if (duration < 60) return `${duration.toFixed(1)}s`;
    const minutes = Math.floor(duration / 60);
    const seconds = Math.round(duration % 60);
    return `${minutes}m ${seconds}s`;
};

const formatTimestamp = (value?: string, lang: Language = "zh") => {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.valueOf())) return value;
    return date.toLocaleTimeString(lang === "zh" ? "zh-CN" : "en-US", { hour12: false });
};

// 紧凑时间格式（参考codex fmt_elapsed_compact）
const fmtElapsedCompact = (secs: number): string => {
    if (secs < 60) return `${secs}s`;
    if (secs < 3600) {
        const m = Math.floor(secs / 60);
        const s = secs % 60;
        return `${m}m ${s.toString().padStart(2, '0')}s`;
    }
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    return `${h}h ${m.toString().padStart(2, '0')}m ${s.toString().padStart(2, '0')}s`;
};

function ThinkingTimer({ startTime }: { startTime?: number }) {
    const [elapsed, setElapsed] = useState(0);
    useEffect(() => {
        if (!startTime) return;
        const interval = setInterval(() => {
            setElapsed(Math.floor((Date.now() - startTime) / 1000));
        }, 1000);
        return () => clearInterval(interval);
    }, [startTime]);

    if (!startTime) return null;
    return (
        <span className="status-indicator font-mono text-[10px] bg-purple-500/15 px-2.5 py-0.5 rounded-full border border-purple-500/30 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-purple-400 shadow-[0_0_8px_rgba(192,132,252,0.6)] animate-pulse"></span>
            <span className="thinking-shimmer">Working</span>
            <span className="text-purple-300 tabular-nums">{fmtElapsedCompact(elapsed)}</span>
        </span>
    );
}

function RenderContent({ content, type, theme }: { content: string; type: StreamLine["type"]; theme: Theme }) {
    // agent 和 user 类型支持代码块渲染
    if (type !== "agent" && type !== "user") return <Ansi>{content}</Ansi>;
    const blocks = parseCodeBlocks(content);
    const codeBlockClass = theme === "dark"
        ? "my-2 border border-slate-700 bg-[#0f1419] p-2 text-xs rounded-sm"
        : "my-2 border border-slate-200 bg-white/90 p-2 text-xs rounded-sm";
    const syntaxTheme = theme === "dark" ? oneDark : oneLight;
    return (
        <>
            {blocks.map((block, i) =>
                block.type === "code" ? (
                    <div key={i} className={codeBlockClass}>
                        <SyntaxHighlighter
                            language={block.lang || "text"}
                            style={syntaxTheme}
                            customStyle={{ margin: 0, padding: 0, background: "transparent" }}
                        >
                            {block.content}
                        </SyntaxHighlighter>
                    </div>
                ) : (
                    <span key={i}>{block.content}</span>
                )
            )}
        </>
    );
}

const Icons = {
    Clock: () => <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
    CheckCircle: () => <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
    XCircle: () => <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
    Stop: () => <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 6h12v12H6z" /></svg>,
    Terminal: () => <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>,
    Grid: () => <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" /></svg>,
    List: () => <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" /></svg>,
    Trash: () => <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>,
    Globe: () => <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129" /></svg>,
    Copy: () => <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>,
    Check: () => <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>,
    Sun: () => <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" /></svg>,
    Moon: () => <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" /></svg>,
};

// 背景图片列表（从public目录随机选择）
const BG_IMAGES = [
    '122.png',
    '6fc129ee-5c9e-4f10-804b-0f73f198347b.png',
    'A8430D51D6F00D3A6CE72F04DC47C8FE.gif',
    'miao.gif',
    'ScreenShot_2025-12-17_175919_945.png',
    'wu.jpg'
];

// NEW: Enhanced RunCard with Background Image support
function RunCard({
    run,
    lang,
    t,
    theme,
    sessions,
    isCompact = false,
}: {
    run: RunState;
    lang: Language;
    t: typeof translations["zh"];
    theme: Theme;
    sessions: Record<string, any>;
    isCompact?: boolean;
}) {
    const scrollRef = useRef<HTMLDivElement>(null);
    const [copied, setCopied] = useState(false);
    const [idCopied, setIdCopied] = useState(false);
    const [isStopping, setIsStopping] = useState(false);
    const [bgImage] = useState(() => {
        if (BG_IMAGES.length === 0) return "";
        const index = Math.floor(Math.random() * BG_IMAGES.length);
        return BG_IMAGES[index];
    });
    const sessionInfo = run.sessionId ? sessions[run.sessionId] : undefined;
    const sessionState = typeof sessionInfo?.state === "string" ? sessionInfo.state : undefined;
    const resolvedState = sessionState ?? (run.status === "error" || run.success === false ? "failed" : run.status === "completed" ? "done" : "running");
    const isRunning = resolvedState === "running";
    const isFailed = resolvedState === "failed";
    const isIdle = resolvedState === "idle";
    const isDone = resolvedState === "done";
    const sessionSummary = typeof sessionInfo?.task_summary === "string" ? sessionInfo.task_summary.trim() : "";
    const summaryPreview = sessionSummary.length > 50 ? `${sessionSummary.slice(0, 50)}...` : sessionSummary;
    const sessionElapsed = sessionInfo?.elapsed_s !== undefined ? Number(sessionInfo.elapsed_s) : undefined;
    const canStop = isRunning && Boolean(run.projectRoot) && Boolean(run.sessionId);
    const stopLabel = isStopping ? t.stopping : t.stop;

    // 获取显示用的短ID（取前8位）
    const shortId = (run.sessionId || run.id || "").slice(0, 8);
    const fullId = run.sessionId || run.id || "";

    useEffect(() => {
        if (scrollRef.current && isRunning) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [run.lines, isRunning]);

    const handleCopy = () => {
        const text = run.lines.map(l => l.content).join("\n");
        navigator.clipboard.writeText(text).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        });
    };

    const handleCopyId = () => {
        // 复制成可恢复对话的命令格式
        const resumeCmd = `codex --resume ${fullId}`;
        navigator.clipboard.writeText(resumeCmd).then(() => {
            setIdCopied(true);
            setTimeout(() => setIdCopied(false), 2000);
        });
    };

    const handleStop = async () => {
        if (!canStop || isStopping) return;
        setIsStopping(true);
        try {
            await invoke("stop_session", {
                project_path: run.projectRoot,
                session_id: run.sessionId,
            });
        } catch (err) {
            console.error("stop_session failed", err);
        } finally {
            setIsStopping(false);
        }
    };

    const statusColor = isRunning
        ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/30"
        : isIdle
            ? "text-amber-400 bg-amber-500/10 border-amber-500/30"
            : isFailed
                ? "text-rose-400 bg-rose-500/10 border-rose-500/30"
                : "text-slate-400 bg-slate-500/10 border-slate-500/30";

    return (
        <div className={`
      relative rounded-xl overflow-hidden shadow-lg
      flex flex-col
      ${theme === "dark" ? "bg-[#1e2030] border border-slate-700/60" : "bg-white border border-slate-200"}
      ${isRunning ? `ring-1 ring-emerald-500/30 ring-offset-2 ${theme === "dark" ? "ring-offset-[#1e2030]" : "ring-offset-white"}` : "hover:border-slate-500/50 hover:shadow-xl"}
      transition-all duration-300 animate-in fade-in slide-in-from-bottom-2
      ${isCompact ? "rounded-lg" : "rounded-xl"}
    `}>
            {/* Header */}
            <div className={`flex-none border-b flex items-center justify-between select-none ${theme === "dark" ? "bg-[#181926] border-slate-800" : "bg-slate-50 border-slate-200"} ${isCompact ? "px-3 py-1.5 gap-2" : "px-4 py-3"}`}>
                <div className={`flex flex-col ${isCompact ? "gap-1" : "gap-1.5"}`}>
                    <div className={`flex items-center ${isCompact ? "gap-2" : "gap-3"}`}>
                        <div className={`rounded font-bold uppercase tracking-wider border flex items-center gap-1.5 ${statusColor} ${isCompact ? "px-1.5 py-0.5 text-[9px]" : "px-2 py-0.5 text-[10px]"}`}>
                        {isRunning && <span className="relative flex h-1.5 w-1.5">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
                        </span>}
                        {isRunning ? t.statusLive : isIdle ? t.statusIdle : isFailed ? t.statusFailed : t.statusDone}
                        </div>

                        {isRunning && !isCompact && <ThinkingTimer startTime={run.thinkingStartTime} />}

                        {run.turnCount > 1 && (
                            <span className={`font-mono text-orange-400 bg-orange-400/10 border border-orange-400/20 px-1.5 rounded ${isCompact ? "text-[9px]" : "text-[10px]"}`}>
                                #{run.turnCount}
                            </span>
                        )}

                        {run.projectRoot && !isCompact && (
                            <span className="hidden sm:inline-block text-[10px] text-slate-500 font-mono">
                                {run.projectRoot.split(/[/\\]/).pop()}
                            </span>
                        )}
                    </div>
                    {summaryPreview && (
                        <div className={`truncate ${isCompact ? "text-[9px]" : "text-[10px]"} ${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>
                            {summaryPreview}
                        </div>
                    )}
                </div>

                <div className="flex items-center gap-2">
                    {isRunning && (
                        <button
                            onClick={handleStop}
                            disabled={!canStop || isStopping}
                            className={`transition-colors p-1 rounded ${
                                theme === "dark"
                                    ? "text-rose-400 hover:text-rose-300 hover:bg-rose-500/10"
                                    : "text-rose-500 hover:text-rose-600 hover:bg-rose-100"
                            } ${!canStop || isStopping ? "opacity-50 cursor-not-allowed hover:bg-transparent" : ""}`}
                            title={stopLabel}
                            aria-label={stopLabel}
                        >
                            <Icons.Stop />
                        </button>
                    )}
                    {/* Session ID with copy */}
                    {shortId && (
                        <button
                            onClick={handleCopyId}
                            className={`font-mono flex items-center gap-1 px-1.5 py-0.5 rounded transition-all ${
                                idCopied
                                    ? "text-emerald-400 bg-emerald-500/10"
                                    : theme === "dark"
                                        ? "text-slate-500 hover:text-slate-300 hover:bg-slate-700/50"
                                        : "text-slate-500 hover:text-slate-700 hover:bg-slate-200/50"
                            } ${isCompact ? "text-[9px]" : "text-[10px]"}`}
                            title={`${lang === "zh" ? "点击复制恢复命令" : "Copy resume command"}: codex --resume ${fullId}`}
                        >
                            {idCopied ? <Icons.Check /> : <Icons.Terminal />}
                            <span>{shortId}</span>
                        </button>
                    )}
                    <button
                        onClick={handleCopy}
                        className={`transition-colors p-1 ${theme === "dark" ? "text-slate-500 hover:text-white" : "text-slate-500 hover:text-slate-800"}`}
                        title={t.copy}
                    >
                        {copied ? <Icons.Check /> : <Icons.Copy />}
                    </button>
                </div>
            </div>

            {/* Terminal View with Background */}
            <div
                ref={scrollRef}
                className={`
          relative flex-1 overflow-auto font-['JetBrains_Mono'] leading-relaxed custom-scrollbar
          shadow-inner
          ${theme === "dark" ? "bg-[#1a1b2e]" : "bg-gradient-to-br from-blue-50/80 to-purple-50/80"}
          ${isCompact
                   ? "max-h-[28vh] p-3 text-[11px]"
                   : "max-h-[60vh] p-4 text-[12px]"}
        `}
            >
                {/* Background Images Overlay */}
                {bgImage && (
                    <div
                        className="absolute inset-0 z-0 opacity-[0.05] pointer-events-none bg-cover bg-center bg-no-repeat"
                        style={{ backgroundImage: `url('/${bgImage}')` }}
                    ></div>
                )}

                <div className="relative z-10 w-full min-h-full">
                    {run.lines.length === 0 ? (
                        <div className="h-full flex flex-col items-center justify-center opacity-30 gap-2">
                            <Icons.Terminal />
                            <span className="text-[10px] font-mono">{t.noOutput}</span>
                        </div>
                    ) : (
                        <div className="flex flex-col gap-0.5">
                            {run.lines.map((line, idx) => {
                                // 参考 codex TUI 的渲染样式
                                switch (line.type) {
                                    case "user":
                                        // 用户消息: › message (醒目样式：背景色、左边框、更大间距)
                                        return (
                                            <div
                                                key={idx}
                                                className={`mt-5 mb-4 flex items-start gap-2 rounded-r-lg border-l-[5px] px-5 py-4 ${theme === "dark"
                                                    ? "bg-indigo-500/20 border-indigo-300"
                                                    : "bg-indigo-100 border-indigo-400"
                                                }`}
                                            >
                                                <span className={`font-bold ${theme === "dark" ? "text-indigo-300" : "text-indigo-600"}`}>›</span>
                                                <span className={`font-medium leading-relaxed ${theme === "dark" ? "text-indigo-100" : "text-indigo-900"}`}>
                                                    <RenderContent content={line.content} type={line.type} theme={theme} />
                                                </span>
                                            </div>
                                        );

                                    case "agent":
                                        // Agent 消息: • message
                                        return (
                                            <div key={idx} className={theme === "dark" ? "text-slate-200" : "text-slate-800"}>
                                                <span className={`mr-1 ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>•</span>
                                                <RenderContent content={line.content} type={line.type} theme={theme} />
                                            </div>
                                        );

                                    case "tool_start":
                                        // 工具开始: • Running command
                                        return (
                                            <div key={idx} className="mt-2 flex items-center gap-1.5">
                                                <span
                                                    className={`${theme === "dark" ? "text-amber-400" : "text-amber-600"} ${isRunning ? "animate-pulse" : ""}`}
                                                >
                                                    •
                                                </span>
                                                <span className={`font-medium ${theme === "dark" ? "text-slate-400" : "text-slate-600"}`}>Running</span>
                                                <span className={`font-mono text-[11px] ${theme === "dark" ? "text-cyan-400" : "text-cyan-700"}`}>{line.content}</span>
                                            </div>
                                        );

                                    case "tool_end":
                                        // 工具结束: • Ran command (duration)
                                        return (
                                            <div key={idx} className="mt-2 flex items-center gap-1.5 flex-wrap">
                                                <span className={line.status === "success" ? (theme === "dark" ? "text-emerald-400 font-bold" : "text-emerald-600 font-bold") : (theme === "dark" ? "text-rose-400 font-bold" : "text-rose-600 font-bold")}>
                                                    {line.status === "success" ? "✓" : "✗"}
                                                </span>
                                                <span className={`font-medium ${theme === "dark" ? "text-slate-400" : "text-slate-600"}`}>Ran</span>
                                                <span className={`font-mono text-[11px] ${theme === "dark" ? "text-cyan-400" : "text-cyan-700"}`}>{line.content}</span>
                                                {line.duration && <span className={`text-[10px] ${theme === "dark" ? "text-slate-500" : "text-slate-600"}`}>• {line.duration}</span>}
                                            </div>
                                        );

                                    case "output":
                                        // 输出: └ output (暗淡)
                                        return (
                                            <div key={idx} className={`text-[11px] pl-4 opacity-70 ${theme === "dark" ? "text-slate-500" : "text-slate-600"}`}>
                                                <span className={`mr-1 ${theme === "dark" ? "text-slate-600" : "text-slate-500"}`}>└</span>
                                                <Ansi>{line.content}</Ansi>
                                            </div>
                                        );

                                    case "file_op":
                                        // 文件操作: ✓ Read/Edit file
                                        return (
                                            <div key={idx} className="flex items-center gap-1.5 text-[11px]">
                                                <span className={`font-bold ${theme === "dark" ? "text-emerald-400" : "text-emerald-600"}`}>✓</span>
                                                <span className={theme === "dark" ? "text-slate-400" : "text-slate-600"}>{line.content}</span>
                                            </div>
                                        );

                                    case "thinking":
                                        // 思考: • thinking (shimmer + 斜体，非运行状态停止动画)
                                        return (
                                            <div key={idx} className="pl-3 border-l border-purple-500/30 my-1">
                                                <span className={`mr-1 ${theme === "dark" ? "text-slate-600" : "text-slate-500"}`}>•</span>
                                                <span className={`italic text-[11px] ${isRunning ? "thinking-shimmer" : "text-purple-400/60"}`}>{line.content}</span>
                                            </div>
                                        );

                                    case "error":
                                        // 错误: ✗ error message
                                        return (
                                            <div key={idx} className={`flex items-start gap-1.5 px-2 py-1 rounded my-1 ${theme === "dark" ? "bg-rose-500/10" : "bg-rose-100"}`}>
                                                <span className={`font-bold ${theme === "dark" ? "text-rose-400" : "text-rose-600"}`}>✗</span>
                                                <span className={`text-[11px] ${theme === "dark" ? "text-rose-300" : "text-rose-700"}`}>{line.content}</span>
                                            </div>
                                        );

                                    case "info":
                                        // 分隔线
                                        return (
                                            <div key={idx} className="text-slate-600 text-[10px] text-center my-3 opacity-50">
                                                {line.content}
                                            </div>
                                        );

                                    default:
                                        return (
                                            <div key={idx} className={theme === "dark" ? "text-slate-300" : "text-slate-700"}>
                                                <RenderContent content={line.content} type={line.type} theme={theme} />
                                            </div>
                                        );
                                }
                            })}

                            {isRunning && (
                                <div className="mt-2 text-emerald-500/50 animate-pulse pl-1">_</div>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {/* Footer Status */}
            <div className={`flex-none border-t flex items-center justify-between font-medium select-none ${theme === "dark" ? "bg-[#181926] border-slate-800/80 text-slate-500" : "bg-slate-50 border-slate-200 text-slate-600"} ${isCompact ? "px-3 py-1 text-[9px]" : "px-4 py-1.5 text-[10px]"}`}>
                <div className="flex items-center gap-2">
                    <Icons.Clock />
                    <span className="font-mono">{formatTimestamp(run.startedAt, lang)}</span>
                </div>
                <div className={`flex items-center ${isCompact ? "gap-2" : "gap-4"}`}>
                    {/* 代码变动统计 */}
                    {(run.codeChanges?.filesChanged > 0 || run.codeChanges?.linesAdded > 0 || run.codeChanges?.linesRemoved > 0) && (
                        <span className="font-mono flex items-center gap-1.5">
                            {run.codeChanges.filesChanged > 0 && (
                                <span className="text-blue-400">{run.codeChanges.filesChanged} {isCompact ? "F" : "files"}</span>
                            )}
                            {run.codeChanges.linesAdded > 0 && (
                                <span className="text-emerald-400">+{run.codeChanges.linesAdded}</span>
                            )}
                            {run.codeChanges.linesRemoved > 0 && (
                                <span className="text-rose-400">-{run.codeChanges.linesRemoved}</span>
                            )}
                        </span>
                    )}
                    {(sessionElapsed !== undefined || run.duration !== undefined || isRunning) && (
                        <span className={`font-mono ${isRunning ? "text-emerald-500" : ""}`}>
                            {formatDuration(sessionElapsed ?? run.duration)}
                        </span>
                    )}
                    {run.exitCode !== undefined && (
                        <span className={`font-mono flex items-center gap-1 ${run.exitCode === 0 ? "text-emerald-500" : "text-rose-500"}`}>
                            {run.exitCode}
                        </span>
                    )}
                </div>
            </div>
        </div>
    );
}

// RESTORED: Original App Layout (Light Theme, Gradients) with New RunCard
export default function App() {
    const [lang, setLang] = useState<Language>("zh");
    const [theme, setTheme] = useState<Theme>(() => {
        const saved = localStorage.getItem("cc-spec-viewer-theme");
        return (saved === "dark" || saved === "light") ? saved : "light";
    });
    const [port, setPort] = useState(DEFAULT_PORT);
    const [showPortInput, setShowPortInput] = useState(false);
    const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");
    const [runs, setRuns] = useState<RunState[]>([]);
    const [sessions, setSessions] = useState<Record<string, any>>({});
    const [layoutMode, setLayoutMode] = useState<LayoutMode>("list");
    const eventSourceRef = useRef<EventSource | null>(null);
    const reconnectTimerRef = useRef<number | null>(null);
    const runsRef = useRef<RunState[]>([]);
    const historyLoadedRef = useRef<Set<string>>(new Set());
    const historyLoadingRef = useRef<Set<string>>(new Set());
    const saveTimerRef = useRef<number | null>(null);

    const bringWindowToFront = useCallback(async () => {
        try {
            const win = getCurrentWindow();
            await win.unminimize();
            await win.setFocus();
        } catch { }
    }, []);

    const t = translations[lang];
    const sseUrl = `http://127.0.0.1:${port}/events`;

    useEffect(() => {
        invoke<ViewerSettings>("get_settings")
            .then((settings) => {
                if (settings.port && settings.port !== port) setPort(settings.port);
            })
            .catch(() => { });
    }, []);

    useEffect(() => {
        localStorage.setItem("cc-spec-viewer-theme", theme);
        document.documentElement.dataset.theme = theme;
    }, [theme]);

    useEffect(() => {
        runsRef.current = runs;
    }, [runs]);

    useEffect(() => {
        const loadSessions = async () => {
            const roots = new Set(runs.map(r => r.projectRoot).filter(Boolean));
            for (const root of roots) {
                try {
                    const raw = await invoke<string>('load_sessions', { project_path: root });
                    const data = JSON.parse(raw);
                    if (data.sessions) {
                        setSessions(prev => ({ ...prev, ...data.sessions }));
                    }
                } catch { }
            }
        };
        loadSessions();
        const interval = setInterval(loadSessions, 5000);
        return () => clearInterval(interval);
    }, [runs]);

    const scheduleHistorySave = useCallback(() => {
        if (saveTimerRef.current) {
            clearTimeout(saveTimerRef.current);
        }
        saveTimerRef.current = window.setTimeout(() => {
            const grouped = groupRunsByProject(runsRef.current);
            for (const [projectRoot, history] of grouped) {
                if (!historyLoadedRef.current.has(projectRoot)) continue;
                const payload = JSON.stringify(history);
                invoke("save_history", { project_path: projectRoot, history_json: payload }).catch(() => { });
            }
        }, HISTORY_SAVE_DEBOUNCE_MS);
    }, []);

    const ensureHistoryLoaded = useCallback((projectRoot: string) => {
        if (!projectRoot) return;
        if (historyLoadedRef.current.has(projectRoot) || historyLoadingRef.current.has(projectRoot)) return;
        historyLoadingRef.current.add(projectRoot);
        invoke<string>("load_history", { project_path: projectRoot })
            .then((raw) => {
                const parsed = parseHistoryPayload(raw);
                if (parsed && parsed.length > 0) {
                    setRuns((prev) => mergeHistoryRuns(prev, parsed));
                }
            })
            .catch(() => { })
            .finally(() => {
                historyLoadingRef.current.delete(projectRoot);
                historyLoadedRef.current.add(projectRoot);
                scheduleHistorySave();
            });
    }, [scheduleHistorySave]);

    useEffect(() => {
        const roots = new Set<string>();
        for (const run of runs) {
            if (run.projectRoot) roots.add(run.projectRoot);
        }
        roots.forEach((root) => ensureHistoryLoaded(root));
    }, [runs, ensureHistoryLoaded]);

    useEffect(() => {
        scheduleHistorySave();
    }, [runs, scheduleHistorySave]);

    useEffect(() => {
        return () => {
            if (saveTimerRef.current) {
                clearTimeout(saveTimerRef.current);
                saveTimerRef.current = null;
            }
        };
    }, []);

    const findSession = (runs: RunState[], sessionId: string | null | undefined, runId: string): number => {
        if (sessionId) {
            const idx = runs.findIndex((r) => r.sessionId === sessionId);
            if (idx >= 0) return idx;
        }
        return runs.findIndex((r) => r.runIds.includes(runId));
    };

    const updateSession = (
        runId: string,
        sessionId: string | null | undefined,
        updater: (prev: RunState | null, isNewTurn: boolean) => RunState
    ) => {
        setRuns((prev) => {
            const index = findSession(prev, sessionId, runId);
            const existing = index >= 0 ? prev[index] : null;
            const isNewTurn = existing !== null && !existing.runIds.includes(runId);
            const next = updater(existing, isNewTurn);
            if (!next.runIds.includes(runId)) {
                next.runIds = [...next.runIds, runId];
            }
            if (index >= 0) {
                const clone = [...prev];
                clone[index] = next;
                return clone;
            }
            return [next, ...prev];
        });
    };

    const connect = () => {
        if (eventSourceRef.current) {
            eventSourceRef.current.close();
            eventSourceRef.current = null;
        }

        setConnectionState("connecting");
        const source = new EventSource(sseUrl);
        eventSourceRef.current = source;

        source.onopen = () => {
            setConnectionState("connected");
            if (reconnectTimerRef.current) {
                clearTimeout(reconnectTimerRef.current);
                reconnectTimerRef.current = null;
            }
        };

        source.onerror = () => {
            setConnectionState("error");
            source.close();
            eventSourceRef.current = null;
            if (!reconnectTimerRef.current) {
                reconnectTimerRef.current = window.setTimeout(() => {
                    reconnectTimerRef.current = null;
                    connect();
                }, 3000);
            }
        };

        const parsePayload = (event: MessageEvent) => {
            try { return JSON.parse(event.data); } catch { return null; }
        };

        let pendingUserInput: string | null = null;
        source.addEventListener("codex.user_input", (event) => {
            const payload = parsePayload(event as MessageEvent);
            if (!payload?.text) return;
            const sessionId = payload.session_id;
            setRuns((prev) => {
                let index = sessionId ? prev.findIndex((r) => r.sessionId === sessionId) : -1;
                if (index < 0) index = prev.findIndex((r) => r.status === "running");

                if (index >= 0) {
                    const clone = [...prev];
                    const existing = clone[index];
                    clone[index] = {
                        ...existing,
                        lines: [...existing.lines, { type: "user", content: payload.text }],
                    };
                    return clone;
                }
                pendingUserInput = payload.text;
                return prev;
            });
        });

        source.addEventListener("codex.started", (event) => {
            const payload = parsePayload(event as MessageEvent);
            if (!payload?.run_id) return;
            bringWindowToFront();
            updateSession(payload.run_id, payload.session_id, (prev, isNewTurn) => {
                const newLines = [...(prev?.lines ?? [])];
                if (isNewTurn && newLines.length > 0) newLines.push({ type: "info", content: "───" });
                if (pendingUserInput) {
                    newLines.push({ type: "user", content: pendingUserInput });
                    pendingUserInput = null;
                }
                return {
                    id: payload.session_id || prev?.id || payload.run_id,
                    runIds: prev?.runIds ?? [],
                    projectRoot: payload.project_root ?? prev?.projectRoot,
                    sessionId: payload.session_id ?? prev?.sessionId,
                    status: "running",
                    startedAt: prev?.startedAt ?? payload.ts,
                    completedAt: prev?.completedAt,
                    success: prev?.success,
                    exitCode: prev?.exitCode,
                    errorType: prev?.errorType,
                    duration: prev?.duration,
                    turnCount: (prev?.turnCount ?? 0) + (isNewTurn || !prev ? 1 : 0),
                    thinkingStartTime: Date.now(),
                    lines: newLines,
                    codeChanges: prev?.codeChanges ?? { filesChanged: 0, linesAdded: 0, linesRemoved: 0 },
                };
            });
        });

        source.addEventListener("codex.stream", (event) => {
            const payload = parsePayload(event as MessageEvent);
            if (!payload?.run_id) return;
            const raw = typeof payload.text === "string" ? payload.text : "";
            if (!raw) return;
            const parsed = parseStreamLine(raw);
            const changes = parseCodeChanges(raw);
            if (!parsed && !changes) return;
            updateSession(payload.run_id, payload.session_id, (prev) => {
                const defaultChanges: CodeChanges = { filesChanged: 0, linesAdded: 0, linesRemoved: 0 };
                const base: RunState = prev ?? {
                    id: payload.session_id || payload.run_id,
                    runIds: [],
                    status: "running",
                    turnCount: 1,
                    lines: [],
                    codeChanges: defaultChanges,
                };
                let nextLines = [...base.lines];
                if (parsed) {
                    // 合并连续的 agent 消息（流式输出）
                    if (parsed.type === "agent" && nextLines.length > 0) {
                        const last = nextLines[nextLines.length - 1];
                        if (last.type === "agent") {
                            nextLines[nextLines.length - 1] = { type: "agent", content: last.content + parsed.content };
                        } else {
                            nextLines.push(parsed);
                        }
                    }
                    // tool_start 后面跟着 tool_end 时，移除 tool_start
                    else if (parsed.type === "tool_end" && nextLines.length > 0) {
                        const last = nextLines[nextLines.length - 1];
                        if (last.type === "tool_start" && last.content === parsed.content) {
                            nextLines[nextLines.length - 1] = parsed; // 替换为 tool_end
                        } else {
                            nextLines.push(parsed);
                        }
                    } else {
                        nextLines.push(parsed);
                    }
                }
                if (nextLines.length > MAX_LINES) nextLines.splice(0, nextLines.length - MAX_LINES);

                // 累加代码变动统计
                const nextChanges = changes ? {
                    filesChanged: (base.codeChanges?.filesChanged || 0) + changes.filesChanged,
                    linesAdded: (base.codeChanges?.linesAdded || 0) + changes.linesAdded,
                    linesRemoved: (base.codeChanges?.linesRemoved || 0) + changes.linesRemoved,
                } : base.codeChanges || defaultChanges;

                return { ...base, status: "running", projectRoot: payload.project_root ?? base.projectRoot, sessionId: payload.session_id ?? base.sessionId, lines: nextLines, codeChanges: nextChanges };
            });
        });

        source.addEventListener("codex.error", (event) => {
            const payload = parsePayload(event as MessageEvent);
            if (!payload?.run_id) return;
            updateSession(payload.run_id, payload.session_id, (prev) => ({
                id: payload.session_id || prev?.id || payload.run_id,
                runIds: prev?.runIds ?? [],
                projectRoot: payload.project_root ?? prev?.projectRoot,
                sessionId: payload.session_id ?? prev?.sessionId,
                status: "error",
                startedAt: prev?.startedAt,
                completedAt: prev?.completedAt,
                success: prev?.success,
                exitCode: prev?.exitCode,
                errorType: payload.error_type ?? prev?.errorType,
                duration: prev?.duration,
                turnCount: prev?.turnCount ?? 1,
                thinkingStartTime: undefined,
                lines: prev?.lines ?? [],
                codeChanges: prev?.codeChanges ?? { filesChanged: 0, linesAdded: 0, linesRemoved: 0 },
            }));
        });

        source.addEventListener("codex.completed", (event) => {
            const payload = parsePayload(event as MessageEvent);
            if (!payload?.run_id) return;
            updateSession(payload.run_id, payload.session_id, (prev) => ({
                id: payload.session_id || prev?.id || payload.run_id,
                runIds: prev?.runIds ?? [],
                projectRoot: payload.project_root ?? prev?.projectRoot,
                sessionId: payload.session_id ?? prev?.sessionId,
                status: "completed",
                startedAt: prev?.startedAt,
                completedAt: payload.ts ?? prev?.completedAt,
                success: payload.success ?? prev?.success,
                exitCode: payload.exit_code ?? prev?.exitCode,
                errorType: payload.error_type ?? prev?.errorType,
                duration: (prev?.duration ?? 0) + (payload.duration_s ?? 0),
                turnCount: prev?.turnCount ?? 1,
                thinkingStartTime: undefined,
                lines: prev?.lines ?? [],
                codeChanges: prev?.codeChanges ?? { filesChanged: 0, linesAdded: 0, linesRemoved: 0 },
            }));
        });
    };

    useEffect(() => {
        connect();
        return () => {
            if (eventSourceRef.current) { eventSourceRef.current.close(); eventSourceRef.current = null; }
            if (reconnectTimerRef.current) { clearTimeout(reconnectTimerRef.current); reconnectTimerRef.current = null; }
        };
    }, [port]);

    const handlePortChange = (newPort: number) => {
        if (newPort >= 1 && newPort <= 65535) {
            setPort(newPort);
            invoke("set_settings", { port: newPort }).catch(() => { });
            setShowPortInput(false);
        }
    };

    return (
        <div className={`min-h-screen font-sans transition-colors duration-300 ${
            theme === "dark"
                ? "bg-slate-900 text-slate-100 selection:bg-purple-500/30"
                : `text-slate-800 selection:bg-orange-100 ${layoutMode === "grid" ? "bg-slate-50/50" : "bg-slate-50/30"}`
            }`}>
            {/* Background Decor */}
            <div className="fixed inset-0 pointer-events-none z-[-1] overflow-hidden">
                {theme === "dark" ? (
                    <>
                        <div className="absolute -left-[10%] -top-[10%] w-[50%] h-[50%] rounded-full bg-gradient-to-br from-purple-600/10 to-blue-600/10 blur-3xl opacity-60"></div>
                        <div className="absolute -right-[10%] top-[20%] w-[40%] h-[40%] rounded-full bg-gradient-to-bl from-indigo-600/10 to-cyan-600/10 blur-3xl opacity-60"></div>
                        <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAiIGhlaWdodD0iMjAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGNpcmNsZSBjeD0iMSIgY3k9IjEiIHI9IjEiIGZpbGw9IiM2NjYiIG9wYWNpdHk9IjAuMSIvPjwvc3ZnPg==')] opacity-20"></div>
                    </>
                ) : (
                    <>
                        <div className="absolute -left-[10%] -top-[10%] w-[50%] h-[50%] rounded-full bg-gradient-to-br from-orange-200/20 to-rose-200/20 blur-3xl opacity-60"></div>
                        <div className="absolute -right-[10%] top-[20%] w-[40%] h-[40%] rounded-full bg-gradient-to-bl from-blue-200/20 to-cyan-200/20 blur-3xl opacity-60"></div>
                        <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAiIGhlaWdodD0iMjAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGNpcmNsZSBjeD0iMSIgY3k9IjEiIHI9IjEiIGZpbGw9IiNjY2MiIG9wYWNpdHk9IjAuMiIvPjwvc3ZnPg==')] opacity-30"></div>
                    </>
                )}
            </div>

            <div className="flex w-full flex-col h-screen">
                {/* Navbar */}
                <header className="flex-none px-6 py-4 flex items-center justify-between z-50">
                    {/* Logo Area */}
                    <div className="flex items-center gap-4 group">
                        <div className={`relative w-10 h-10 rounded-xl flex items-center justify-center shadow-lg transition-transform group-hover:scale-105 group-hover:rotate-3 ${theme === "dark" ? "bg-slate-700 text-white" : "bg-slate-900 text-white"}`}>
                            <span className="font-bold text-sm tracking-tighter">CS</span>
                            <div className="absolute inset-0 rounded-xl bg-white/10 opacity-0 group-hover:opacity-100 transition-opacity"></div>
                        </div>
                        <div>
                            <h1 className={`text-lg font-bold tracking-tight transition-colors ${theme === "dark" ? "text-slate-100 group-hover:text-purple-400" : "text-slate-900 group-hover:text-orange-600"}`}>{t.title}</h1>
                            <div className="flex items-center gap-2">
                                <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] uppercase font-bold tracking-wider border ${connectionState === "connected" ? "bg-emerald-50 text-emerald-600 border-emerald-100" :
                                    connectionState === "connecting" ? "bg-amber-50 text-amber-600 border-amber-100" :
                                        "bg-rose-50 text-rose-600 border-rose-100"
                                    }`}>
                                    <span className={`w-1.5 h-1.5 rounded-full ${connectionState === "connected" ? "bg-emerald-500 animate-pulse" :
                                        connectionState === "connecting" ? "bg-amber-500 animate-pulse" :
                                            "bg-rose-500"
                                        }`}></span>
                                    {connectionState === "connected" ? t.connected : connectionState === "connecting" ? t.connecting : t.connectionError}
                                </div>
                                {showPortInput ? (
                                    <input
                                        type="number"
                                        value={port}
                                        onChange={(e) => handlePortChange(parseInt(e.target.value))}
                                        onBlur={() => setShowPortInput(false)}
                                        className="w-20 text-[10px] bg-slate-100 border border-slate-200 rounded px-1.5 py-0.5 outline-none focus:ring-1 focus:ring-orange-200 font-mono text-slate-600"
                                        autoFocus
                                    />
                                ) : (
                                    <button
                                        onClick={() => setShowPortInput(true)}
                                        className="text-[10px] text-slate-400 font-mono hover:text-orange-500 transition-colors border-b border-transparent hover:border-orange-200"
                                        title="Click to change port"
                                    >
                                        localhost:{port}
                                    </button>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Controls */}
                    <div className={`flex items-center gap-3 backdrop-blur-md p-1.5 rounded-2xl border shadow-sm ${theme === "dark" ? "bg-slate-800/60 border-slate-700/50" : "bg-white/60 border-white/50"}`}>
                        <div className={`flex rounded-xl p-1 gap-1 ${theme === "dark" ? "bg-slate-700/50" : "bg-slate-100/50"}`}>
                            <button
                                onClick={() => setLayoutMode("list")}
                                className={`p-2 rounded-lg transition-all ${layoutMode === "list" ? (theme === "dark" ? "bg-slate-600 text-slate-100 shadow-sm" : "bg-white text-slate-800 shadow-sm") : (theme === "dark" ? "text-slate-400 hover:text-slate-200" : "text-slate-400 hover:text-slate-600")}`}
                                title="List View"
                            >
                                <Icons.List />
                            </button>
                            <button
                                onClick={() => setLayoutMode("grid")}
                                className={`p-2 rounded-lg transition-all ${layoutMode === "grid" ? (theme === "dark" ? "bg-slate-600 text-slate-100 shadow-sm" : "bg-white text-slate-800 shadow-sm") : (theme === "dark" ? "text-slate-400 hover:text-slate-200" : "text-slate-400 hover:text-slate-600")}`}
                                title="Grid View"
                            >
                                <Icons.Grid />
                            </button>
                        </div>

                        <div className={`w-px h-6 mx-1 ${theme === "dark" ? "bg-slate-600" : "bg-slate-200"}`}></div>

                        <button
                            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl transition-colors text-[11px] font-semibold ${theme === "dark" ? "hover:bg-slate-700/80 text-slate-300" : "hover:bg-white/80 text-slate-600"}`}
                            title={theme === "dark" ? t.lightMode : t.darkMode}
                        >
                            {theme === "dark" ? <Icons.Sun /> : <Icons.Moon />}
                            {theme === "dark" ? t.lightMode : t.darkMode}
                        </button>

                        <button
                            onClick={() => setLang(lang === "zh" ? "en" : "zh")}
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl transition-colors text-[11px] font-semibold ${theme === "dark" ? "hover:bg-slate-700/80 text-slate-300" : "hover:bg-white/80 text-slate-600"}`}
                        >
                            <Icons.Globe />
                            {lang === "zh" ? "EN" : "中"}
                        </button>

                        {runs.length > 0 && (
                            <button
                                onClick={() => setRuns([])}
                                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl transition-colors text-[11px] font-semibold ${theme === "dark" ? "bg-orange-900/40 text-orange-300 hover:bg-orange-900/60 hover:text-orange-200" : "bg-orange-50 text-orange-700 hover:bg-orange-100 hover:text-orange-800"}`}
                            >
                                <Icons.Trash />
                                {t.clearRuns}
                            </button>
                        )}
                    </div>
                </header>

                {/* Content Area */}
                <main className="flex-1 overflow-y-auto px-6 pb-8 custom-scrollbar">
                    {runs.length === 0 ? (
                        <div className="h-full flex flex-col items-center justify-center -mt-20">
                            <div className="relative group">
                                <div className={`absolute inset-0 rounded-full blur-2xl opacity-20 group-hover:opacity-40 transition-opacity duration-1000 ${theme === "dark" ? "bg-gradient-to-tr from-purple-600 to-blue-600" : "bg-gradient-to-tr from-orange-200 to-rose-200"}`}></div>
                                <div className={`relative w-24 h-24 rounded-3xl border shadow-[0_20px_40px_-10px_rgba(0,0,0,0.05)] flex items-center justify-center mb-6 ${theme === "dark" ? "bg-slate-800 border-slate-700" : "bg-white border-slate-100"}`}>
                                    <svg className={`w-10 h-10 ${theme === "dark" ? "text-slate-500" : "text-slate-300"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M13 10V3L4 14h7v7l9-11h-7z" />
                                    </svg>
                                </div>
                            </div>
                            <h3 className={`text-lg font-semibold mb-2 ${theme === "dark" ? "text-slate-200" : "text-slate-800"}`}>{t.waitingEvents}</h3>
                            <p className={`text-sm max-w-sm text-center leading-relaxed ${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>
                                Waiting for Codex execution events from <br />
                                <code className={`px-2 py-0.5 rounded font-mono text-xs mt-1 inline-block ${theme === "dark" ? "bg-slate-800 text-slate-300" : "bg-slate-100 text-slate-600"}`}>{sseUrl}</code>
                            </p>
                        </div>
                    ) : (
                        <div className={`
               ${layoutMode === "grid"
                   ? "grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-4"
                   : "flex flex-col gap-6 w-full"}
               mx-auto
             `}>
                            {runs.map((run) => (
                                <RunCard
                                    key={run.id}
                                    run={run}
                                    lang={lang}
                                    t={t}
                                    theme={theme}
                                    sessions={sessions}
                                    isCompact={layoutMode === "grid"}
                                />
                            ))}
                        </div>
                    )}
                </main>
            </div>

            <style>{`
        .custom-scrollbar::-webkit-scrollbar { width: 6px; height: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #94a3b8; }

        /* Shimmer animation for thinking (inspired by codex TUI) */
        @keyframes shimmer {
          0% { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }
        .thinking-shimmer {
          background: linear-gradient(
            90deg,
            rgba(168, 85, 247, 0.4) 0%,
            rgba(192, 132, 252, 0.7) 25%,
            rgba(168, 85, 247, 0.4) 50%,
            rgba(192, 132, 252, 0.7) 75%,
            rgba(168, 85, 247, 0.4) 100%
          );
          background-size: 200% 100%;
          -webkit-background-clip: text;
          background-clip: text;
          -webkit-text-fill-color: transparent;
          animation: shimmer 2s linear infinite;
        }
      `}</style>
        </div>
    );
}
