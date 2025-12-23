// App.tsx - 主应用入口（精简版）

import { useEffect, useRef, useState, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { SettingsPage } from "./components/settings/SettingsPage";
import { RunCard } from "./components/chat/RunCard";
import { Icons } from "./components/icons/Icons";
import {
    parseStreamLine,
    parseCodeChanges,
    parseHistoryPayload,
    mergeHistoryRuns,
    groupRunsByProject,
} from "./utils/parse";
import {
    MAX_LINES,
    DEFAULT_PORT,
    HISTORY_SAVE_DEBOUNCE_MS,
    translations,
    type LayoutMode,
    type ConnectionState,
    type Language,
    type Theme,
    type RunState,
    type ViewerSettings,
    type CodeChanges,
} from "./types/viewer";

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
    const [showSettings, setShowSettings] = useState(false);
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

    useEffect(() => { runsRef.current = runs; }, [runs]);

    useEffect(() => {
        const loadSessions = async () => {
            const roots = new Set(runs.map(r => r.projectRoot).filter(Boolean));
            for (const root of roots) {
                try {
                    const raw = await invoke<string>('load_sessions', { project_path: root });
                    const data = JSON.parse(raw);
                    if (data.sessions) setSessions(prev => ({ ...prev, ...data.sessions }));
                } catch { }
            }
        };
        loadSessions();
        const interval = setInterval(loadSessions, 5000);
        return () => clearInterval(interval);
    }, [runs]);

    const scheduleHistorySave = useCallback(() => {
        if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
        saveTimerRef.current = window.setTimeout(() => {
            const grouped = groupRunsByProject(runsRef.current);
            for (const [projectRoot, history] of grouped) {
                if (!historyLoadedRef.current.has(projectRoot)) continue;
                invoke("save_history", { project_path: projectRoot, history_json: JSON.stringify(history) }).catch(() => { });
            }
        }, HISTORY_SAVE_DEBOUNCE_MS);
    }, []);

    const ensureHistoryLoaded = useCallback((projectRoot: string) => {
        if (!projectRoot || historyLoadedRef.current.has(projectRoot) || historyLoadingRef.current.has(projectRoot)) return;
        historyLoadingRef.current.add(projectRoot);
        invoke<string>("load_history", { project_path: projectRoot })
            .then((raw) => {
                const parsed = parseHistoryPayload(raw);
                if (parsed && parsed.length > 0) setRuns((prev) => mergeHistoryRuns(prev, parsed));
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
        for (const run of runs) if (run.projectRoot) roots.add(run.projectRoot);
        roots.forEach((root) => ensureHistoryLoaded(root));
    }, [runs, ensureHistoryLoaded]);

    useEffect(() => { scheduleHistorySave(); }, [runs, scheduleHistorySave]);
    useEffect(() => () => { if (saveTimerRef.current) clearTimeout(saveTimerRef.current); }, []);

    const findSession = (runs: RunState[], sessionId: string | null | undefined, runId: string): number => {
        if (sessionId) {
            const idx = runs.findIndex((r) => r.sessionId === sessionId);
            if (idx >= 0) return idx;
        }
        return runs.findIndex((r) => r.runIds.includes(runId));
    };

    const updateSession = (runId: string, sessionId: string | null | undefined, updater: (prev: RunState | null, isNewTurn: boolean) => RunState) => {
        setRuns((prev) => {
            const index = findSession(prev, sessionId, runId);
            const existing = index >= 0 ? prev[index] : null;
            const isNewTurn = existing !== null && !existing.runIds.includes(runId);
            const next = updater(existing, isNewTurn);
            if (!next.runIds.includes(runId)) next.runIds = [...next.runIds, runId];
            if (index >= 0) { const clone = [...prev]; clone[index] = next; return clone; }
            return [next, ...prev];
        });
    };

    const connect = () => {
        if (eventSourceRef.current) { eventSourceRef.current.close(); eventSourceRef.current = null; }
        setConnectionState("connecting");
        const source = new EventSource(sseUrl);
        eventSourceRef.current = source;

        source.onopen = () => {
            setConnectionState("connected");
            if (reconnectTimerRef.current) { clearTimeout(reconnectTimerRef.current); reconnectTimerRef.current = null; }
        };

        source.onerror = () => {
            setConnectionState("error");
            source.close();
            eventSourceRef.current = null;
            if (!reconnectTimerRef.current) {
                reconnectTimerRef.current = window.setTimeout(() => { reconnectTimerRef.current = null; connect(); }, 3000);
            }
        };

        const parsePayload = (event: MessageEvent) => { try { return JSON.parse(event.data); } catch { return null; } };
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
                    clone[index] = { ...clone[index], lines: [...clone[index].lines, { type: "user", content: payload.text }] };
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
                if (pendingUserInput) { newLines.push({ type: "user", content: pendingUserInput }); pendingUserInput = null; }
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
                const base: RunState = prev ?? { id: payload.session_id || payload.run_id, runIds: [], status: "running", turnCount: 1, lines: [], codeChanges: defaultChanges };
                let nextLines = [...base.lines];
                if (parsed) {
                    if (parsed.type === "agent" && nextLines.length > 0 && nextLines[nextLines.length - 1].type === "agent") {
                        nextLines[nextLines.length - 1] = { type: "agent", content: nextLines[nextLines.length - 1].content + parsed.content };
                    } else if (parsed.type === "tool_end" && nextLines.length > 0 && nextLines[nextLines.length - 1].type === "tool_start" && nextLines[nextLines.length - 1].content === parsed.content) {
                        nextLines[nextLines.length - 1] = parsed;
                    } else {
                        nextLines.push(parsed);
                    }
                }
                if (nextLines.length > MAX_LINES) nextLines.splice(0, nextLines.length - MAX_LINES);
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
                id: payload.session_id || prev?.id || payload.run_id, runIds: prev?.runIds ?? [], projectRoot: payload.project_root ?? prev?.projectRoot, sessionId: payload.session_id ?? prev?.sessionId, status: "error",
                startedAt: prev?.startedAt, completedAt: prev?.completedAt, success: prev?.success, exitCode: prev?.exitCode, errorType: payload.error_type ?? prev?.errorType, duration: prev?.duration, turnCount: prev?.turnCount ?? 1, thinkingStartTime: undefined, lines: prev?.lines ?? [], codeChanges: prev?.codeChanges ?? { filesChanged: 0, linesAdded: 0, linesRemoved: 0 },
            }));
        });

        source.addEventListener("codex.completed", (event) => {
            const payload = parsePayload(event as MessageEvent);
            if (!payload?.run_id) return;
            updateSession(payload.run_id, payload.session_id, (prev) => ({
                id: payload.session_id || prev?.id || payload.run_id, runIds: prev?.runIds ?? [], projectRoot: payload.project_root ?? prev?.projectRoot, sessionId: payload.session_id ?? prev?.sessionId, status: "completed",
                startedAt: prev?.startedAt, completedAt: payload.ts ?? prev?.completedAt, success: payload.success ?? prev?.success, exitCode: payload.exit_code ?? prev?.exitCode, errorType: payload.error_type ?? prev?.errorType, duration: (prev?.duration ?? 0) + (payload.duration_s ?? 0), turnCount: prev?.turnCount ?? 1, thinkingStartTime: undefined, lines: prev?.lines ?? [], codeChanges: prev?.codeChanges ?? { filesChanged: 0, linesAdded: 0, linesRemoved: 0 },
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
        <div className={`min-h-screen font-sans transition-colors duration-300 ${theme === "dark" ? "bg-slate-900 text-slate-100 selection:bg-purple-500/30" : `text-slate-800 selection:bg-orange-100 ${layoutMode === "grid" ? "bg-slate-50/50" : "bg-slate-50/30"}`}`}>
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
                    <div className="flex items-center gap-4 group">
                        <div className={`relative w-10 h-10 rounded-xl flex items-center justify-center shadow-lg transition-transform group-hover:scale-105 group-hover:rotate-3 ${theme === "dark" ? "bg-slate-700 text-white" : "bg-slate-900 text-white"}`}>
                            <span className="font-bold text-sm tracking-tighter">CS</span>
                            <div className="absolute inset-0 rounded-xl bg-white/10 opacity-0 group-hover:opacity-100 transition-opacity"></div>
                        </div>
                        <div>
                            <h1 className={`text-lg font-bold tracking-tight transition-colors ${theme === "dark" ? "text-slate-100 group-hover:text-purple-400" : "text-slate-900 group-hover:text-orange-600"}`}>{t.title}</h1>
                            <div className="flex items-center gap-2">
                                <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] uppercase font-bold tracking-wider border ${connectionState === "connected" ? "bg-emerald-50 text-emerald-600 border-emerald-100" : connectionState === "connecting" ? "bg-amber-50 text-amber-600 border-amber-100" : "bg-rose-50 text-rose-600 border-rose-100"}`}>
                                    <span className={`w-1.5 h-1.5 rounded-full ${connectionState === "connected" ? "bg-emerald-500 animate-pulse" : connectionState === "connecting" ? "bg-amber-500 animate-pulse" : "bg-rose-500"}`}></span>
                                    {connectionState === "connected" ? t.connected : connectionState === "connecting" ? t.connecting : t.connectionError}
                                </div>
                                {showPortInput ? (
                                    <input type="number" value={port} onChange={(e) => handlePortChange(parseInt(e.target.value))} onBlur={() => setShowPortInput(false)} className="w-20 text-[10px] bg-slate-100 border border-slate-200 rounded px-1.5 py-0.5 outline-none focus:ring-1 focus:ring-orange-200 font-mono text-slate-600" autoFocus />
                                ) : (
                                    <button onClick={() => setShowPortInput(true)} className="text-[10px] text-slate-400 font-mono hover:text-orange-500 transition-colors border-b border-transparent hover:border-orange-200" title="Click to change port">localhost:{port}</button>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Controls */}
                    <div className={`flex items-center gap-3 backdrop-blur-md p-1.5 rounded-2xl border shadow-sm ${theme === "dark" ? "bg-slate-800/60 border-slate-700/50" : "bg-white/60 border-white/50"}`}>
                        <div className={`flex rounded-xl p-1 gap-1 ${theme === "dark" ? "bg-slate-700/50" : "bg-slate-100/50"}`}>
                            <button onClick={() => setLayoutMode("list")} className={`p-2 rounded-lg transition-all ${layoutMode === "list" ? (theme === "dark" ? "bg-slate-600 text-slate-100 shadow-sm" : "bg-white text-slate-800 shadow-sm") : (theme === "dark" ? "text-slate-400 hover:text-slate-200" : "text-slate-400 hover:text-slate-600")}`} title="List View"><Icons.List /></button>
                            <button onClick={() => setLayoutMode("grid")} className={`p-2 rounded-lg transition-all ${layoutMode === "grid" ? (theme === "dark" ? "bg-slate-600 text-slate-100 shadow-sm" : "bg-white text-slate-800 shadow-sm") : (theme === "dark" ? "text-slate-400 hover:text-slate-200" : "text-slate-400 hover:text-slate-600")}`} title="Grid View"><Icons.Grid /></button>
                        </div>
                        <div className={`w-px h-6 mx-1 ${theme === "dark" ? "bg-slate-600" : "bg-slate-200"}`}></div>
                        <button onClick={() => setTheme(theme === "dark" ? "light" : "dark")} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl transition-colors text-[11px] font-semibold ${theme === "dark" ? "hover:bg-slate-700/80 text-slate-300" : "hover:bg-white/80 text-slate-600"}`} title={theme === "dark" ? t.lightMode : t.darkMode}>{theme === "dark" ? <Icons.Sun /> : <Icons.Moon />}{theme === "dark" ? t.lightMode : t.darkMode}</button>
                        <button onClick={() => setLang(lang === "zh" ? "en" : "zh")} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl transition-colors text-[11px] font-semibold ${theme === "dark" ? "hover:bg-slate-700/80 text-slate-300" : "hover:bg-white/80 text-slate-600"}`}><Icons.Globe />{lang === "zh" ? "EN" : "中"}</button>
                        <button onClick={() => setShowSettings(true)} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl transition-colors text-[11px] font-semibold ${theme === "dark" ? "hover:bg-slate-700/80 text-slate-300" : "hover:bg-white/80 text-slate-600"}`} title="Settings"><Icons.Cog /></button>
                        {runs.length > 0 && (<button onClick={() => setRuns([])} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl transition-colors text-[11px] font-semibold ${theme === "dark" ? "bg-orange-900/40 text-orange-300 hover:bg-orange-900/60 hover:text-orange-200" : "bg-orange-50 text-orange-700 hover:bg-orange-100 hover:text-orange-800"}`}><Icons.Trash />{t.clearRuns}</button>)}
                    </div>
                </header>

                {/* Content Area */}
                <main className="flex-1 overflow-y-auto px-6 pb-8 custom-scrollbar">
                    {runs.length === 0 ? (
                        <div className="h-full flex flex-col items-center justify-center -mt-20">
                            <div className="relative group">
                                <div className={`absolute inset-0 rounded-full blur-2xl opacity-20 group-hover:opacity-40 transition-opacity duration-1000 ${theme === "dark" ? "bg-gradient-to-tr from-purple-600 to-blue-600" : "bg-gradient-to-tr from-orange-200 to-rose-200"}`}></div>
                                <div className={`relative w-24 h-24 rounded-3xl border shadow-[0_20px_40px_-10px_rgba(0,0,0,0.05)] flex items-center justify-center mb-6 ${theme === "dark" ? "bg-slate-800 border-slate-700" : "bg-white border-slate-100"}`}>
                                    <svg className={`w-10 h-10 ${theme === "dark" ? "text-slate-500" : "text-slate-300"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                                </div>
                            </div>
                            <h3 className={`text-lg font-semibold mb-2 ${theme === "dark" ? "text-slate-200" : "text-slate-800"}`}>{t.waitingEvents}</h3>
                            <p className={`text-sm max-w-sm text-center leading-relaxed ${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>Waiting for Codex execution events from <br /><code className={`px-2 py-0.5 rounded font-mono text-xs mt-1 inline-block ${theme === "dark" ? "bg-slate-800 text-slate-300" : "bg-slate-100 text-slate-600"}`}>{sseUrl}</code></p>
                        </div>
                    ) : (
                        <div className={`${layoutMode === "grid" ? "grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-4" : "flex flex-col gap-6 w-full"} mx-auto`}>
                            {runs.map((run) => (<RunCard key={run.id} run={run} lang={lang} t={t} theme={theme} sessions={sessions} isCompact={layoutMode === "grid"} />))}
                        </div>
                    )}
                </main>
            </div>

            <style>{`
                .custom-scrollbar::-webkit-scrollbar { width: 6px; height: 6px; }
                .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
                .custom-scrollbar::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
                .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
                @keyframes shimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }
                .thinking-shimmer { background: linear-gradient(90deg, rgba(168, 85, 247, 0.4) 0%, rgba(192, 132, 252, 0.7) 25%, rgba(168, 85, 247, 0.4) 50%, rgba(192, 132, 252, 0.7) 75%, rgba(168, 85, 247, 0.4) 100%); background-size: 200% 100%; -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; animation: shimmer 2s linear infinite; }
            `}</style>

            {showSettings && <SettingsPage onClose={() => setShowSettings(false)} isDarkMode={theme === "dark"} />}
        </div>
    );
}
