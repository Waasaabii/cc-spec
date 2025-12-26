import { useCallback, useEffect, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Icons } from "../icons/Icons";
import { RunCard } from "../chat/RunCard";
import { ProjectArtifactsPanel } from "./ProjectArtifactsPanel";
import { ProjectCodexPanel } from "./ProjectCodexPanel";
import { ProjectSkillsPanel } from "../settings/ProjectSkillsPanel";
import type { ProjectRecord } from "../../types/projects";
import type { Language, LayoutMode, RunState, Theme, translations } from "../../types/viewer";
import type { ChangeSummary } from "../../types/artifacts";

type ProjectTab = "overview" | "skills" | "codex" | "artifacts" | "runs";

type IndexLevels = {
  l1_summary: boolean;
  l2_symbols: boolean;
  l3_details: boolean;
};

type IndexStatus = {
  initialized: boolean;
  last_updated: string | null;
  file_count: number;
  index_version: string | null;
  levels: IndexLevels | null;
};

type ProjectPageProps = {
  theme: Theme;
  t: typeof translations["zh"];
  lang: Language;
  project: ProjectRecord;
  activeTab: ProjectTab;
  onTabChange: (tab: ProjectTab) => void;
  runs: RunState[];
  sessions: Record<string, any>;
  layoutMode: LayoutMode;
  onLaunchClaudeTerminal: () => Promise<void> | void;
  onBack: () => void;
};

