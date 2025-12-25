import { Icons } from "../icons/Icons";
import type { CommandStatus } from "../../types/commands";
import type { Theme } from "../../types/viewer";

type CommandsPanelTranslations = {
    commandsTitle: string;
    commandsHint: string;
    commandsVersion: string;
    commandsUpdateNeeded: string;
    commandsUpToDate: string;
    commandsInstall: string;
    commandsUninstall: string;
    commandsRefresh: string;
    commandsNoProject: string;
    commandsEmpty: string;
    commandsInstalled: string;
    commandsMissing: string;
    loading: string;
};

type CommandsPanelProps = {
    theme: Theme;
    t: CommandsPanelTranslations;
    projectPath: string | null;
    commands: CommandStatus[];
    loading: boolean;
    error: string | null;
    version: string | null;
    updateNeeded: boolean;
    onRefresh: () => Promise<void> | void;
    onInstall: () => Promise<void> | void;
    onUninstall: () => Promise<void> | void;
};

export function CommandsPanel({
    theme,
    t,
    projectPath,
    commands,
    loading,
    error,
    version,
    updateNeeded,
    onRefresh,
    onInstall,
    onUninstall,
}: CommandsPanelProps) {
    const canOperate = Boolean(projectPath) && !loading;

    return (
        <section className={`rounded-3xl border shadow-sm p-5 ${theme === "dark" ? "bg-slate-900/70 border-slate-700/60" : "bg-white/80 border-white/70"}`}>
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div>
                    <h2 className={`text-base font-semibold tracking-tight ${theme === "dark" ? "text-slate-100" : "text-slate-900"}`}>{t.commandsTitle}</h2>
                    <p className={`text-xs mt-1 ${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>{t.commandsHint}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                    <button
                        onClick={() => onRefresh()}
                        disabled={!canOperate}
                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${theme === "dark" ? "bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-60" : "bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-60"}`}
                    >
                        <Icons.Refresh />
                        {loading ? t.loading : t.commandsRefresh}
                    </button>
                    <button
                        onClick={() => onInstall()}
                        disabled={!canOperate}
                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${theme === "dark" ? "bg-slate-700 text-slate-100 hover:bg-slate-600 disabled:opacity-60" : "bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-60"}`}
                    >
                        <Icons.Plus />
                        {t.commandsInstall}
                    </button>
                    <button
                        onClick={() => onUninstall()}
                        disabled={!canOperate}
                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${theme === "dark" ? "bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-60" : "bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-60"}`}
                    >
                        <Icons.Trash />
                        {t.commandsUninstall}
                    </button>
                </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-3 text-xs">
                <span className={`${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>
                    {t.commandsVersion}: <span className="font-mono">{version ?? "-"}</span>
                </span>
                <span className={`px-2 py-0.5 rounded-full font-semibold ${updateNeeded ? (theme === "dark" ? "bg-amber-500/20 text-amber-200" : "bg-amber-100 text-amber-700") : (theme === "dark" ? "bg-emerald-500/20 text-emerald-200" : "bg-emerald-100 text-emerald-700")}`}>
                    {updateNeeded ? t.commandsUpdateNeeded : t.commandsUpToDate}
                </span>
            </div>

            <div className="mt-4">
                {!projectPath ? (
                    <div className={`text-sm ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>{t.commandsNoProject}</div>
                ) : commands.length === 0 ? (
                    <div className={`text-sm ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>{t.commandsEmpty}</div>
                ) : (
                    <div className="grid gap-2">
                        {commands.map((command) => (
                            <div
                                key={command.name}
                                className={`flex items-center justify-between rounded-2xl border px-3 py-2 ${theme === "dark" ? "border-slate-800 bg-slate-900/60" : "border-slate-100 bg-white"}`}
                            >
                                <div className="flex items-center gap-2 min-w-0">
                                    <span className={`${command.installed ? "text-emerald-400" : "text-rose-400"}`}>
                                        {command.installed ? <Icons.CheckCircle /> : <Icons.XCircle />}
                                    </span>
                                    <span className={`text-sm font-semibold truncate ${theme === "dark" ? "text-slate-100" : "text-slate-800"}`}>{command.name}</span>
                                </div>
                                <div className="flex items-center gap-3 text-[10px]">
                                    <span className={`${command.installed ? (theme === "dark" ? "text-emerald-300" : "text-emerald-700") : (theme === "dark" ? "text-rose-300" : "text-rose-600")}`}>
                                        {command.installed ? t.commandsInstalled : t.commandsMissing}
                                    </span>
                                    <span className={`font-mono ${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>{command.version ?? "-"}</span>
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
