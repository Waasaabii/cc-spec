import { useState, useEffect } from "react";
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
    enterProject: string;
    removeProject: string;
    noProjects: string;
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
    onEnter: (projectId: string) => Promise<void> | void;
    onRemove: (projectId: string) => Promise<void> | void;
    onRefresh: () => Promise<void> | void;
};

export function ProjectPanel({
    theme,
    t,
    projects,
    currentProject,
    loading,
    error,
    onImport,
    onEnter,
    onRemove,
    onRefresh,
}: ProjectPanelProps) {
    const [isDragging, setIsDragging] = useState(false);

    const handleDirectImport = async () => {
        try {
            const selected = await open({
                directory: true,
                multiple: false,
                title: "选择项目文件夹",
            });
            if (selected && typeof selected === "string") {
                await onImport(selected);
            }
        } catch (err) {
            console.error("选择文件夹失败:", err);
        }
    };

    // 监听 Tauri 文件拖拽事件
    useEffect(() => {
        let unlisten: () => void;
        import("@tauri-apps/api/event").then(({ listen }) => {
            // Tauri v2 可能是 tauri://drag-drop
            listen<{ paths: string[] }>("tauri://drag-drop", (event) => {
                if (event.payload.paths && event.payload.paths.length > 0) {
                    // 自动导入第一个文件夹
                    // 注意：这里需要判断是否是文件夹，交由后端处理或在这里简单判断
                    onImport(event.payload.paths[0]);
                }
            }).then(u => { unlisten = u; });

            // 兼容 Tauri v1 或者是 file-drop 事件
            listen<string[]>("tauri://file-drop", (event) => {
                if (event.payload && event.payload.length > 0) {
                    onImport(event.payload[0]);
                }
            }).then(u => { if (!unlisten) unlisten = u; /* handle cleanup ?? */ });
        });
        return () => {
            if (unlisten) unlisten();
        };
    }, [onImport]);

    // HTML5 Drag & Drop 视觉反馈 (即使实际数据通过 Tauri 事件传递)
    const handleDragOver = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(true);
    };

    const handleDragLeave = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        // dataTransfer 处理可能受限，主要依赖 Tauri 事件，但这里保留以防 Webview 允许
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            // 尝试读取 path，现代浏览器通常屏蔽
            // @ts-ignore
            const path = e.dataTransfer.files[0].path;
            if (path) {
                onImport(path);
            }
        }
    };

    return (
        <section
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`rounded-3xl border shadow-sm p-5 transition-all duration-200 ${isDragging
                ? (theme === "dark" ? "bg-purple-900/40 border-purple-500 scale-[1.02]" : "bg-orange-50 border-orange-400 scale-[1.02]")
                : (theme === "dark" ? "bg-slate-900/70 border-slate-700/60" : "bg-white/80 border-white/70")
                }`}
        >
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex items-start gap-3">
                    <div className={`w-10 h-10 rounded-2xl flex items-center justify-center ${theme === "dark" ? "bg-slate-800 text-slate-200" : "bg-slate-900 text-white"}`}>
                        <Icons.Folder />
                    </div>
                    <div>
                        <h2 className={`text-base font-semibold tracking-tight ${theme === "dark" ? "text-slate-100" : "text-slate-900"}`}>{t.projects}</h2>
                        <p className={`text-xs mt-1 ${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>
                            {isDragging ? "松开鼠标以导入项目..." : t.projectHint}
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={handleDirectImport}
                        disabled={loading}
                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${theme === "dark" ? "bg-[var(--accent)] text-white hover:brightness-110 disabled:opacity-60" : "bg-[var(--accent)] text-white hover:brightness-110 disabled:opacity-60"}`}
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

            {/* 主内容区：项目列表优先，当前项目其次 */}
            <div className="mt-4 grid gap-4 lg:grid-cols-[1.5fr,1fr]">
                {/* 项目列表（主要） */}
                <div className={`rounded-2xl border p-4 ${theme === "dark" ? "bg-slate-900/80 border-slate-700/60" : "bg-white border-slate-100"}`}>
                    <div className={`text-xs uppercase tracking-[0.2em] font-semibold ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>{t.projectList}</div>
                    <div className="mt-3 max-h-[320px] overflow-y-auto custom-scrollbar pr-1">
                        {!projects.length ? (
                            <div className="flex flex-col items-center justify-center py-8">
                                <div className={`w-12 h-12 rounded-2xl flex items-center justify-center mb-3 ${theme === "dark" ? "bg-slate-800" : "bg-slate-100"}`}>
                                    <Icons.Folder />
                                </div>
                                <div className={`text-sm ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>{t.noProjects}</div>
                                <div className={`text-xs mt-1 opacity-60 ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>
                                    支持拖拽文件夹到此处
                                </div>
                                <button
                                    onClick={handleDirectImport}
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
                                            onClick={() => onEnter(project.id)}
                                            role="button"
                                            tabIndex={0}
                                            onKeyDown={(e) => {
                                                if (e.key === "Enter" || e.key === " ") {
                                                    e.preventDefault();
                                                    onEnter(project.id);
                                                }
                                            }}
                                            className={`flex items-center justify-between gap-3 rounded-xl border px-3 py-2 transition-colors cursor-pointer ${isCurrent ? (theme === "dark" ? "border-purple-500/40 bg-purple-500/10" : "border-orange-200 bg-orange-50") : (theme === "dark" ? "border-slate-800 bg-slate-900/60 hover:border-slate-700" : "border-slate-100 bg-white hover:border-slate-200")}`}
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
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        onEnter(project.id);
                                                    }}
                                                    disabled={loading}
                                                    className={`text-[10px] px-2 py-1 rounded-lg font-semibold transition-colors ${theme === "dark" ? "bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-60" : "bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-60"}`}
                                                >
                                                    {t.enterProject}
                                                </button>
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        onRemove(project.id);
                                                    }}
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
                                    onClick={() => onEnter(currentProject.id)}
                                    disabled={loading}
                                    className={`inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-xs font-semibold transition-colors w-full justify-center ${theme === "dark" ? "bg-[var(--accent)] text-white hover:brightness-110 disabled:opacity-60" : "bg-[var(--accent)] text-white hover:brightness-110 disabled:opacity-60"}`}
                                >
                                    <Icons.ArrowRight />
                                    {t.enterProject}
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
