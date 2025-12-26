// App.tsx - 主应用入口（精简版）

import { useEffect, useRef, useState, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { SettingsPage } from "./components/settings/SettingsPage";
import { ModelManagerPage } from "./components/settings/ModelManagerPage";
import { SkillsPage } from "./components/settings/SkillsPage";
import { Icons } from "./components/icons/Icons";
import { ProjectPanel } from "./components/projects/ProjectPanel";
import { ProjectPage } from "./components/projects/ProjectPage";
import { RemoveProjectPrompt } from "./components/projects/RemoveProjectPrompt";
import { CommandsGuidePage } from "./components/commands-panel/CommandsGuidePage";
import { IndexPrompt } from "./components/index/IndexPrompt";
import { TitleBar } from "./components/layout/TitleBar";
import { useTauriEvents, type TauriAgentEvent } from "./hooks/useTauriEvents";
import { useCommands } from "./hooks/useCommands";
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
import type { ProjectRecord } from "./types/projects";

export default function App() {
    const [lang, setLang] = useState<Language>("zh");
    const themeStorageKey = "cc-spec-tools-theme";
    const legacyThemeStorageKey = "cc-spec-viewer-theme";
    const [theme, setTheme] = useState<Theme>(() => {
        const saved = localStorage.getItem(themeStorageKey) ?? localStorage.getItem(legacyThemeStorageKey);
        if (saved === "dark" || saved === "light") {
            if (!localStorage.getItem(themeStorageKey)) {
                localStorage.setItem(themeStorageKey, saved);
            }
            return saved;
        }
        return "light";
    });
    const [port, setPort] = useState(DEFAULT_PORT);
    const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");
    const [runs, setRuns] = useState<RunState[]>([]);
    const [sessions, setSessions] = useState<Record<string, any>>({});
    const [projects, setProjects] = useState<ProjectRecord[]>([]);
    const [currentProject, setCurrentProject] = useState<ProjectRecord | null>(null);
    const [projectLoading, setProjectLoading] = useState(false);
    const [projectError, setProjectError] = useState<string | null>(null);
    const [layoutMode, setLayoutMode] = useState<LayoutMode>("list");
    const [activeView, setActiveView] = useState<"projects" | "project" | "settings" | "model-manager" | "commands-guide" | "skills">("projects");
    const [activeProjectTab, setActiveProjectTab] = useState<"overview" | "skills" | "codex" | "artifacts" | "runs">("overview");
    const [showIndexPrompt, setShowIndexPrompt] = useState(false);
    const [removeProjectTarget, setRemoveProjectTarget] = useState<ProjectRecord | null>(null);
    const [removeProjectModalError, setRemoveProjectModalError] = useState<string | null>(null);
    const [userSelectedProject, setUserSelectedProject] = useState(false); // 区分用户主动选择 vs 启动恢复
    const eventSourceRef = useRef<EventSource | null>(null);
    const reconnectTimerRef = useRef<number | null>(null);
    const runsRef = useRef<RunState[]>([]);
    const historyLoadedRef = useRef<Set<string>>(new Set());
    const historyLoadingRef = useRef<Set<string>>(new Set());
    const saveTimerRef = useRef<number | null>(null);
    const {
        commands,
        loading: commandsLoading,
        error: commandsError,
        version: commandsVersion,
        updateNeeded,
        checkStatus,
        installCommands,
        uninstallCommands,
    } = useCommands();

    const bringWindowToFront = useCallback(async () => {
        try {
            const win = getCurrentWindow();
            await win.unminimize();
            await win.setFocus();
        } catch { }
    }, []);

    const t = translations[lang];
    const sseUrl = `http://127.0.0.1:${port}/events`;
    const normalizePath = useCallback((path?: string | null) => {
        if (!path) return "";
        return path.replace(/\\/g, "/").toLowerCase();
    }, []);
    const isSamePath = useCallback((left?: string | null, right?: string | null) => {
        if (!left || !right) return false;
        return normalizePath(left) === normalizePath(right);
    }, [normalizePath]);

    const loadProjects = useCallback(async () => {
        setProjectLoading(true);
        setProjectError(null);
        try {
            const [list, current] = await Promise.all([
                invoke<ProjectRecord[]>("list_projects"),
                invoke<ProjectRecord | null>("get_current_project"),
            ]);
            setProjects(list);
            setCurrentProject(current ?? null);
        } catch (error) {
            setProjectError(error instanceof Error ? error.message : String(error));
        } finally {
            setProjectLoading(false);
        }
    }, []);

    const handleImportProject = useCallback(async (path: string) => {
        const trimmed = path.trim();
        if (!trimmed) {
            setProjectError(t.projectPathRequired);
            return;
        }
        setProjectLoading(true);
        setProjectError(null);
        try {
            const record = await invoke<ProjectRecord>("import_project", { path: trimmed });
            setProjects((prev) => {
                const next = prev.filter((project) => project.id !== record.id);
                return [record, ...next];
            });
            setCurrentProject(record);
            setUserSelectedProject(true); // 用户主动导入项目

            // 导入后自动安装 Commands（静默，不阻断流程）
            installCommands(record.path).catch((err) => {
                console.error("Commands 自动安装失败:", err);
            });

            // 导入后刷新 Commands 状态
            checkStatus(record.path);
        } catch (error) {
            setProjectError(error instanceof Error ? error.message : String(error));
        } finally {
            setProjectLoading(false);
        }
    }, [t.projectPathRequired, installCommands, checkStatus]);

    const handleSelectProject = useCallback(async (projectId: string): Promise<ProjectRecord | null> => {
        setProjectLoading(true);
        setProjectError(null);
        try {
            const selected = await invoke<ProjectRecord | null>("set_current_project", { projectId });
            if (!selected) {
                setProjectError(t.projectNotFound);
                return null;
            }
            setProjects((prev) => prev.map((project) => (project.id === selected.id ? selected : project)));
            setCurrentProject(selected);
            setUserSelectedProject(true); // 用户主动选择项目
            return selected;
        } catch (error) {
            setProjectError(error instanceof Error ? error.message : String(error));
            return null;
        } finally {
            setProjectLoading(false);
        }
    }, [t.projectNotFound]);

    const handleEnterProject = useCallback(async (projectId: string) => {
        if (currentProject?.id === projectId) {
            setUserSelectedProject(true);
            setActiveProjectTab("overview");
            setActiveView("project");
            return;
        }
        const selected = await handleSelectProject(projectId);
        if (selected) {
            setActiveProjectTab("overview");
            setActiveView("project");
        }
    }, [currentProject?.id, handleSelectProject]);

    const handleRemoveProject = useCallback(async (projectId: string) => {
        const target = projects.find((p) => p.id === projectId) || null;
        if (!target) {
            setProjectError(t.projectNotFound);
            return;
        }
        setRemoveProjectModalError(null);
        setRemoveProjectTarget(target);
    }, [projects, t.projectNotFound]);

    const handleLaunchClaudeTerminal = useCallback(async () => {
        if (!currentProject?.path) {
            setProjectError(t.noProjectSelected);
            return;
        }
        setProjectLoading(true);
        setProjectError(null);
        try {
            await invoke("launch_claude_terminal", { projectPath: currentProject.path });
        } catch (error) {
            setProjectError(error instanceof Error ? error.message : String(error));
        } finally {
            setProjectLoading(false);
        }
    }, [currentProject?.path, t.noProjectSelected]);

    const handleRefreshCommands = useCallback(async () => {
        if (!currentProject?.path) return;
        await checkStatus(currentProject.path);
    }, [currentProject?.path, checkStatus]);

    const handleInstallCommands = useCallback(async () => {
        if (!currentProject?.path) return;
        await installCommands(currentProject.path);
    }, [currentProject?.path, installCommands]);

    const handleUninstallCommands = useCallback(async () => {
        if (!currentProject?.path) return;
        await uninstallCommands(currentProject.path);
    }, [currentProject?.path, uninstallCommands]);

    useEffect(() => {
        invoke<ViewerSettings>("get_settings")
            .then((settings) => {
                if (settings.port && settings.port !== port) setPort(settings.port);
            })
            .catch(() => { });
    }, []);

    useEffect(() => {
        loadProjects();
    }, [loadProjects]);

    useEffect(() => {
        localStorage.setItem(themeStorageKey, theme);
        document.documentElement.dataset.theme = theme;
    }, [theme, themeStorageKey]);

    useEffect(() => { runsRef.current = runs; }, [runs]);

    useEffect(() => {
        const loadSessions = async () => {
            const roots = new Set(runs.map(r => r.projectRoot).filter(Boolean));
            for (const root of roots) {
                try {
                    const raw = await invoke<string>('load_sessions', { projectPath: root });
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
                invoke("save_history", { projectPath: projectRoot, historyJson: JSON.stringify(history) }).catch(() => { });
            }
        }, HISTORY_SAVE_DEBOUNCE_MS);
    }, []);

    const ensureHistoryLoaded = useCallback((projectRoot: string) => {
        if (!projectRoot || historyLoadedRef.current.has(projectRoot) || historyLoadingRef.current.has(projectRoot)) return;
        historyLoadingRef.current.add(projectRoot);
        invoke<string>("load_history", { projectPath: projectRoot })
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

    useEffect(() => {
        if (currentProject?.path) ensureHistoryLoaded(currentProject.path);
    }, [currentProject?.path, ensureHistoryLoaded]);

    useEffect(() => {
        if (currentProject?.path) checkStatus(currentProject.path);
    }, [currentProject?.path, checkStatus]);

    useEffect(() => {
        let active = true;
        const checkIndexPrompt = async () => {
            // 只在用户主动选择项目时才显示弹窗，启动时自动恢复的项目不弹窗
            if (!currentProject?.path || !userSelectedProject) {
                if (active) setShowIndexPrompt(false);
                return;
            }
            try {
                const [exists, dismissed] = await Promise.all([
                    invoke<boolean>("check_index_exists", { projectPath: currentProject.path }),
                    invoke<boolean>("get_index_settings_prompt_dismissed", { projectPath: currentProject.path }),
                ]);
                if (active) setShowIndexPrompt(!exists && !dismissed);
            } catch {
                if (active) setShowIndexPrompt(false);
            }
        };
        checkIndexPrompt();
        return () => {
            active = false;
        };
    }, [currentProject?.path, userSelectedProject]);

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

    // ========== Tauri 事件监听 (CC 事件) ==========
    const handleTauriStarted = useCallback((event: TauriAgentEvent) => {
        bringWindowToFront();
        updateSession(event.run_id, event.session_id, (prev, isNewTurn) => {
            const newLines = [...(prev?.lines ?? [])];
            if (isNewTurn && newLines.length > 0) newLines.push({ type: "info", content: "───" });
            return {
                id: event.session_id || prev?.id || event.run_id,
                runIds: prev?.runIds ?? [],
                projectRoot: prev?.projectRoot,
                sessionId: event.session_id ?? prev?.sessionId,
                status: "running",
                startedAt: prev?.startedAt ?? new Date().toISOString(),
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
    }, [bringWindowToFront]);

    const handleTauriStream = useCallback((event: TauriAgentEvent) => {
        // 提取文本内容
        let text = "";
        if (typeof event.data.content === "string") {
            text = event.data.content;
        } else if (Array.isArray(event.data.content)) {
            text = event.data.content
                .filter(b => b.type === "text")
                .map(b => b.text || "")
                .join("");
        }
        if (!text) return;

        const parsed = parseStreamLine(text);
        const changes = parseCodeChanges(text);
        if (!parsed && !changes) return;

        updateSession(event.run_id, event.session_id, (prev) => {
            const defaultChanges: CodeChanges = { filesChanged: 0, linesAdded: 0, linesRemoved: 0 };
            const base: RunState = prev ?? { id: event.session_id || event.run_id, runIds: [], status: "running", turnCount: 1, lines: [], codeChanges: defaultChanges };
            let nextLines = [...base.lines];
            if (parsed) {
                if (parsed.type === "agent" && nextLines.length > 0 && nextLines[nextLines.length - 1].type === "agent") {
                    nextLines[nextLines.length - 1] = { type: "agent", content: nextLines[nextLines.length - 1].content + parsed.content };
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
            return { ...base, status: "running", sessionId: event.session_id ?? base.sessionId, lines: nextLines, codeChanges: nextChanges };
        });
    }, []);

    const handleTauriCompleted = useCallback((event: TauriAgentEvent) => {
        updateSession(event.run_id, event.session_id, (prev) => ({
            id: event.session_id || prev?.id || event.run_id,
            runIds: prev?.runIds ?? [],
            projectRoot: prev?.projectRoot,
            sessionId: event.session_id ?? prev?.sessionId,
            status: "completed",
            startedAt: prev?.startedAt,
            completedAt: new Date().toISOString(),
            success: event.data.success ?? prev?.success,
            exitCode: prev?.exitCode,
            errorType: prev?.errorType,
            duration: prev?.duration,
            turnCount: prev?.turnCount ?? 1,
            thinkingStartTime: undefined,
            lines: prev?.lines ?? [],
            codeChanges: prev?.codeChanges ?? { filesChanged: 0, linesAdded: 0, linesRemoved: 0 },
        }));
    }, []);

    const handleTauriError = useCallback((event: TauriAgentEvent) => {
        updateSession(event.run_id, event.session_id, (prev) => ({
            id: event.session_id || prev?.id || event.run_id,
            runIds: prev?.runIds ?? [],
            projectRoot: prev?.projectRoot,
            sessionId: event.session_id ?? prev?.sessionId,
            status: "error",
            startedAt: prev?.startedAt,
            completedAt: prev?.completedAt,
            success: false,
            exitCode: prev?.exitCode,
            errorType: event.data.error ?? prev?.errorType,
            duration: prev?.duration,
            turnCount: prev?.turnCount ?? 1,
            thinkingStartTime: undefined,
            lines: prev?.lines ?? [],
            codeChanges: prev?.codeChanges ?? { filesChanged: 0, linesAdded: 0, linesRemoved: 0 },
        }));
    }, []);

    // 启用 Tauri 事件监听
    useTauriEvents({
        onStarted: handleTauriStarted,
        onStream: handleTauriStream,
        onCompleted: handleTauriCompleted,
        onError: handleTauriError,
        enabled: true,
    });

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



    const visibleRuns = currentProject?.path
        ? runs.filter((run) => run.projectRoot && isSamePath(run.projectRoot, currentProject.path))
        : runs;

    const toolbarButtons = (
        <div className="flex items-center gap-1.5 px-2">
            {activeView === "project" && activeProjectTab === "runs" && currentProject && (
                <>
                    <div className={`flex rounded-lg p-0.5 gap-0.5 ${theme === "dark" ? "bg-slate-800" : "bg-slate-100"}`}>
                        <button onClick={() => setLayoutMode("list")} className={`p-1.5 rounded-md transition-all ${layoutMode === "list" ? (theme === "dark" ? "bg-slate-600 text-slate-100 shadow-sm" : "bg-white text-slate-800 shadow-sm") : (theme === "dark" ? "text-slate-400 hover:text-slate-200" : "text-slate-400 hover:text-slate-600")}`} title="List View"><Icons.List /></button>
                        <button onClick={() => setLayoutMode("grid")} className={`p-1.5 rounded-md transition-all ${layoutMode === "grid" ? (theme === "dark" ? "bg-slate-600 text-slate-100 shadow-sm" : "bg-white text-slate-800 shadow-sm") : (theme === "dark" ? "text-slate-400 hover:text-slate-200" : "text-slate-400 hover:text-slate-600")}`} title="Grid View"><Icons.Grid /></button>
                    </div>
                    <div className={`w-px h-4 mx-1 ${theme === "dark" ? "bg-slate-700" : "bg-slate-300"}`}></div>
                </>
            )}
            <button onClick={() => setTheme(theme === "dark" ? "light" : "dark")} className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg transition-colors text-[11px] font-semibold ${theme === "dark" ? "hover:bg-slate-800 text-slate-300" : "hover:bg-slate-100 text-slate-600"}`} title={theme === "dark" ? t.lightMode : t.darkMode}>{theme === "dark" ? <Icons.Sun /> : <Icons.Moon />}</button>
            <button onClick={() => setLang(lang === "zh" ? "en" : "zh")} className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg transition-colors text-[11px] font-semibold ${theme === "dark" ? "hover:bg-slate-800 text-slate-300" : "hover:bg-slate-100 text-slate-600"}`}><Icons.Globe />{lang === "zh" ? "EN" : "中文"}</button>
            <button onClick={() => setActiveView("settings")} className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg transition-colors text-[11px] font-semibold ${activeView === "settings" ? (theme === "dark" ? "bg-slate-800 text-slate-100" : "bg-slate-100 text-slate-800") : (theme === "dark" ? "hover:bg-slate-800 text-slate-300" : "hover:bg-slate-100 text-slate-600")}`} title="Settings"><Icons.Cog /></button>
            {activeView === "project" && activeProjectTab === "runs" && runs.length > 0 && (
                <>
                    <div className={`w-px h-4 mx-1 ${theme === "dark" ? "bg-slate-700" : "bg-slate-300"}`}></div>
                    <button onClick={() => setRuns([])} className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg transition-colors text-[11px] font-semibold ${theme === "dark" ? "hover:bg-orange-900/40 text-orange-300" : "hover:bg-orange-50 text-orange-700"}`}><Icons.Trash />{t.clearRuns}</button>
                </>
            )}
        </div>
    );

    return (
        <div className={`h-screen flex flex-col font-sans transition-colors duration-300 ${theme === "dark" ? "bg-slate-900 text-slate-100 selection:bg-purple-500/30" : `text-slate-800 selection:bg-orange-100 ${layoutMode === "grid" ? "bg-slate-50/50" : "bg-slate-50/30"}`}`}>
            {/* 自定义标题栏 */}
            <TitleBar theme={theme} rightContent={toolbarButtons} t={t} />
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

            <div className="flex w-full flex-1 min-h-0">
                <aside className={`flex-none w-64 border-r pt-2 ${theme === "dark" ? "bg-slate-900/80 border-slate-800" : "bg-white/70 border-slate-200"}`}>
                    <div className="flex h-full flex-col p-3 gap-4">

                        <nav className="flex flex-col gap-2">
                            <button
                                onClick={() => setActiveView("projects")}
                                className={`px-3 py-2 rounded-xl text-left text-sm font-semibold transition-colors ${activeView === "projects" ? (theme === "dark" ? "bg-slate-800 text-slate-100" : "bg-slate-900 text-white") : (theme === "dark" ? "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60" : "text-slate-500 hover:text-slate-800 hover:bg-slate-100")}`}
                            >
                                {t.navProjects}
                            </button>
                            <button
                                onClick={() => setActiveView("commands-guide")}
                                className={`flex items-center gap-2 px-3 py-2 rounded-xl text-left text-sm font-semibold transition-colors ${activeView === "commands-guide" ? (theme === "dark" ? "bg-slate-800 text-slate-100" : "bg-slate-900 text-white") : (theme === "dark" ? "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60" : "text-slate-500 hover:text-slate-800 hover:bg-slate-100")}`}
                            >
                                <Icons.Book />
                                {t.navCommandsGuide || "Commands 指南"}
                            </button>
                            <button
                                onClick={() => setActiveView("skills")}
                                className={`flex items-center gap-2 px-3 py-2 rounded-xl text-left text-sm font-semibold transition-colors ${activeView === "skills" ? (theme === "dark" ? "bg-slate-800 text-slate-100" : "bg-slate-900 text-white") : (theme === "dark" ? "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60" : "text-slate-500 hover:text-slate-800 hover:bg-slate-100")}`}
                            >
                                <Icons.Sparkles />
                                Skills 管理
                            </button>
                        </nav>

                        <div className="flex flex-col gap-2">
                            <div className={`text-[10px] uppercase tracking-[0.2em] font-semibold ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>{t.projects}</div>
                            {projects.length === 0 ? (
                                <div className={`text-xs ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>{t.noProjects}</div>
                            ) : (
                                <div className="flex flex-col gap-2">
                                    {projects.map((project) => {
                                        const isCurrent = currentProject?.id === project.id;
                                        return (
                                            <button
                                                key={project.id}
                                                onClick={() => handleEnterProject(project.id)}
                                                disabled={projectLoading}
                                                className={`w-full text-left px-3 py-2 rounded-xl text-xs font-semibold transition-colors ${isCurrent ? (theme === "dark" ? "bg-purple-500/20 text-purple-100 border border-purple-500/40" : "bg-orange-100 text-orange-700 border border-orange-200") : (theme === "dark" ? "bg-slate-900/60 text-slate-300 border border-slate-800 hover:bg-slate-800" : "bg-white text-slate-600 border border-slate-100 hover:bg-slate-50")}`}
                                            >
                                                <div className="truncate">{project.name}</div>
                                                <div className={`text-[10px] font-mono truncate ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>{project.path}</div>
                                            </button>
                                        );
                                    })}
                                </div>
                            )}
                        </div>

                        {currentProject && (
                            <div className={`mt-auto text-[10px] font-mono ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>{currentProject.path}</div>
                        )}
                    </div>
                </aside>

                <div className="flex-1 flex flex-col min-w-0">
                    {/* Content Area */}
                    {/* Content Area */}
                    <main className="flex-1 overflow-y-auto px-6 py-4 custom-scrollbar">
                        {activeView === "projects" ? (
                            <div className="mx-auto w-full max-w-6xl flex flex-col gap-6">
                                <ProjectPanel
                                    theme={theme}
                                    t={t}
                                    projects={projects}
                                    currentProject={currentProject}
                                    loading={projectLoading}
                                    error={projectError}
                                    onImport={handleImportProject}
                                    onEnter={handleEnterProject}
                                    onRemove={handleRemoveProject}
                                    onRefresh={loadProjects}
                                    onLaunchClaudeTerminal={handleLaunchClaudeTerminal}
                                />
                            </div>
                        ) : activeView === "project" ? (
                            <div className="mx-auto w-full max-w-6xl flex flex-col gap-6">
                                {currentProject ? (
                                    <ProjectPage
                                        theme={theme}
                                        t={t}
                                        lang={lang}
                                        project={currentProject}
                                        activeTab={activeProjectTab}
                                        onTabChange={setActiveProjectTab}
                                        runs={visibleRuns}
                                        sessions={sessions}
                                        layoutMode={layoutMode}
                                        onLaunchClaudeTerminal={handleLaunchClaudeTerminal}
                                        onBack={() => setActiveView("projects")}
                                    />
                                ) : (
                                    <div className="h-full flex flex-col items-center justify-center py-10">
                                        <div className="relative group">
                                            <div className={`absolute inset-0 rounded-full blur-2xl opacity-20 group-hover:opacity-40 transition-opacity duration-1000 ${theme === "dark" ? "bg-gradient-to-tr from-purple-600 to-blue-600" : "bg-gradient-to-tr from-orange-200 to-rose-200"}`}></div>
                                            <div className={`relative w-24 h-24 rounded-3xl border shadow-[0_20px_40px_-10px_rgba(0,0,0,0.05)] flex items-center justify-center mb-6 ${theme === "dark" ? "bg-slate-800 border-slate-700" : "bg-white border-slate-100"}`}>
                                                <svg className={`w-10 h-10 ${theme === "dark" ? "text-slate-500" : "text-slate-300"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" /></svg>
                                            </div>
                                        </div>
                                        <h3 className={`text-lg font-semibold mb-2 ${theme === "dark" ? "text-slate-200" : "text-slate-800"}`}>{t.noProjectSelected}</h3>
                                        <p className={`text-sm max-w-sm text-center leading-relaxed ${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>
                                            {t.selectProjectHint}
                                        </p>
                                    </div>
                                )}
                            </div>
                        ) : activeView === "settings" ? (
                            <div className="mx-auto w-full max-w-6xl flex flex-col gap-6">
                                <SettingsPage
                                    onClose={() => setActiveView("projects")}
                                    isDarkMode={theme === "dark"}
                                    onOpenModelManager={() => setActiveView("model-manager")}
                                    t={t}
                                />
                            </div>
                        ) : activeView === "model-manager" ? (
                            <div className="mx-auto w-full max-w-6xl flex flex-col gap-6">
                                <ModelManagerPage
                                    onClose={() => setActiveView("settings")}
                                    isDarkMode={theme === "dark"}
                                    t={t}
                                />
                            </div>
                        ) : activeView === "commands-guide" ? (
                            <div className="mx-auto w-full max-w-6xl flex flex-col gap-6">
                                <CommandsGuidePage
                                    onClose={() => setActiveView("projects")}
                                    isDarkMode={theme === "dark"}
                                />
                            </div>
                        ) : activeView === "skills" ? (
                            <div className="mx-auto w-full max-w-6xl flex flex-col gap-6">
                                <SkillsPage
                                    onClose={() => setActiveView("projects")}
                                    isDarkMode={theme === "dark"}
                                    currentProjectPath={currentProject?.path}
                                    t={t}
                                />
                            </div>
                        ) : null}
                    </main>
                </div>
            </div>
            <style>{`
                .custom-scrollbar::-webkit-scrollbar { width: 6px; height: 6px; }
                .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
                .custom-scrollbar::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
                .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
                @keyframes shimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }
                .thinking-shimmer { background: linear-gradient(90deg, rgba(168, 85, 247, 0.4) 0%, rgba(192, 132, 252, 0.7) 25%, rgba(168, 85, 247, 0.4) 50%, rgba(192, 132, 252, 0.7) 75%, rgba(168, 85, 247, 0.4) 100%); background-size: 200% 100%; -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; animation: shimmer 2s linear infinite; }
            `}</style>

            {showIndexPrompt && currentProject?.path && (
                <IndexPrompt projectPath={currentProject.path} theme={theme} t={t} onClose={() => setShowIndexPrompt(false)} />
            )}

            {removeProjectTarget && (
                <RemoveProjectPrompt
                    project={removeProjectTarget}
                    theme={theme}
                    t={t}
                    loading={projectLoading}
                    error={removeProjectModalError}
                    onCancel={() => {
                        if (projectLoading) return;
                        setRemoveProjectModalError(null);
                        setRemoveProjectTarget(null);
                    }}
                    onRemoveOnly={async () => {
                        if (!removeProjectTarget?.id) return;
                        setProjectLoading(true);
                        setProjectError(null);
                        setRemoveProjectModalError(null);
                        try {
                            const removed = await invoke<boolean>("remove_project", { projectId: removeProjectTarget.id });
                            if (!removed) {
                                setRemoveProjectModalError(t.projectNotFound);
                                return;
                            }
                            setProjects((prev) => prev.filter((project) => project.id !== removeProjectTarget.id));
                            setCurrentProject((prev) => (prev?.id === removeProjectTarget.id ? null : prev));
                            setActiveView((prev) => (prev === "project" && currentProject?.id === removeProjectTarget.id ? "projects" : prev));
                            setRemoveProjectTarget(null);
                        } catch (error) {
                            setRemoveProjectModalError(error instanceof Error ? error.message : String(error));
                        } finally {
                            setProjectLoading(false);
                        }
                    }}
                    onCleanupAndRemove={async ({ backupRequirements }) => {
                        if (!removeProjectTarget?.path || !removeProjectTarget?.id) return;
                        setProjectLoading(true);
                        setProjectError(null);
                        setRemoveProjectModalError(null);
                        try {
                            const normalizePath = (p: string) => p.replace(/\//g, "\\").replace(/\\+$/, "");
                            const isPathInsideProject = (outputPath: string, projectPath: string) => {
                                const outNorm = normalizePath(outputPath);
                                const projNorm = normalizePath(projectPath);
                                const prefix = projNorm.endsWith("\\") ? projNorm : projNorm + "\\";
                                return outNorm.toLowerCase().startsWith(prefix.toLowerCase());
                            };

                            if (backupRequirements) {
                                const { save } = await import("@tauri-apps/plugin-dialog");
                                const today = new Date();
                                const yyyyMMdd = today.toISOString().slice(0, 10).replace(/-/g, "");
                                const sanitizeFileName = (name: string) =>
                                    name
                                        .replace(/[<>:"/\\|?*\x00-\x1F]/g, "-")
                                        .replace(/\s+/g, " ")
                                        .trim() || "requirements";
                                const defaultPath = `${sanitizeFileName(removeProjectTarget.name)}-requirements-${yyyyMMdd}.zip`;
                                const outputPath = await save({
                                    title: t.backupSaveDialogTitle,
                                    defaultPath,
                                    filters: [{ name: "zip", extensions: ["zip"] }],
                                });
                                if (!outputPath) return;
                                if (isPathInsideProject(outputPath, removeProjectTarget.path)) {
                                    setRemoveProjectModalError(t.backupPathInProjectError);
                                    return;
                                }
                                await invoke<string>("export_requirements", {
                                    projectPath: removeProjectTarget.path,
                                    outputPath,
                                });
                            }

                            const cleanupWarnings = await invoke<string[]>("cleanup_project_ccspec", { projectPath: removeProjectTarget.path });

                            const removed = await invoke<boolean>("remove_project", { projectId: removeProjectTarget.id });
                            if (!removed) {
                                setRemoveProjectModalError(t.projectNotFound);
                                return;
                            }
                            setProjects((prev) => prev.filter((project) => project.id !== removeProjectTarget.id));
                            setCurrentProject((prev) => (prev?.id === removeProjectTarget.id ? null : prev));
                            setActiveView((prev) => (prev === "project" && currentProject?.id === removeProjectTarget.id ? "projects" : prev));
                            if (cleanupWarnings.length > 0) {
                                setProjectError(cleanupWarnings.join("\n"));
                            }
                            setRemoveProjectTarget(null);
                        } catch (error) {
                            setRemoveProjectModalError(error instanceof Error ? error.message : String(error));
                        } finally {
                            setProjectLoading(false);
                        }
                    }}
                />
            )}
        </div>
    );
}
