import { useEffect, useRef, useState, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import Ansi from "ansi-to-react";

const MAX_LINES = 500;
const DEFAULT_PORT = 38888;

type LayoutMode = "list" | "grid";
type RunStatus = "running" | "completed" | "error";

type StreamLine = {
    type: "text" | "tool" | "result" | "error" | "info" | "user" | "thinking" | "raw";
    content: string;
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

// Prompt-style parsing
const parseStreamLine = (raw: string): StreamLine | null => {
    try {
        const obj = JSON.parse(raw);
        const type = obj.type;

        if (type === "item.started") {
            const item = obj.item;
            if (item?.type === "command_execution") {
                const cmd = item.command || "";
                return { type: "tool", content: `➜ ${cmd}` };
            }
            if (item?.type === "file_edit") {
                const file = item.file_path || item.path || "";
                return { type: "tool", content: `➜ Editing ${file}` };
            }
        }
        if (type === "item.completed") {
            const item = obj.item;
            if (item?.type === "reasoning" && item?.text) return { type: "thinking", content: item.text };
            if (item?.type === "agent_message" && item?.text) return { type: "text", content: item.text };
            if (item?.type === "command_execution") {
                const cmd = item.command || "";
                const output = item.aggregated_output || "";
                const exitCode = item.exit_code;
                const status = exitCode === 0 ? "✓" : "✗";

                const isReadCmd = /Get-Content|cat |head |tail |less |more /i.test(cmd);
                if (isReadCmd && exitCode === 0) {
                    const lines = output.split('\n').length;
                    const shortCmd = cmd.length > 60 ? cmd.slice(0, 60) + "..." : cmd;
                    return { type: "result", content: `${status} Read ${lines} lines from ${shortCmd}` };
                }
                const maxLen = 800;
                const preview = output.length > maxLen ? output.slice(0, maxLen) + "\n... (truncated)" : output;
                return { type: exitCode === 0 ? "result" : "error", content: preview || "(no output)" };
            }
            if (item?.type === "file_edit" || item?.type === "file_change") {
                if (item.changes && Array.isArray(item.changes)) {
                    const parts = item.changes.map((c: { path?: string; kind?: string }) => {
                        const file = c.path?.split(/[/\\]/).slice(-2).join('/') || "file";
                        const kind = c.kind || "update";
                        return `• ${kind}: ${file}`;
                    });
                    return { type: "result", content: `✓ Changes applied:\n${parts.join('\n')}` };
                }
                const file = item.file_path || item.path || "";
                const shortFile = file.split(/[/\\]/).slice(-2).join('/');
                return { type: "result", content: `✓ Edited ${shortFile}` };
            }
            if (item?.type === "file_read") {
                const file = item.file_path || item.path || "";
                const shortFile = file.split(/[/\\]/).slice(-2).join('/');
                return { type: "result", content: `✓ Read ${shortFile}` };
            }
        }
        if (type === "error") {
            const msg = obj.message || obj.error || "unknown error";
            return { type: "error", content: `Error: ${msg}` };
        }
        return null;
    } catch {
        if (raw.trim()) return { type: "text", content: raw };
        return null;
    }
};

type ConnectionState = "connecting" | "connected" | "error";
type Language = "zh" | "en";
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
        <span className="text-purple-400 font-mono text-[10px] bg-purple-500/10 px-2 py-0.5 rounded-full border border-purple-500/20 animate-pulse flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-purple-400 shadow-[0_0_8px_rgba(192,132,252,0.6)]"></span>
            thinking <span className="tabular-nums">{elapsed}s</span>
        </span>
    );
}

