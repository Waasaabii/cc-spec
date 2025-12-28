// components/index/IndexPrompt.tsx - 索引初始化提示组件

import { useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type { Theme, translations } from "../../types/viewer";

interface IndexPromptProps {
    projectPath: string;
    theme: Theme;
    t: typeof translations["zh"];
    onClose: () => void;
}

export function IndexPrompt({ projectPath, theme, t, onClose }: IndexPromptProps) {
    const [isInitializing, setIsInitializing] = useState(false);
    const [initDone, setInitDone] = useState(false);
    const [initSuccess, setInitSuccess] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [selectedLevels, setSelectedLevels] = useState<string[]>(["l1", "l2"]);
    const [runId, setRunId] = useState<string | null>(null);
    const [logs, setLogs] = useState<Array<{ stage: string; stream: string; line: string }>>([]);
    const allLogsRef = useRef<Array<{ stage: string; stream: string; line: string }>>([]);
    const logRef = useRef<HTMLDivElement>(null);
    const unlistenersRef = useRef<UnlistenFn[]>([]);
    const runIdRef = useRef<string | null>(null);

    const stages = useMemo(() => ([
        { id: "bootstrap", label: "Bootstrap（生成 Commands/Standards）" },
        { id: "index", label: "初始化多级索引（PROJECT_INDEX / FOLDER_INDEX）" },
        { id: "finalize", label: "写入状态（status.json）" },
    ]), []);

    type StageState = "pending" | "running" | "completed" | "failed";
    const [stageState, setStageState] = useState<Record<string, { state: StageState; command?: string; exit_code?: number; error?: string }>>(() => {
        const init: Record<string, { state: StageState; command?: string; exit_code?: number; error?: string }> = {};
        for (const s of stages) init[s.id] = { state: "pending" };
        return init;
    });

    const resetProgress = () => {
        setLogs([]);
        allLogsRef.current = [];
        setRunId(null);
        runIdRef.current = null;
        setStageState(() => {
            const init: Record<string, { state: StageState; command?: string; exit_code?: number; error?: string }> = {};
            for (const s of stages) init[s.id] = { state: "pending" };
            return init;
        });
    };

    const cleanupListeners = () => {
        for (const unlisten of unlistenersRef.current) unlisten();
        unlistenersRef.current = [];
    };

    useEffect(() => {
        return () => cleanupListeners();
    }, []);

    useEffect(() => {
        // 自动滚动到最新日志
        if (!logRef.current) return;
        logRef.current.scrollTop = logRef.current.scrollHeight;
    }, [logs.length]);

    const handleInit = async () => {
        setIsInitializing(true);
        setInitDone(false);
        setInitSuccess(false);
        setError(null);
        resetProgress();

        cleanupListeners();
        try {
            // index:init:started
            unlistenersRef.current.push(
                await listen<{ run_id: string; project_path: string; levels: string[] }>("index:init:started", (event) => {
                    if (event.payload.project_path !== projectPath) return;
                    runIdRef.current = event.payload.run_id;
                    setRunId(event.payload.run_id);
                })
            );

            // index:init:stage
            unlistenersRef.current.push(
                await listen<{ run_id: string; stage: string; state: string; command?: string; exit_code?: number; error?: string }>("index:init:stage", (event) => {
                    if (!runIdRef.current) return;
                    if (event.payload.run_id !== runIdRef.current) return;
                    const stage = event.payload.stage;
                    const state: StageState =
                        event.payload.state === "started" ? "running" :
                            event.payload.state === "completed" ? "completed" :
                                "failed";
                    setStageState((prev) => ({
                        ...prev,
                        [stage]: {
                            state,
                            command: event.payload.command ?? prev[stage]?.command,
                            exit_code: event.payload.exit_code ?? prev[stage]?.exit_code,
                            error: event.payload.error ?? prev[stage]?.error,
                        },
                    }));
                })
            );

            // index:init:log
            unlistenersRef.current.push(
                await listen<{ run_id: string; stage: string; stream: string; line: string }>("index:init:log", (event) => {
                    if (!runIdRef.current) return;
                    if (event.payload.run_id !== runIdRef.current) return;
                    const entry = { stage: event.payload.stage, stream: event.payload.stream, line: event.payload.line };
                    allLogsRef.current.push(entry);
                    setLogs(() => {
                        // UI 为性能只渲染最后 N 行，但保留全量日志用于复制/排查
                        const limit = 2000;
                        const start = Math.max(0, allLogsRef.current.length - limit);
                        return allLogsRef.current.slice(start);
                    });
                })
            );

            // index:init:completed
            unlistenersRef.current.push(
                await listen<{ run_id: string; project_path: string; success: boolean; stage?: string; stdout?: string; stderr?: string }>("index:init:completed", (event) => {
                    if (!runIdRef.current) return;
                    if (event.payload.run_id !== runIdRef.current) return;
                    setInitDone(true);
                    setInitSuccess(Boolean(event.payload.success));
                    setIsInitializing(false);
                })
            );

            await invoke("init_index", {
                projectPath: projectPath,
                levels: selectedLevels,
            });

            setInitDone(true);
            setInitSuccess(true);
        } catch (err) {
            setInitDone(true);
            setInitSuccess(false);
            setError(String(err));
        } finally {
            setIsInitializing(false);
        }
    };

    const toggleLevel = (level: string) => {
        setSelectedLevels((prev) =>
            prev.includes(level) ? prev.filter((l) => l !== level) : [...prev, level]
        );
    };

    const levels = [
        { id: "l1", name: t.indexL1Name, desc: t.indexL1Desc },
        { id: "l2", name: t.indexL2Name, desc: t.indexL2Desc },
        { id: "l3", name: t.indexL3Name, desc: t.indexL3Desc },
    ];

    const stageBadgeClass = (state: StageState) => {
        switch (state) {
            case "running":
                return theme === "dark" ? "bg-amber-500/15 text-amber-300 border-amber-500/30" : "bg-amber-50 text-amber-700 border-amber-200";
            case "completed":
                return theme === "dark" ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" : "bg-emerald-50 text-emerald-700 border-emerald-200";
            case "failed":
                return theme === "dark" ? "bg-rose-500/15 text-rose-300 border-rose-500/30" : "bg-rose-50 text-rose-700 border-rose-200";
            default:
                return theme === "dark" ? "bg-slate-700/40 text-slate-300 border-slate-600" : "bg-slate-50 text-slate-600 border-slate-200";
        }
    };

    const stageBadgeText = (state: StageState) => {
        switch (state) {
            case "running": return "进行中";
            case "completed": return "完成";
            case "failed": return "失败";
            default: return "等待";
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
            <div
                className={`w-full max-w-md rounded-xl shadow-2xl ${theme === "dark" ? "bg-slate-800 text-slate-100" : "bg-white text-slate-800"
                    }`}
            >
                {/* Header */}
                <div className={`px-6 py-4 border-b ${theme === "dark" ? "border-slate-700" : "border-slate-200"}`}>
                    <h2 className="text-lg font-semibold flex items-center gap-2">
                        <svg className="w-5 h-5 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                        {t.indexPromptTitle}
                    </h2>
                    <p className={`text-sm mt-1 ${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>
                        {t.indexPromptSubtitle}
                    </p>
                </div>

                {/* Content */}
                <div className="px-6 py-4">
                    <p className={`text-sm mb-4 ${theme === "dark" ? "text-slate-300" : "text-slate-600"}`}>
                        {t.indexPromptDesc}
                    </p>

                    <div className="space-y-2">
                        {levels.map((level) => (
                            <label
                                key={level.id}
                                className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-colors ${selectedLevels.includes(level.id)
                                    ? theme === "dark"
                                        ? "bg-blue-500/20 border border-blue-500/30"
                                        : "bg-blue-50 border border-blue-200"
                                    : theme === "dark"
                                        ? "bg-slate-700/50 border border-slate-600 hover:bg-slate-700"
                                        : "bg-slate-50 border border-slate-200 hover:bg-slate-100"
                                    }`}
                            >
                                <input
                                    type="checkbox"
                                    checked={selectedLevels.includes(level.id)}
                                    onChange={() => toggleLevel(level.id)}
                                    disabled={isInitializing}
                                    className="w-4 h-4 rounded border-slate-400"
                                />
                                <div className="flex-1">
                                    <div className="font-medium text-sm">{level.name}</div>
                                    <div className={`text-xs ${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>
                                        {level.desc}
                                    </div>
                                </div>
                            </label>
                        ))}
                    </div>

                    {(isInitializing || logs.length > 0 || initDone) && (
                        <div className="mt-5">
                            <div className={`text-xs font-semibold ${theme === "dark" ? "text-slate-300" : "text-slate-600"}`}>
                                进度 {runId ? <span className="font-mono text-[10px] opacity-70">({runId.slice(0, 8)})</span> : null}
                            </div>

                            <div className="mt-2 space-y-2">
                                {stages.map((s) => {
                                    const info = stageState[s.id] ?? { state: "pending" as StageState };
                                    return (
                                        <div key={s.id} className={`rounded-lg border p-3 ${theme === "dark" ? "border-slate-700 bg-slate-900/40" : "border-slate-200 bg-slate-50"}`}>
                                            <div className="flex items-start justify-between gap-3">
                                                <div className="min-w-0 flex-1">
                                                    <div className="text-sm font-semibold truncate">{s.label}</div>
                                                    {info.command && (
                                                        <div className={`mt-1 text-[10px] font-mono break-all ${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>
                                                            {info.command}
                                                        </div>
                                                    )}
                                                    {typeof info.exit_code === "number" && (
                                                        <div className={`mt-1 text-[10px] font-mono ${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>
                                                            exit={info.exit_code}
                                                        </div>
                                                    )}
                                                </div>
                                                <div className={`flex items-center gap-2 text-[10px] px-2 py-0.5 rounded-full border ${stageBadgeClass(info.state)}`}>
                                                    {info.state === "running" && (
                                                        <span className="inline-block w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin" aria-hidden />
                                                    )}
                                                    {stageBadgeText(info.state)}
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>

                            <div className="mt-4">
                                <div className={`text-xs font-semibold ${theme === "dark" ? "text-slate-300" : "text-slate-600"}`}>输出（stdout/stderr）</div>
                                {allLogsRef.current.length > logs.length && (
                                    <div className={`mt-1 text-[10px] ${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>
                                        为性能仅显示最后 {logs.length} 行（共 {allLogsRef.current.length} 行），复制按钮会复制全部日志。
                                    </div>
                                )}
                                <div
                                    ref={logRef}
                                    className={`mt-2 max-h-56 overflow-auto rounded-lg border p-3 font-mono text-[10px] whitespace-pre-wrap break-words ${theme === "dark"
                                        ? "bg-slate-900/50 border-slate-700 text-slate-200"
                                        : "bg-white border-slate-200 text-slate-800"
                                        }`}
                                >
                                    {logs.length === 0 ? (
                                        <div className={`opacity-70 ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>（暂无输出）</div>
                                    ) : (
                                        logs.map((l, idx) => (
                                            <div key={idx} className={l.stream === "stderr" ? (theme === "dark" ? "text-rose-300" : "text-rose-700") : l.stream === "system" ? (theme === "dark" ? "text-amber-300" : "text-amber-700") : ""}>
                                                <span className={`mr-2 opacity-70`}>[{l.stage}:{l.stream}]</span>
                                                {l.line}
                                            </div>
                                        ))
                                    )}
                                </div>
                                {logs.length > 0 && (
                                    <div className="mt-2 flex justify-end">
                                        <button
                                            onClick={() => {
                                                const text = allLogsRef.current.map((l) => `[${l.stage}:${l.stream}] ${l.line}`).join("\n");
                                                navigator.clipboard.writeText(text);
                                            }}
                                            className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${theme === "dark" ? "border-slate-700 text-slate-300 hover:bg-slate-700/50" : "border-slate-200 text-slate-600 hover:bg-slate-100"}`}
                                        >
                                            {t.copy || "复制"}全部日志
                                        </button>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {error && (
                        <div className="mt-4 relative">
                            <div className="p-3 rounded-lg bg-rose-500/10 text-rose-400 text-sm max-h-40 overflow-auto break-all whitespace-pre-wrap pr-10">
                                {error}
                            </div>
                            <button
                                onClick={() => {
                                    navigator.clipboard.writeText(error);
                                }}
                                className={`absolute top-2 right-2 p-1.5 rounded-md transition-colors ${theme === "dark"
                                        ? "hover:bg-slate-700 text-slate-400 hover:text-slate-200"
                                        : "hover:bg-slate-200 text-slate-500 hover:text-slate-700"
                                    }`}
                                title={t.copy || "复制"}
                            >
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                                </svg>
                            </button>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className={`px-6 py-4 border-t flex items-center justify-end ${theme === "dark" ? "border-slate-700" : "border-slate-200"}`}>
                    {initDone && initSuccess ? (
                        <button
                            onClick={onClose}
                            className="px-4 py-2 rounded-lg text-sm font-medium transition-colors bg-[var(--accent)] text-white hover:brightness-110"
                        >
                            完成
                        </button>
                    ) : (
                        <button
                            onClick={handleInit}
                            disabled={isInitializing || selectedLevels.length === 0}
                            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${isInitializing || selectedLevels.length === 0
                                ? "bg-[rgba(218,119,86,0.5)] text-white/70 cursor-not-allowed"
                                : "bg-[var(--accent)] text-white hover:brightness-110"
                                }`}
                        >
                            {isInitializing ? t.indexInitializing : t.indexInitialize}
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}
