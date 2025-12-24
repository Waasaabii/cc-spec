import { Icons } from "../icons/Icons";
import type { SkillStatus } from "../../types/skills";
import type { Theme } from "../../types/viewer";

type SkillsPanelTranslations = {
    skillsTitle: string;
    skillsHint: string;
    skillsVersion: string;
    skillsUpdateNeeded: string;
    skillsUpToDate: string;
    skillsInstall: string;
    skillsUninstall: string;
    skillsRefresh: string;
    skillsNoProject: string;
    skillsEmpty: string;
    skillsInstalled: string;
    skillsMissing: string;
    loading: string;
};

type SkillsPanelProps = {
    theme: Theme;
    t: SkillsPanelTranslations;
    projectPath: string | null;
    skills: SkillStatus[];
    loading: boolean;
    error: string | null;
    version: string | null;
    updateNeeded: boolean;
    onRefresh: () => Promise<void> | void;
    onInstall: () => Promise<void> | void;
    onUninstall: () => Promise<void> | void;
};

export function SkillsPanel({
    theme,
    t,
    projectPath,
    skills,
    loading,
    error,
    version,
    updateNeeded,
    onRefresh,
    onInstall,
    onUninstall,
}: SkillsPanelProps) {
    const canOperate = Boolean(projectPath) && !loading;

    return (
        <section className={`rounded-3xl border shadow-sm p-5 ${theme === "dark" ? "bg-slate-900/70 border-slate-700/60" : "bg-white/80 border-white/70"}`}>
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div>
                    <h2 className={`text-base font-semibold tracking-tight ${theme === "dark" ? "text-slate-100" : "text-slate-900"}`}>{t.skillsTitle}</h2>
                    <p className={`text-xs mt-1 ${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>{t.skillsHint}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                    <button
                        onClick={() => onRefresh()}
                        disabled={!canOperate}
                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${theme === "dark" ? "bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-60" : "bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-60"}`}
                    >
                        <Icons.Refresh />
                        {loading ? t.loading : t.skillsRefresh}
                    </button>
                    <button
                        onClick={() => onInstall()}
                        disabled={!canOperate}
                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${theme === "dark" ? "bg-slate-700 text-slate-100 hover:bg-slate-600 disabled:opacity-60" : "bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-60"}`}
                    >
                        <Icons.Plus />
                        {t.skillsInstall}
                    </button>
                    <button
                        onClick={() => onUninstall()}
                        disabled={!canOperate}
                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${theme === "dark" ? "bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-60" : "bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-60"}`}
                    >
                        <Icons.Trash />
                        {t.skillsUninstall}
                    </button>
                </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-3 text-xs">
                <span className={`${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>
                    {t.skillsVersion}: <span className="font-mono">{version ?? "-"}</span>
                </span>
                <span className={`px-2 py-0.5 rounded-full font-semibold ${updateNeeded ? (theme === "dark" ? "bg-amber-500/20 text-amber-200" : "bg-amber-100 text-amber-700") : (theme === "dark" ? "bg-emerald-500/20 text-emerald-200" : "bg-emerald-100 text-emerald-700")}`}>
                    {updateNeeded ? t.skillsUpdateNeeded : t.skillsUpToDate}
                </span>
            </div>

            <div className="mt-4">
                {!projectPath ? (
                    <div className={`text-sm ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>{t.skillsNoProject}</div>
                ) : skills.length === 0 ? (
                    <div className={`text-sm ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>{t.skillsEmpty}</div>
                ) : (
                    <div className="grid gap-2">
                        {skills.map((skill) => (
                            <div
                                key={skill.name}
                                className={`flex items-center justify-between rounded-2xl border px-3 py-2 ${theme === "dark" ? "border-slate-800 bg-slate-900/60" : "border-slate-100 bg-white"}`}
                            >
                                <div className="flex items-center gap-2 min-w-0">
                                    <span className={`${skill.installed ? "text-emerald-400" : "text-rose-400"}`}>
                                        {skill.installed ? <Icons.CheckCircle /> : <Icons.XCircle />}
                                    </span>
                                    <span className={`text-sm font-semibold truncate ${theme === "dark" ? "text-slate-100" : "text-slate-800"}`}>{skill.name}</span>
                                </div>
                                <div className="flex items-center gap-3 text-[10px]">
                                    <span className={`${skill.installed ? (theme === "dark" ? "text-emerald-300" : "text-emerald-700") : (theme === "dark" ? "text-rose-300" : "text-rose-600")}`}>
                                        {skill.installed ? t.skillsInstalled : t.skillsMissing}
                                    </span>
                                    <span className={`font-mono ${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>{skill.version ?? "-"}</span>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {error && (
                <div className={`mt-4 text-xs px-3 py-2 rounded-xl border ${theme === "dark" ? "bg-rose-900/30 border-rose-800 text-rose-200" : "bg-rose-50 border-rose-100 text-rose-600"}`}>
                    {error}
                </div>
            )}
        </section>
    );
}