function RenderContent({ content, type }: { content: string; type: StreamLine["type"] }) {
    if (type !== "text") return <Ansi>{content}</Ansi>;
    const blocks = parseCodeBlocks(content);
    return (
        <>
            {blocks.map((block, i) =>
                block.type === "code" ? (
                    <div key={i} className="my-2 border border-slate-700 bg-[#0f1419] p-2 text-xs rounded-sm">
                        <SyntaxHighlighter
                            language={block.lang || "text"}
                            style={oneDark}
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
    Terminal: () => <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>,
    Grid: () => <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" /></svg>,
    List: () => <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" /></svg>,
    Trash: () => <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>,
    Globe: () => <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129" /></svg>,
    Copy: () => <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>,
    Check: () => <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>,
};

// NEW: Enhanced RunCard with Background Image support
function RunCard({
    run,
    lang,
    t,
    isCompact = false,
}: {
    run: RunState;
    lang: Language;
    t: typeof translations["zh"];
    isCompact?: boolean;
}) {
    const scrollRef = useRef<HTMLDivElement>(null);
    const [copied, setCopied] = useState(false);
    const isRunning = run.status === "running";
    const isFailed = run.success === false || run.status === "error";

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

    const statusColor = isRunning
        ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/30"
        : isFailed
            ? "text-rose-400 bg-rose-500/10 border-rose-500/30"
            : "text-slate-400 bg-slate-500/10 border-slate-500/30";

    return (
        <div className={`
      relative rounded-xl overflow-hidden bg-[#1e2030] border border-slate-700/60 shadow-lg 
      flex flex-col
      ${isRunning ? "ring-1 ring-emerald-500/30 ring-offset-2 ring-offset-[#1e2030]" : "hover:border-slate-500/50 hover:shadow-xl"}
      transition-all duration-300 animate-in fade-in slide-in-from-bottom-2
    `}>
            {/* Header - Dark Themed now to match terminal */}
            <div className="flex-none px-4 py-3 bg-[#181926] border-b border-slate-800 flex items-center justify-between select-none">
                <div className="flex items-center gap-3">
                    <div className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border flex items-center gap-1.5 ${statusColor}`}>
                        {isRunning && <span className="relative flex h-1.5 w-1.5">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
                        </span>}
                        {isRunning ? t.statusLive : isFailed ? t.statusFailed : t.statusDone}
                    </div>

                    {isRunning && <ThinkingTimer startTime={run.thinkingStartTime} />}

                    {run.turnCount > 1 && (
                        <span className="text-[10px] font-mono text-orange-400 bg-orange-400/10 border border-orange-400/20 px-1.5 rounded">
                            #{run.turnCount}
                        </span>
                    )}

                    {run.projectRoot && (
                        <span className="hidden sm:inline-block text-[10px] text-slate-500 font-mono">
                            {run.projectRoot.split(/[/\\]/).pop()}
                        </span>
                    )}
                </div>

                <div className="flex items-center gap-2">
                    <button
                        onClick={handleCopy}
                        className="text-slate-500 hover:text-white transition-colors p-1"
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
          relative flex-1 overflow-auto bg-[#1a1b26] p-4 font-['JetBrains_Mono'] text-[12px] leading-relaxed custom-scrollbar
          shadow-inner
          ${isCompact ? "h-[35vh]" : "h-[60vh]"}
        `}
            >
                {/* Background Images Overlay */}
                <div className="absolute inset-0 z-0 opacity-[0.05] pointer-events-none bg-[url('/bg.png')] bg-cover bg-center bg-no-repeat"></div>
                <div className="absolute inset-0 z-0 opacity-[0.05] pointer-events-none bg-[url('/bg.gif')] bg-cover bg-center bg-no-repeat"></div>

                <div className="relative z-10 w-full min-h-full">
                    {run.lines.length === 0 ? (
                        <div className="h-full flex flex-col items-center justify-center opacity-30 gap-2">
                            <Icons.Terminal />
                            <span className="text-[10px] font-mono">{t.noOutput}</span>
                        </div>
                    ) : (
                        <div className="flex flex-col gap-1">
                            {run.lines.map((line, idx) => {
                                let className = "break-all whitespace-pre-wrap transition-opacity duration-300";
                                let prefix = null;

                                switch (line.type) {
                                    case "tool": className += " text-cyan-400 font-bold mt-2 mb-1"; break;
                                    case "result": className += " text-slate-300 opacity-90"; break;
                                    case "error": className += " text-rose-400 bg-rose-500/10 px-2 py-1 border-l-2 border-rose-500 my-1"; break;
                                    case "info": className += " text-slate-500 text-[10px] text-center my-4 opacity-50 tracking-wider"; break;
                                    case "user": className += " text-indigo-300 font-bold mt-4 mb-2 pb-1 border-b border-indigo-500/20"; prefix = "👤 "; break;
                                    case "thinking": className += " text-purple-400/70 italic pl-3 border-l border-purple-500/20 my-1"; break;
                                    case "raw": className += " text-slate-600"; break;
                                    default: className += " text-slate-300";
                                }

                                return (
                                    <div key={idx} className={className}>
                                        {prefix}{line.type === "tool" ? line.content : <RenderContent content={line.content} type={line.type} />}
                                    </div>
                                );
                            })}

                            {isRunning && (
                                <div className="mt-2 text-emerald-500/50 animate-pulse pl-1">_</div>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {/* Footer Status */}
            <div className="flex-none bg-[#181926] border-t border-slate-800/80 px-4 py-1.5 flex items-center justify-between text-[10px] font-medium text-slate-500 select-none">
                <div className="flex items-center gap-2">
                    <Icons.Clock />
                    <span className="font-mono">{formatTimestamp(run.startedAt, lang)}</span>
                </div>
                <div className="flex items-center gap-4">
                    {(run.duration !== undefined || isRunning) && (
                        <span className={`font-mono ${isRunning ? "text-emerald-500" : ""}`}>{formatDuration(run.duration)}</span>
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
    const [port, setPort] = useState(DEFAULT_PORT);
    const [showPortInput, setShowPortInput] = useState(false);
    const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");
    const [runs, setRuns] = useState<RunState[]>([]);
    const [layoutMode, setLayoutMode] = useState<LayoutMode>("list");
    const eventSourceRef = useRef<EventSource | null>(null);
    const reconnectTimerRef = useRef<number | null>(null);

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
                };
            });
        });

        source.addEventListener("codex.stream", (event) => {
            const payload = parsePayload(event as MessageEvent);
            if (!payload?.run_id) return;
            const raw = typeof payload.text === "string" ? payload.text : "";
            if (!raw) return;
            const parsed = parseStreamLine(raw);
            if (!parsed) return;
            updateSession(payload.run_id, payload.session_id, (prev) => {
                const base: RunState = prev ?? {
                    id: payload.session_id || payload.run_id,
                    runIds: [],
                    status: "running",
                    turnCount: 1,
                    lines: [],
                };
                let nextLines = [...base.lines];
                if (parsed.type === "text" && nextLines.length > 0) {
                    const last = nextLines[nextLines.length - 1];
                    if (last.type === "text") {
                        nextLines[nextLines.length - 1] = { type: "text", content: last.content + parsed.content };
                    } else {
                        nextLines.push(parsed);
                    }
                } else {
                    nextLines.push(parsed);
                }
                if (nextLines.length > MAX_LINES) nextLines.splice(0, nextLines.length - MAX_LINES);
                return { ...base, status: "running", projectRoot: payload.project_root ?? base.projectRoot, sessionId: payload.session_id ?? base.sessionId, lines: nextLines };
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
        <div className={`min-h-screen text-slate-800 font-sans selection:bg-orange-100 ${layoutMode === "grid" ? "bg-slate-50/50" : "bg-slate-50/30"
            }`}>
            {/* Background Decor */}
            <div className="fixed inset-0 pointer-events-none z-[-1] overflow-hidden">
                <div className="absolute -left-[10%] -top-[10%] w-[50%] h-[50%] rounded-full bg-gradient-to-br from-orange-200/20 to-rose-200/20 blur-3xl opacity-60"></div>
                <div className="absolute -right-[10%] top-[20%] w-[40%] h-[40%] rounded-full bg-gradient-to-bl from-blue-200/20 to-cyan-200/20 blur-3xl opacity-60"></div>
                <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAiIGhlaWdodD0iMjAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGNpcmNsZSBjeD0iMSIgY3k9IjEiIHI9IjEiIGZpbGw9IiNjY2MiIG9wYWNpdHk9IjAuMiIvPjwvc3ZnPg==')] opacity-30"></div>
            </div>

            <div className="flex w-full flex-col h-screen">
                {/* Navbar */}
                <header className="flex-none px-6 py-4 flex items-center justify-between z-50">
                    {/* Logo Area */}
                    <div className="flex items-center gap-4 group">
                        <div className="relative w-10 h-10 rounded-xl bg-slate-900 flex items-center justify-center text-white shadow-lg transition-transform group-hover:scale-105 group-hover:rotate-3">
                            <span className="font-bold text-sm tracking-tighter">CS</span>
                            <div className="absolute inset-0 rounded-xl bg-white/10 opacity-0 group-hover:opacity-100 transition-opacity"></div>
                        </div>
                        <div>
                            <h1 className="text-lg font-bold tracking-tight text-slate-900 group-hover:text-orange-600 transition-colors">{t.title}</h1>
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
                    <div className="flex items-center gap-3 bg-white/60 backdrop-blur-md p-1.5 rounded-2xl border border-white/50 shadow-sm">
                        <div className="flex bg-slate-100/50 rounded-xl p-1 gap-1">
                            <button
                                onClick={() => setLayoutMode("list")}
                                className={`p-2 rounded-lg transition-all ${layoutMode === "list" ? "bg-white text-slate-800 shadow-sm" : "text-slate-400 hover:text-slate-600"}`}
                                title="List View"
                            >
                                <Icons.List />
                            </button>
                            <button
                                onClick={() => setLayoutMode("grid")}
                                className={`p-2 rounded-lg transition-all ${layoutMode === "grid" ? "bg-white text-slate-800 shadow-sm" : "text-slate-400 hover:text-slate-600"}`}
                                title="Grid View"
                            >
                                <Icons.Grid />
                            </button>
                        </div>

                        <div className="w-px h-6 bg-slate-200 mx-1"></div>

                        <button
                            onClick={() => setLang(lang === "zh" ? "en" : "zh")}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl hover:bg-white/80 transition-colors text-[11px] font-semibold text-slate-600"
                        >
                            <Icons.Globe />
                            {lang === "zh" ? "EN" : "中"}
                        </button>

                        {runs.length > 0 && (
                            <button
                                onClick={() => setRuns([])}
                                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-orange-50 text-orange-700 hover:bg-orange-100 hover:text-orange-800 transition-colors text-[11px] font-semibold"
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
                                <div className="absolute inset-0 bg-gradient-to-tr from-orange-200 to-rose-200 rounded-full blur-2xl opacity-20 group-hover:opacity-40 transition-opacity duration-1000"></div>
                                <div className="relative w-24 h-24 rounded-3xl bg-white border border-slate-100 shadow-[0_20px_40px_-10px_rgba(0,0,0,0.05)] flex items-center justify-center mb-6">
                                    <svg className="w-10 h-10 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M13 10V3L4 14h7v7l9-11h-7z" />
                                    </svg>
                                </div>
                            </div>
                            <h3 className="text-lg font-semibold text-slate-800 mb-2">{t.waitingEvents}</h3>
                            <p className="text-sm text-slate-500 max-w-sm text-center leading-relaxed">
                                Waiting for Codex execution events from <br />
                                <code className="bg-slate-100 px-2 py-0.5 rounded text-slate-600 font-mono text-xs mt-1 inline-block">{sseUrl}</code>
                            </p>
                        </div>
                    ) : (
                        <div className={`
               ${layoutMode === "grid" ? "grid grid-cols-1 xl:grid-cols-2 gap-6" : "flex flex-col gap-6"}
               max-w-[1600px] mx-auto
             `}>
                            {runs.map((run) => (
                                <RunCard key={run.id} run={run} lang={lang} t={t} isCompact={layoutMode === "grid"} />
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
      `}</style>
        </div>
    );
}
