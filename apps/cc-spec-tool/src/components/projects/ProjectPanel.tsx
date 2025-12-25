import { useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { Icons } from "../icons/Icons";
import type { ProjectRecord } from "../../types/projects";
import type { Theme } from "../../types/viewer";

type ProjectPanelTranslations = {
    projects: string;
    projectHint: string;
    currentProject: string;
    noProjectSelected: string;
    projectPathPlaceholder: string;
    importProject: string;
    refresh: string;
    projectList: string;
    setCurrent: string;
    removeProject: string;
    noProjects: string;
    openClaudeTerminal: string;
    loading: string;
};

type ProjectPanelProps = {
    theme: Theme;
    t: ProjectPanelTranslations;
    projects: ProjectRecord[];
    currentProject: ProjectRecord | null;
    loading: boolean;
    error: string | null;
    onImport: (path: string) => Promise<void> | void;
    onSelect: (projectId: string) => Promise<void> | void;
    onRemove: (projectId: string) => Promise<void> | void;
    onRefresh: () => Promise<void> | void;
    onLaunchClaudeTerminal: () => Promise<void> | void;
};

export function ProjectPanel({
    theme,
    t,
    projects,
    currentProject,
    loading,
    error,
    onImport,
    onSelect,
    onRemove,
    onRefresh,
    onLaunchClaudeTerminal,
}: ProjectPanelProps) {
    const [pathInput, setPathInput] = useState("");
    const [showImport, setShowImport] = useState(false);
    const hasProjects = projects.length > 0;
    const canImport = !loading && pathInput.trim().length > 0;

    const handleImport = () => {
        const trimmed = pathInput.trim();
        if (!trimmed) return;
        Promise.resolve(onImport(trimmed)).finally(() => {
            setPathInput("");
            setShowImport(false);
        });
    };

    const handleBrowse = async () => {
        try {
            const selected = await open({
                directory: true,
                multiple: false,
                title: "选择项目文件夹",
            });
            if (selected && typeof selected === "string") {
                setPathInput(selected);
            }
        } catch (err) {
            console.error("打开文件夹选择对话框失败:", err);
        }
    };

    return (
        <section className={`rounded-3xl border shadow-sm p-5 ${theme === "dark" ? "bg-slate-900/70 border-slate-700/60" : "bg-white/80 border-white/70"}`}>
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex items-start gap-3">
                    <div className={`w-10 h-10 rounded-2xl flex items-center justify-center ${theme === "dark" ? "bg-slate-800 text-slate-200" : "bg-slate-900 text-white"}`}>
                        <Icons.Folder />
                    </div>
                    <div>
                        <h2 className={`text-base font-semibold tracking-tight ${theme === "dark" ? "text-slate-100" : "text-slate-900"}`}>{t.projects}</h2>
                        <p className={`text-xs mt-1 ${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>{t.projectHint}</p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => setShowImport(!showImport)}
                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${showImport ? (theme === "dark" ? "bg-purple-500/20 text-purple-200" : "bg-orange-100 text-orange-700") : (theme === "dark" ? "bg-slate-800 text-slate-400 hover:text-slate-300 hover:bg-slate-700" : "bg-slate-100 text-slate-500 hover:text-slate-600 hover:bg-slate-200")}`}
                    >
                        <Icons.Plus />
                        {t.importProject}
                    </button>
                    <button
                        onClick={() => onRefresh()}
                        disabled={loading}
                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${theme === "dark" ? "bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-60" : "bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-60"}`}
                    >
                        <Icons.Refresh />
                        {loading ? t.loading : t.refresh}
                    </button>
                </div>
            </div>

            {/* 折叠式导入区域 */}
            {showImport && (
                <div className={`mt-4 rounded-2xl border p-4 ${theme === "dark" ? "bg-slate-800/50 border-slate-700/60" : "bg-slate-50 border-slate-200"}`}>
                    <div className="flex flex-col gap-2">
                        <div className="flex gap-2">
                            <input
                                value={pathInput}
                                onChange={(event) => setPathInput(event.target.value)}
                                onKeyDown={(event) => {
                                    if (event.key === "Enter") handleImport();
                                }}
                                placeholder={t.projectPathPlaceholder}
                                className={`flex-1 rounded-xl px-3 py-2 text-xs font-mono outline-none transition-colors ${theme === "dark" ? "bg-slate-900 text-slate-200 placeholder:text-slate-500 focus:ring-1 focus:ring-slate-500/60" : "bg-white text-slate-700 placeholder:text-slate-400 focus:ring-1 focus:ring-orange-200"}`}
                            />
                            <button
                                onClick={handleBrowse}
                                disabled={loading}
                                className={`px-3 py-2 rounded-xl text-xs font-semibold transition-colors ${theme === "dark" ? "bg-slate-700 text-slate-200 hover:bg-slate-600 disabled:opacity-60" : "bg-slate-200 text-slate-700 hover:bg-slate-300 disabled:opacity-60"}`}
                                title="浏览..."
                            >
                                <Icons.Folder />
                            </button>
                            <button
                                onClick={handleImport}
                                disabled={!canImport}
                                className={`inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold transition-colors ${theme === "dark" ? "bg-purple-600 text-white hover:bg-purple-500 disabled:opacity-60" : "bg-orange-500 text-white hover:bg-orange-600 disabled:opacity-60"}`}
                            >
                                {t.importProject}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* 主内容区：项目列表优先，当前项目其次 */}
            <div className="mt-4 grid gap-4 lg:grid-cols-[1.5fr,1fr]">
                {/* 项目列表（主要） */}
                <div className={`rounded-2xl border p-4 ${theme === "dark" ? "bg-slate-900/80 border-slate-700/60" : "bg-white border-slate-100"}`}>
                    <div className={`text-xs uppercase tracking-[0.2em] font-semibold ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>{t.projectList}</div>
                    <div className="mt-3 max-h-[320px] overflow-y-auto custom-scrollbar pr-1">
                        {!hasProjects ? (
                            <div className="flex flex-col items-center justify-center py-8">
                                <div className={`w-12 h-12 rounded-2xl flex items-center justify-center mb-3 ${theme === "dark" ? "bg-slate-800" : "bg-slate-100"}`}>
                                    <Icons.Folder />
                                </div>
                                <div className={`text-sm ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>{t.noProjects}</div>
                                <button
                                    onClick={() => setShowImport(true)}
                                    className={`mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${theme === "dark" ? "bg-slate-800 text-slate-300 hover:bg-slate-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
                                >
                                    <Icons.Plus />
                                    {t.importProject}
                                </button>
                            </div>
                        ) : (
                            <ul className="flex flex-col gap-2">
                                {projects.map((project) => {
                                    const isCurrent = currentProject?.id === project.id;
                                    return (
                                        <li
                                            key={project.id}
                                            className={`flex items-center justify-between gap-3 rounded-xl border px-3 py-2 transition-colors ${isCurrent ? (theme === "dark" ? "border-purple-500/40 bg-purple-500/10" : "border-orange-200 bg-orange-50") : (theme === "dark" ? "border-slate-800 bg-slate-900/60 hover:border-slate-700" : "border-slate-100 bg-white hover:border-slate-200")}`}
                                        >
                                            <div className="min-w-0 flex-1">
                                                <div className="flex items-center gap-2">
                                                    <span className={`text-sm font-semibold truncate ${theme === "dark" ? "text-slate-100" : "text-slate-800"}`}>{project.name}</span>
                                                    {isCurrent && (
                                                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold flex-shrink-0 ${theme === "dark" ? "bg-purple-500/20 text-purple-200" : "bg-orange-100 text-orange-700"}`}>
                                                            {t.currentProject}
                                                        </span>
                                                    )}
                                                </div>
                                                {project.description && (
                                                    <div className={`text-xs mt-1 line-clamp-2 ${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>{project.description}</div>
                                                )}
                                                <div className={`text-[10px] font-mono truncate mt-1 ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>{project.path}</div>
                                            </div>
                                            <div className="flex items-center gap-2">
                                                {!isCurrent && (
                                                    <button
                                                        onClick={() => onSelect(project.id)}
                                                        disabled={loading}
                                                        className={`text-[10px] px-2 py-1 rounded-lg font-semibold transition-colors ${theme === "dark" ? "bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-60" : "bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-60"}`}
                                                    >
                                                        {t.setCurrent}
                                                    </button>
                                                )}
                                                <button
                                                    onClick={() => onRemove(project.id)}
                                                    disabled={loading}
                                                    className={`p-2 rounded-lg transition-colors ${theme === "dark" ? "bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-60" : "bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-60"}`}
                                                    title={t.removeProject}
                                                >
                                                    <Icons.Trash />
                                                </button>
                                            </div>
                                        </li>
                                    );
                                })}
                            </ul>
                        )}
                    </div>
                </div>

                {/* 当前项目信息（次要） */}
                <div className={`rounded-2xl border p-4 ${theme === "dark" ? "bg-slate-900/80 border-slate-700/60" : "bg-white border-slate-100"}`}>
                    <div className={`text-xs uppercase tracking-[0.2em] font-semibold ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>{t.currentProject}</div>
                    {currentProject ? (
                        <div className="mt-3">
                            <div className={`text-sm font-semibold ${theme === "dark" ? "text-slate-100" : "text-slate-900"}`}>{currentProject.name}</div>
                            {currentProject.description && (
                                <div className={`mt-2 text-xs leading-relaxed ${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>{currentProject.description}</div>
                            )}
                            <div className={`mt-2 text-[10px] font-mono break-all ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>{currentProject.path}</div>
                            <div className="mt-4">
                                <button
                                    onClick={() => onLaunchClaudeTerminal()}
                                    disabled={loading}
                                    className={`inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-xs font-semibold transition-colors w-full justify-center ${theme === "dark" ? "bg-purple-600 text-white hover:bg-purple-500 disabled:opacity-60" : "bg-orange-500 text-white hover:bg-orange-600 disabled:opacity-60"}`}
                                >
                                    <Icons.Terminal />
                                    {t.openClaudeTerminal}
                                </button>
                            </div>
                        </div>
                    ) : (
                        <div className="mt-3 flex flex-col items-center justify-center py-6">
                            <div className={`w-10 h-10 rounded-2xl flex items-center justify-center mb-2 ${theme === "dark" ? "bg-slate-800" : "bg-slate-100"}`}>
                                <Icons.Folder />
                            </div>
                            <div className={`text-sm text-center ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>{t.noProjectSelected}</div>
                        </div>
                    )}
                </div>
            </div>

            {error && (
                <div className={`mt-4 text-xs px-3 py-2 rounded-xl border ${theme === "dark" ? "bg-rose-900/30 border-rose-800 text-rose-200" : "bg-rose-50 border-rose-100 text-rose-600"}`}>
                    {error}
                </div>
            )}
        </section>
    );
}
