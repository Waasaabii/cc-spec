// components/index/IndexPrompt.tsx - 索引初始化提示组件

import { useState, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { Theme } from "../../types/viewer";

interface IndexPromptProps {
    projectPath: string;
    theme: Theme;
    onClose: () => void;
}

export function IndexPrompt({ projectPath, theme, onClose }: IndexPromptProps) {
    const [isInitializing, setIsInitializing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [selectedLevels, setSelectedLevels] = useState<string[]>(["l1", "l2"]);

    const handleInit = async () => {
        setIsInitializing(true);
        setError(null);
        try {
            await invoke("init_index", {
                project_path: projectPath,
                levels: selectedLevels,
            });
            onClose();
        } catch (err) {
            setError(String(err));
        } finally {
            setIsInitializing(false);
        }
    };

    const handleDismiss = async (dontAskAgain: boolean) => {
        if (dontAskAgain) {
            try {
                await invoke("set_index_settings_prompt_dismissed", {
                    project_path: projectPath,
                    dismissed: true,
                });
            } catch (err) {
                console.error("Failed to save dismiss setting:", err);
            }
        }
        onClose();
    };

    const toggleLevel = (level: string) => {
        setSelectedLevels((prev) =>
            prev.includes(level) ? prev.filter((l) => l !== level) : [...prev, level]
        );
    };

    const levels = [
        { id: "l1", name: "L1 - Summary", desc: "Project structure overview" },
        { id: "l2", name: "L2 - Symbols", desc: "Functions, classes, exports" },
        { id: "l3", name: "L3 - Details", desc: "Full code analysis (slower)" },
    ];

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
            <div
                className={`w-full max-w-md rounded-xl shadow-2xl ${
                    theme === "dark" ? "bg-slate-800 text-slate-100" : "bg-white text-slate-800"
                }`}
            >
                {/* Header */}
                <div className={`px-6 py-4 border-b ${theme === "dark" ? "border-slate-700" : "border-slate-200"}`}>
                    <h2 className="text-lg font-semibold flex items-center gap-2">
                        <svg className="w-5 h-5 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                        Initialize Project Index
                    </h2>
                    <p className={`text-sm mt-1 ${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>
                        Create a multi-level index for better AI assistance
                    </p>
                </div>

                {/* Content */}
                <div className="px-6 py-4">
                    <p className={`text-sm mb-4 ${theme === "dark" ? "text-slate-300" : "text-slate-600"}`}>
                        An index helps Claude Code understand your project structure.
                        Select the levels you want to generate:
                    </p>

                    <div className="space-y-2">
                        {levels.map((level) => (
                            <label
                                key={level.id}
                                className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-colors ${
                                    selectedLevels.includes(level.id)
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

                    {error && (
                        <div className="mt-4 p-3 rounded-lg bg-rose-500/10 text-rose-400 text-sm">
                            {error}
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className={`px-6 py-4 border-t flex items-center justify-between ${theme === "dark" ? "border-slate-700" : "border-slate-200"}`}>
                    <button
                        onClick={() => handleDismiss(true)}
                        className={`text-sm ${theme === "dark" ? "text-slate-400 hover:text-slate-300" : "text-slate-500 hover:text-slate-700"}`}
                    >
                        Don't ask again
                    </button>
                    <div className="flex items-center gap-3">
                        <button
                            onClick={() => handleDismiss(false)}
                            className={`px-4 py-2 rounded-lg text-sm font-medium ${
                                theme === "dark"
                                    ? "text-slate-300 hover:bg-slate-700"
                                    : "text-slate-600 hover:bg-slate-100"
                            }`}
                        >
                            Skip
                        </button>
                        <button
                            onClick={handleInit}
                            disabled={isInitializing || selectedLevels.length === 0}
                            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                                isInitializing || selectedLevels.length === 0
                                    ? "bg-blue-500/50 text-white/70 cursor-not-allowed"
                                    : "bg-blue-500 text-white hover:bg-blue-600"
                            }`}
                        >
                            {isInitializing ? "Initializing..." : "Initialize"}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
