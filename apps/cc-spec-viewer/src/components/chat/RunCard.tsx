// components/chat/RunCard.tsx - 执行任务卡片组件

import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import Ansi from "ansi-to-react";
import { Icons } from "../icons/Icons";
import { ThinkingTimer } from "./ThinkingTimer";
import { RenderContent } from "./RenderContent";
import { formatDuration, formatTimestamp } from "../../utils/format";
import type { RunState, Language, Theme } from "../../types/viewer";
import { translations, BG_IMAGES } from "../../types/viewer";

interface RunCardProps {
    run: RunState;
    lang: Language;
    t: typeof translations["zh"];
    theme: Theme;
    sessions: Record<string, any>;
    isCompact?: boolean;
}

export function RunCard({ run, lang, t, theme, sessions, isCompact = false }: RunCardProps) {
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
    const sessionSummary = typeof sessionInfo?.task_summary === "string" ? sessionInfo.task_summary.trim() : "";
    const summaryPreview = sessionSummary.length > 50 ? `${sessionSummary.slice(0, 50)}...` : sessionSummary;
    const sessionElapsed = sessionInfo?.elapsed_s !== undefined ? Number(sessionInfo.elapsed_s) : undefined;
    const canStop = isRunning && Boolean(run.projectRoot) && Boolean(run.sessionId);
    const stopLabel = isStopping ? t.stopping : t.stop;
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
            relative rounded-xl overflow-hidden shadow-lg flex flex-col
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
                            {isRunning && (
                                <span className="relative flex h-1.5 w-1.5">
                                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                                    <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
                                </span>
                            )}
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
                            className={`transition-colors p-1 rounded ${theme === "dark" ? "text-rose-400 hover:text-rose-300 hover:bg-rose-500/10" : "text-rose-500 hover:text-rose-600 hover:bg-rose-100"} ${!canStop || isStopping ? "opacity-50 cursor-not-allowed hover:bg-transparent" : ""}`}
                            title={stopLabel}
                            aria-label={stopLabel}
                        >
                            <Icons.Stop />
                        </button>
                    )}
                    {shortId && (
                        <button
                            onClick={handleCopyId}
                            className={`font-mono flex items-center gap-1 px-1.5 py-0.5 rounded transition-all ${idCopied ? "text-emerald-400 bg-emerald-500/10" : theme === "dark" ? "text-slate-500 hover:text-slate-300 hover:bg-slate-700/50" : "text-slate-500 hover:text-slate-700 hover:bg-slate-200/50"} ${isCompact ? "text-[9px]" : "text-[10px]"}`}
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
                    relative flex-1 overflow-auto font-['JetBrains_Mono'] leading-relaxed custom-scrollbar shadow-inner
                    ${theme === "dark" ? "bg-[#1a1b2e]" : "bg-gradient-to-br from-blue-50/80 to-purple-50/80"}
                    ${isCompact ? "max-h-[28vh] p-3 text-[11px]" : "max-h-[60vh] p-4 text-[12px]"}
                `}
            >
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
                                switch (line.type) {
                                    case "user":
                                        return (
                                            <div
                                                key={idx}
                                                className={`mt-5 mb-4 flex items-start gap-2 rounded-r-lg border-l-[5px] px-5 py-4 ${theme === "dark" ? "bg-indigo-500/20 border-indigo-300" : "bg-indigo-100 border-indigo-400"}`}
                                            >
                                                <span className={`font-bold ${theme === "dark" ? "text-indigo-300" : "text-indigo-600"}`}>›</span>
                                                <span className={`font-medium leading-relaxed ${theme === "dark" ? "text-indigo-100" : "text-indigo-900"}`}>
                                                    <RenderContent content={line.content} type={line.type} theme={theme} />
                                                </span>
                                            </div>
                                        );
                                    case "agent":
                                        return (
                                            <div key={idx} className={theme === "dark" ? "text-slate-200" : "text-slate-800"}>
                                                <span className={`mr-1 ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>•</span>
                                                <RenderContent content={line.content} type={line.type} theme={theme} />
                                            </div>
                                        );
                                    case "tool_start":
                                        return (
                                            <div key={idx} className="mt-2 flex items-center gap-1.5">
                                                <span className={`${theme === "dark" ? "text-amber-400" : "text-amber-600"} ${isRunning ? "animate-pulse" : ""}`}>•</span>
                                                <span className={`font-medium ${theme === "dark" ? "text-slate-400" : "text-slate-600"}`}>Running</span>
                                                <span className={`font-mono text-[11px] ${theme === "dark" ? "text-cyan-400" : "text-cyan-700"}`}>{line.content}</span>
                                            </div>
                                        );
                                    case "tool_end":
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
                                        return (
                                            <div key={idx} className={`text-[11px] pl-4 opacity-70 ${theme === "dark" ? "text-slate-500" : "text-slate-600"}`}>
                                                <span className={`mr-1 ${theme === "dark" ? "text-slate-600" : "text-slate-500"}`}>└</span>
                                                <Ansi>{line.content}</Ansi>
                                            </div>
                                        );
                                    case "file_op":
                                        return (
                                            <div key={idx} className="flex items-center gap-1.5 text-[11px]">
                                                <span className={`font-bold ${theme === "dark" ? "text-emerald-400" : "text-emerald-600"}`}>✓</span>
                                                <span className={theme === "dark" ? "text-slate-400" : "text-slate-600"}>{line.content}</span>
                                            </div>
                                        );
                                    case "thinking":
                                        return (
                                            <div key={idx} className="pl-3 border-l border-purple-500/30 my-1">
                                                <span className={`mr-1 ${theme === "dark" ? "text-slate-600" : "text-slate-500"}`}>•</span>
                                                <span className={`italic text-[11px] ${isRunning ? "thinking-shimmer" : "text-purple-400/60"}`}>{line.content}</span>
                                            </div>
                                        );
                                    case "error":
                                        return (
                                            <div key={idx} className={`flex items-start gap-1.5 px-2 py-1 rounded my-1 ${theme === "dark" ? "bg-rose-500/10" : "bg-rose-100"}`}>
                                                <span className={`font-bold ${theme === "dark" ? "text-rose-400" : "text-rose-600"}`}>✗</span>
                                                <span className={`text-[11px] ${theme === "dark" ? "text-rose-300" : "text-rose-700"}`}>{line.content}</span>
                                            </div>
                                        );
                                    case "info":
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
