// components/index/IndexPrompt.tsx - 索引初始化提示组件

import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { Theme, translations } from "../../types/viewer";

interface IndexPromptProps {
    projectPath: string;
    theme: Theme;
    t: typeof translations["zh"];
    onClose: () => void;
}

export function IndexPrompt({ projectPath, theme, t, onClose }: IndexPromptProps) {
    const [isInitializing, setIsInitializing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [selectedLevels, setSelectedLevels] = useState<string[]>(["l1", "l2"]);

    const handleInit = async () => {
        setIsInitializing(true);
        setError(null);
        try {
            await invoke("init_index", {
                projectPath: projectPath,
                levels: selectedLevels,
            });
            onClose();
        } catch (err) {
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
                </div>
            </div>
        </div>
    );
}