export function ProjectPage({
  theme,
  t,
  lang,
  project,
  activeTab,
  onTabChange,
  runs,
  sessions,
  layoutMode,
  onLaunchClaudeTerminal,
  onBack,
}: ProjectPageProps) {
  const [indexStatus, setIndexStatus] = useState<IndexStatus | null>(null);
  const [changes, setChanges] = useState<ChangeSummary[]>([]);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [overviewError, setOverviewError] = useState<string | null>(null);

  const isDark = theme === "dark";

  const loadOverview = useCallback(async () => {
    setOverviewLoading(true);
    setOverviewError(null);
    try {
      const [status, changeList] = await Promise.all([
        invoke<IndexStatus>("get_index_status", { projectPath: project.path }),
        invoke<ChangeSummary[]>("list_project_changes", { projectPath: project.path }),
      ]);
      setIndexStatus(status);
      setChanges(changeList);
    } catch (err) {
      setOverviewError(err instanceof Error ? err.message : String(err));
    } finally {
      setOverviewLoading(false);
    }
  }, [project.path]);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  const openChangeStatusInVSCode = useCallback(async (dirName: string) => {
    try {
      await invoke("open_project_artifact_in_vscode", {
        projectPath: project.path,
        rootId: "cc_spec",
        relFile: `changes/${dirName}/status.yaml`,
      });
    } catch (err) {
      console.error("Failed to open in VS Code:", err);
    }
  }, [project.path]);

  const levelsText = useMemo(() => {
    if (!indexStatus?.levels) return "-";
    const enabled: string[] = [];
    if (indexStatus.levels.l1_summary) enabled.push("L1");
    if (indexStatus.levels.l2_symbols) enabled.push("L2");
    if (indexStatus.levels.l3_details) enabled.push("L3");
    return enabled.length ? enabled.join(", ") : "-";
  }, [indexStatus?.levels]);

  const tabButtonClass = (tab: ProjectTab) =>
    `px-3 py-2 rounded-xl text-left text-sm font-semibold transition-colors ${activeTab === tab
      ? (isDark ? "bg-slate-800 text-slate-100" : "bg-slate-900 text-white")
      : (isDark ? "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60" : "text-slate-500 hover:text-slate-800 hover:bg-slate-100")
    }`;

  return (
    <div className="flex flex-col gap-4">
      <header className={`rounded-3xl border shadow-sm p-5 ${isDark ? "bg-slate-900/70 border-slate-700/60" : "bg-white/80 border-white/70"}`}>
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <button
                onClick={onBack}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${isDark ? "bg-slate-800 text-slate-300 hover:bg-slate-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
              >
                <span aria-hidden>←</span>
                {t.backToProjects || "返回项目中心"}
              </button>
              <div className={`text-lg font-semibold truncate ${isDark ? "text-slate-100" : "text-slate-900"}`}>{project.name}</div>
            </div>
            {project.description && (
              <div className={`mt-2 text-sm leading-relaxed ${isDark ? "text-slate-400" : "text-slate-500"}`}>{project.description}</div>
            )}
            <div className={`mt-2 text-[11px] font-mono break-all ${isDark ? "text-slate-500" : "text-slate-400"}`}>{project.path}</div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => loadOverview()}
              disabled={overviewLoading}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${isDark ? "bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-60" : "bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-60"}`}
            >
              <Icons.Refresh />
              {overviewLoading ? (t.loading || "加载中") : (t.refresh || "刷新")}
            </button>
            <button
              onClick={() => onLaunchClaudeTerminal()}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors text-white hover:brightness-110"
              style={{ backgroundColor: "#DA7756" }}
            >
              <Icons.Terminal />
              {t.openClaudeTerminal || "打开 Claude 终端"}
            </button>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <button onClick={() => onTabChange("overview")} className={tabButtonClass("overview")}>
            {t.projectTabOverview || "概览"}
          </button>
          <button onClick={() => onTabChange("skills")} className={tabButtonClass("skills")}>
            {t.projectTabSkills || "Skills"}
          </button>
          <button onClick={() => onTabChange("codex")} className={tabButtonClass("codex")}>
            {t.projectTabCodex || "Codex"}
          </button>
          <button onClick={() => onTabChange("artifacts")} className={tabButtonClass("artifacts")}>
            {t.projectTabArtifacts || "产物"}
          </button>
          <button onClick={() => onTabChange("runs")} className={tabButtonClass("runs")}>
            {t.projectTabRuns || "运行"}
          </button>
        </div>
      </header>

      {activeTab === "overview" ? (
        <div className="flex flex-col gap-6">
          <section className={`rounded-3xl border shadow-sm p-5 ${isDark ? "bg-slate-900/70 border-slate-700/60" : "bg-white/80 border-white/70"}`}>
            <div className="flex flex-col gap-1.5">
              <div className={`text-xs uppercase tracking-[0.2em] font-semibold ${isDark ? "text-slate-500" : "text-slate-400"}`}>{t.projectIndexTitle || "索引"}</div>
              <div className="mt-1 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                <div className={`rounded-2xl border p-3 ${isDark ? "bg-slate-900/60 border-slate-800" : "bg-white border-slate-100"}`}>
                  <div className={`text-[10px] uppercase tracking-[0.2em] font-semibold ${isDark ? "text-slate-500" : "text-slate-400"}`}>{t.projectIndexInitialized || "是否初始化"}</div>
                  <div className={`mt-1 text-sm font-semibold ${isDark ? "text-slate-100" : "text-slate-800"}`}>{indexStatus?.initialized ? (t.yes || "是") : (t.no || "否")}</div>
                </div>
                <div className={`rounded-2xl border p-3 ${isDark ? "bg-slate-900/60 border-slate-800" : "bg-white border-slate-100"}`}>
                  <div className={`text-[10px] uppercase tracking-[0.2em] font-semibold ${isDark ? "text-slate-500" : "text-slate-400"}`}>{t.projectIndexLevels || "Levels"}</div>
                  <div className={`mt-1 text-sm font-semibold ${isDark ? "text-slate-100" : "text-slate-800"}`}>{levelsText}</div>
                </div>
                <div className={`rounded-2xl border p-3 ${isDark ? "bg-slate-900/60 border-slate-800" : "bg-white border-slate-100"}`}>
                  <div className={`text-[10px] uppercase tracking-[0.2em] font-semibold ${isDark ? "text-slate-500" : "text-slate-400"}`}>{t.projectIndexFiles || "文件数"}</div>
                  <div className={`mt-1 text-sm font-semibold ${isDark ? "text-slate-100" : "text-slate-800"}`}>{indexStatus?.file_count ?? "-"}</div>
                </div>
                <div className={`rounded-2xl border p-3 ${isDark ? "bg-slate-900/60 border-slate-800" : "bg-white border-slate-100"}`}>
                  <div className={`text-[10px] uppercase tracking-[0.2em] font-semibold ${isDark ? "text-slate-500" : "text-slate-400"}`}>{t.projectIndexUpdatedAt || "更新时间"}</div>
                  <div className={`mt-1 text-xs font-mono break-all ${isDark ? "text-slate-300" : "text-slate-700"}`}>{indexStatus?.last_updated ?? "-"}</div>
                </div>
              </div>
            </div>
          </section>

          <section className={`rounded-3xl border shadow-sm p-5 ${isDark ? "bg-slate-900/70 border-slate-700/60" : "bg-white/80 border-white/70"}`}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className={`text-xs uppercase tracking-[0.2em] font-semibold ${isDark ? "text-slate-500" : "text-slate-400"}`}>{t.projectChangesTitle || "变更"}</div>
                <div className={`text-xs mt-1 ${isDark ? "text-slate-400" : "text-slate-500"}`}>{t.projectChangesHint || "从 .cc-spec/changes 读取 status.yaml 汇总"}</div>
              </div>
              <div className={`text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>{t.projectChangesCount || "数量"}: <span className="font-mono">{changes.length}</span></div>
            </div>

            <div className="mt-4">
              {changes.length === 0 ? (
                <div className={`text-sm ${isDark ? "text-slate-500" : "text-slate-400"}`}>{t.projectChangesEmpty || "暂无变更记录"}</div>
              ) : (
                <div className="grid gap-2">
                  {changes.map((c) => (
                    <div key={c.dirName} className={`flex items-center justify-between gap-3 rounded-2xl border px-3 py-2 ${isDark ? "border-slate-800 bg-slate-900/60" : "border-slate-100 bg-white"}`}>
                      <div className="min-w-0 flex-1">
                        <div className={`text-sm font-semibold truncate ${isDark ? "text-slate-100" : "text-slate-800"}`}>{c.changeName ?? c.dirName}</div>
                        <div className={`mt-1 text-xs flex flex-wrap gap-2 ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                          <span className="font-mono">{c.currentStage ?? "-"}</span>
                          <span className="font-mono">{c.currentStageStatus ?? "-"}</span>
                          <span className="font-mono">{c.updatedAt ?? "-"}</span>
                        </div>
                      </div>
                      <button
                        onClick={() => openChangeStatusInVSCode(c.dirName)}
                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${isDark ? "bg-slate-800 text-slate-300 hover:bg-slate-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
                        title={t.openInVSCode || "在 VS Code 打开"}
                      >
                        <Icons.FileText />
                        {t.openInVSCode || "VS Code"}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {overviewError && (
              <div className={`mt-4 text-xs px-3 py-2 rounded-xl border ${isDark ? "bg-rose-900/30 border-rose-800 text-rose-200" : "bg-rose-50 border-rose-100 text-rose-600"}`}>
                {overviewError}
              </div>
            )}
          </section>
        </div>
      ) : activeTab === "skills" ? (
        <ProjectSkillsPanel projectPath={project.path} isDarkMode={isDark} t={t} />
      ) : activeTab === "codex" ? (
        <ProjectCodexPanel projectPath={project.path} isDarkMode={isDark} t={t} />
      ) : activeTab === "runs" ? (
        <section className="flex flex-col gap-6">
          {runs.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center py-10">
              <div className="relative group">
                <div className={`absolute inset-0 rounded-full blur-2xl opacity-20 group-hover:opacity-40 transition-opacity duration-1000 ${isDark ? "bg-gradient-to-tr from-purple-600 to-blue-600" : "bg-gradient-to-tr from-orange-200 to-rose-200"}`}></div>
                <div className={`relative w-24 h-24 rounded-3xl border shadow-[0_20px_40px_-10px_rgba(0,0,0,0.05)] flex items-center justify-center mb-6 ${isDark ? "bg-slate-800 border-slate-700" : "bg-white border-slate-100"}`}>
                  <svg className={`w-10 h-10 ${isDark ? "text-slate-500" : "text-slate-300"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                </div>
              </div>
              <h3 className={`text-lg font-semibold mb-2 ${isDark ? "text-slate-200" : "text-slate-800"}`}>{t.projectEmpty}</h3>
              <p className={`text-sm max-w-sm text-center leading-relaxed ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                {t.projectEmptyHint}
              </p>
            </div>
          ) : (
            <div className={`${layoutMode === "grid" ? "grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-4" : "flex flex-col gap-6 w-full"} mx-auto`}>
              {runs.map((run) => (
                <RunCard
                  key={run.id}
                  run={run}
                  lang={lang}
                  t={t}
                  theme={theme}
                  sessions={sessions}
                  isCompact={layoutMode === "grid"}
                />
              ))}
            </div>
          )}
        </section>
      ) : (
        <ProjectArtifactsPanel theme={theme} t={t} projectPath={project.path} />
      )}
    </div>
  );
}
