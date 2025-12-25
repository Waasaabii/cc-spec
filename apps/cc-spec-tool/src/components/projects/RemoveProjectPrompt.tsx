import { useState } from "react";
import type { ProjectRecord } from "../../types/projects";
import type { Theme, translations } from "../../types/viewer";

interface RemoveProjectPromptProps {
    project: ProjectRecord;
    theme: Theme;
    t: typeof translations["zh"];
    loading: boolean;
    error: string | null;
    onCancel: () => void;
    onRemoveOnly: () => Promise<void>;
    onCleanupAndRemove: (opts: { backupRequirements: boolean }) => Promise<void>;
}

export function RemoveProjectPrompt({
    project,
    theme,
    t,
    loading,
    error,
    onCancel,
    onRemoveOnly,
    onCleanupAndRemove,
}: RemoveProjectPromptProps) {
    const [backupRequirements, setBackupRequirements] = useState(true);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
            <div
                className={`w-full max-w-lg rounded-xl shadow-2xl ${theme === "dark" ? "bg-slate-800 text-slate-100" : "bg-white text-slate-800"
                    }`}
                onClick={(e) => e.stopPropagation()}
            >
                <div className={`px-6 py-4 border-b ${theme === "dark" ? "border-slate-700" : "border-slate-200"}`}>
                    <h2 className="text-lg font-semibold">{t.removeProjectDialogTitle}</h2>
                    <p className={`text-sm mt-1 ${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>
                        {t.removeProjectDialogSubtitle}
                    </p>
                </div>

                <div className="px-6 py-4 space-y-4">
                    <div className={`rounded-lg border p-3 ${theme === "dark" ? "border-slate-700 bg-slate-900/40" : "border-slate-200 bg-slate-50"}`}>
                        <div className="text-sm font-semibold truncate">{project.name}</div>
                        <div className={`text-[11px] font-mono mt-1 truncate ${theme === "dark" ? "text-slate-500" : "text-slate-500"}`}>{project.path}</div>
                    </div>

                    <div className={`text-sm leading-relaxed ${theme === "dark" ? "text-slate-300" : "text-slate-600"}`}>
                        {t.removeProjectDialogDesc}
                    </div>

                    <label className={`flex items-start gap-3 p-3 rounded-lg cursor-pointer border transition-colors ${theme === "dark"
                        ? "border-slate-700 bg-slate-900/30 hover:bg-slate-900/50"
                        : "border-slate-200 bg-slate-50 hover:bg-slate-100"
                        }`}>
                        <input
                            type="checkbox"
                            checked={backupRequirements}
                            onChange={() => setBackupRequirements((prev) => !prev)}
                            className="mt-1 w-4 h-4 rounded border-slate-400"
                            disabled={loading}
                        />
                        <div className="flex-1">
                            <div className="font-medium text-sm">{t.backupRequirementsLabel}</div>
                            <div className={`text-xs mt-0.5 ${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>
                                {t.backupRequirementsHint}
                            </div>
                        </div>
                    </label>

                    {error && (
                        <div className="p-3 rounded-lg bg-rose-500/10 text-rose-400 text-sm max-h-40 overflow-auto break-all whitespace-pre-wrap">
                            {error}
                        </div>
                    )}
                </div>

                <div className={`px-6 py-4 border-t flex items-center justify-end gap-2 ${theme === "dark" ? "border-slate-700" : "border-slate-200"}`}>
                    <button
                        onClick={onCancel}
                        disabled={loading}
                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${theme === "dark"
                            ? "bg-slate-700 hover:bg-slate-600 disabled:opacity-60"
                            : "bg-slate-100 hover:bg-slate-200 disabled:opacity-60"
                            }`}
                    >
                        {t.cancel}
                    </button>
                    <button
                        onClick={() => onRemoveOnly()}
                        disabled={loading}
                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${theme === "dark"
                            ? "bg-slate-800 border border-slate-600 hover:bg-slate-700 disabled:opacity-60"
                            : "bg-white border border-slate-300 hover:bg-slate-50 disabled:opacity-60"
                            }`}
                    >
                        {t.removeProjectOnly}
                    </button>
                    <button
                        onClick={() => onCleanupAndRemove({ backupRequirements })}
                        disabled={loading}
                        className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${theme === "dark"
                            ? "bg-rose-600 hover:bg-rose-500 disabled:opacity-60"
                            : "bg-rose-600 text-white hover:bg-rose-500 disabled:opacity-60"
                            }`}
                    >
                        {loading ? t.removeProjectWorking : t.removeProjectCleanupAndRemove}
                    </button>
                </div>
            </div>
        </div>
    );
}

