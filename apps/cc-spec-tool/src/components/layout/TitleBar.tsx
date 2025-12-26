// TitleBar.tsx - 自定义窗口标题栏组件

import { getCurrentWindow } from "@tauri-apps/api/window";
import type { Theme, translations } from "../../types/viewer";

interface TitleBarProps {
    theme: Theme;
    title?: string;
    rightContent?: React.ReactNode;
    t: typeof translations["zh"];
}

export function TitleBar({ theme, title = "cc-spec tools", rightContent, t }: TitleBarProps) {
    const appWindow = getCurrentWindow();

    const handleMinimize = async () => {
        try { await appWindow.minimize(); } catch (e) { console.error("Minimize failed", e); }
    };

    const handleMaximize = async () => {
        try {
            const isMaximized = await appWindow.isMaximized();
            if (isMaximized) {
                await appWindow.unmaximize();
            } else {
                await appWindow.maximize();
            }
        } catch (e) {
            console.error("Maximize failed", e);
        }
    };

    const handleClose = async () => {
        try { await appWindow.close(); } catch (e) { console.error("Close failed", e); }
    };

    // 处理标题栏拖拽
    const handleMouseDown = async (e: React.MouseEvent) => {
        // 只响应左键，且不是在按钮上
        if (e.button !== 0) return;
        const target = e.target as HTMLElement;
        if (target.closest('button')) return;

        try {
            await appWindow.startDragging();
        } catch (err) {
            console.error("Start dragging failed", err);
        }
    };

    // 双击最大化/还原
    const handleDoubleClick = async (e: React.MouseEvent) => {
        const target = e.target as HTMLElement;
        if (target.closest('button')) return;
        await handleMaximize();
    };

    const isDark = theme === "dark";

    return (
        <div
            className={`relative z-50 flex items-center justify-between h-10 px-3 select-none border-b shrink-0 cursor-default ${isDark
                    ? "bg-slate-900/95 border-slate-800"
                    : "bg-white/95 border-slate-200"
                }`}
            onMouseDown={handleMouseDown}
            onDoubleClick={handleDoubleClick}
        >
            {/* 左侧：Logo + 标题 */}
            <div className="flex items-center gap-2">
                <div
                    className={`w-5 h-5 rounded-md overflow-hidden flex items-center justify-center ${isDark ? "bg-slate-700" : "bg-white shadow-sm"
                        }`}
                >
                    <img
                        src="/logo.gif"
                        alt="CS"
                        className="w-full h-full object-cover"
                    />
                </div>
                <span
                    className={`text-xs font-medium ${isDark ? "text-slate-300" : "text-slate-600"
                        }`}
                >
                    {title}
                </span>
            </div>

            {/* 右侧：自定义内容 + 窗口控制按钮 */}
            <div className="flex items-center gap-3">
                {/* 自定义功能区 */}
                {rightContent && (
                    <div className="flex items-center gap-1 z-10">
                        {rightContent}
                    </div>
                )}

                {/* 窗口控制按钮 */}
                <div className="flex items-center -mr-1">
                    {/* 最小化按钮 */}
                    <button
                        onClick={handleMinimize}
                        className={`w-10 h-9 flex items-center justify-center rounded-lg transition-colors ${isDark
                            ? "hover:bg-slate-700 text-slate-400 hover:text-slate-200"
                            : "hover:bg-slate-100 text-slate-500 hover:text-slate-700"
                            }`}
                        title={t.minimize}
                    >
                        <svg
                            className="w-3 h-3"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth={2}
                        >
                            <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M20 12H4"
                            />
                        </svg>
                    </button>

                    {/* 最大化按钮 */}
                    <button
                        onClick={handleMaximize}
                        className={`w-10 h-9 flex items-center justify-center rounded-lg transition-colors ${isDark
                            ? "hover:bg-slate-700 text-slate-400 hover:text-slate-200"
                            : "hover:bg-slate-100 text-slate-500 hover:text-slate-700"
                            }`}
                        title={t.maximizeRestore}
                    >
                        <svg
                            className="w-3 h-3"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth={2}
                        >
                            <rect x="4" y="4" width="16" height="16" rx="1" />
                        </svg>
                    </button>

                    {/* 关闭按钮 */}
                    <button
                        onClick={handleClose}
                        className={`w-10 h-9 flex items-center justify-center rounded-lg transition-colors ${isDark
                            ? "hover:bg-red-600 text-slate-400 hover:text-white"
                            : "hover:bg-red-500 text-slate-500 hover:text-white"
                            }`}
                        title={t.close}
                    >
                        <svg
                            className="w-3 h-3"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth={2}
                        >
                            <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M6 18L18 6M6 6l12 12"
                            />
                        </svg>
                    </button>
                </div>
            </div>
        </div>
    );
}
