// ProjectSkillsPanel.tsx - 项目 Skills 状态面板

import { useEffect, useState, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { ProjectState, SkillScanResult, Skill } from "../../types/skills";
import type { translations } from "../../types/viewer";
import { Icons } from "../icons/Icons";

interface ProjectSkillsPanelProps {
  projectPath: string | null;
  isDarkMode: boolean;
  t: typeof translations["zh"];
}

export function ProjectSkillsPanel({ projectPath, isDarkMode, t }: ProjectSkillsPanelProps) {
  const [projectState, setProjectState] = useState<ProjectState | null>(null);
  const [scanResult, setScanResult] = useState<SkillScanResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // 样式定义
  const cardClass = isDarkMode
    ? "bg-slate-800 border-slate-700"
    : "bg-white border-slate-200";
  const textPrimary = isDarkMode ? "text-slate-100" : "text-slate-900";
  const textSecondary = isDarkMode ? "text-slate-400" : "text-slate-500";
  const borderClass = isDarkMode ? "border-slate-700" : "border-slate-200";

  // 显示消息（自动消失）
  const showMessage = (type: "success" | "error", text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 3000);
  };

  // 加载项目 Skills 状态
  const loadProjectState = useCallback(async () => {
    if (!projectPath) {
      setProjectState(null);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const state = await invoke<ProjectState | null>("get_project_skills_status", {
        projectPath,
      });
      setProjectState(state);
    } catch (err) {
      setError(`加载项目状态失败: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [projectPath]);

  // 扫描项目 Skills 目录
  const handleScanProjectSkills = async () => {
    if (!projectPath) return;

    setScanning(true);
    setError(null);
    try {
      const result = await invoke<SkillScanResult>("scan_project_skills", {
        projectPath,
      });
      setScanResult(result);
      showMessage("success", `${t.scanning.replace("...", "")}完成，发现 ${result.skills.length} 个项目 Skills`);
    } catch (err) {
      showMessage("error", `扫描失败: ${err}`);
    } finally {
      setScanning(false);
    }
  };

  // 更新项目 Skills 安装状态
  const handleUpdateProjectStatus = async (skillNames: string[]) => {
    if (!projectPath) return;

    try {
      await invoke("update_project_skills_status", {
        projectPath,
        skillsInstalled: skillNames,
      });
      await loadProjectState();
      showMessage("success", t.skillsUpdated);
    } catch (err) {
      showMessage("error", `更新失败: ${err}`);
    }
  };

  // 添加扫描到的 Skill 到项目
  const handleAddSkillToProject = async (skillName: string) => {
    if (!projectState) {
      // 初始化项目状态
      await handleUpdateProjectStatus([skillName]);
    } else {
      const newSkills = [...projectState.skills_installed, skillName];
      await handleUpdateProjectStatus(newSkills);
    }
  };

  // 从项目移除 Skill
  const handleRemoveSkillFromProject = async (skillName: string) => {
    if (!projectState) return;
    const newSkills = projectState.skills_installed.filter((s) => s !== skillName);
    await handleUpdateProjectStatus(newSkills);
  };

  // 初始化加载
  useEffect(() => {
    loadProjectState();
    setScanResult(null);
  }, [loadProjectState]);

  // 无项目选中
  if (!projectPath) {
    return (
      <div className={`p-4 rounded-xl border ${cardClass}`}>
        <div className={`text-center py-6 ${textSecondary}`}>
          <p>{t.selectProjectFirst}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 消息提示 */}
      {message && (
        <div
          className={`p-3 rounded-xl text-sm font-medium ${
            message.type === "error"
              ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300"
              : "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
          }`}
        >
          {message.text}
        </div>
      )}

      {/* 错误提示 */}
      {error && (
        <div className="p-3 rounded-xl text-sm font-medium bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300">
          {error}
        </div>
      )}

      {/* 项目信息 */}
      <div className={`p-4 rounded-xl border ${cardClass}`}>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className={`text-lg font-semibold ${textPrimary}`}>项目 Skills</h3>
            <p className={`text-xs font-mono mt-1 ${textSecondary}`}>{projectPath}</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleScanProjectSkills}
              disabled={scanning}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                isDarkMode
                  ? "bg-purple-600 text-white hover:bg-purple-500"
                  : "bg-blue-600 text-white hover:bg-blue-500"
              } disabled:opacity-50`}
            >
              {scanning ? t.scanning : t.scanProjectDir}
            </button>
            <button
              onClick={loadProjectState}
              disabled={loading}
              className={`px-3 py-1.5 rounded-lg text-xs border transition-colors ${borderClass} ${textSecondary} hover:bg-slate-50 dark:hover:bg-slate-700`}
            >
              {t.refresh}
            </button>
          </div>
        </div>

        {/* 项目状态 */}
        {loading ? (
          <div className={`py-4 text-center ${textSecondary}`}>{t.loading}...</div>
        ) : projectState ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-4">
              <div className={`p-3 rounded-lg ${isDarkMode ? "bg-slate-900/50" : "bg-slate-50"}`}>
                <div className={`text-xs ${textSecondary}`}>初始化时间</div>
                <div className={`text-sm font-medium ${textPrimary}`}>
                  {new Date(projectState.initialized_at).toLocaleDateString()}
                </div>
              </div>
              <div className={`p-3 rounded-lg ${isDarkMode ? "bg-slate-900/50" : "bg-slate-50"}`}>
                <div className={`text-xs ${textSecondary}`}>已安装 Skills</div>
                <div className={`text-sm font-bold text-emerald-500`}>
                  {projectState.skills_installed.length}
                </div>
              </div>
            </div>

            {/* 已安装 Skills 列表 */}
            {projectState.skills_installed.length > 0 && (
              <div>
                <div className={`text-xs font-medium mb-2 ${textSecondary}`}>已安装的 Skills:</div>
                <div className="flex flex-wrap gap-2">
                  {projectState.skills_installed.map((skillName) => (
                    <span
                      key={skillName}
                      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm border ${
                        isDarkMode
                          ? "bg-slate-700 text-slate-200 border-slate-600"
                          : "bg-slate-100 text-slate-700 border-slate-200"
                      }`}
                    >
                      {skillName}
                      <button
                        onClick={() => handleRemoveSkillFromProject(skillName)}
                        className="opacity-60 hover:opacity-100"
                        title={t.removeFromProject}
                      >
                        <Icons.Close className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* 自定义覆盖 */}
            {projectState.custom_overrides.length > 0 && (
              <div>
                <div className={`text-xs font-medium mb-2 ${textSecondary}`}>自定义覆盖:</div>
                <div className="flex flex-wrap gap-2">
                  {projectState.custom_overrides.map((override) => (
                    <span
                      key={override}
                      className={`px-2 py-1 rounded text-xs font-mono ${
                        isDarkMode ? "bg-amber-900/30 text-amber-300" : "bg-amber-100 text-amber-700"
                      }`}
                    >
                      {override}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className={`py-4 text-center ${textSecondary}`}>
            <p>此项目尚未初始化 Skills 状态</p>
            <p className="text-xs mt-1">{t.clickToScan}</p>
          </div>
        )}
      </div>

      {/* 扫描结果 */}
      {scanResult && (
        <div className={`p-4 rounded-xl border ${cardClass}`}>
          <div className="flex items-center justify-between mb-3">
            <h4 className={`text-sm font-semibold ${textPrimary}`}>
              扫描结果 ({scanResult.skills.length} 个 Skills)
            </h4>
            <button
              onClick={() => setScanResult(null)}
              className={`text-xs ${textSecondary} hover:text-slate-700 dark:hover:text-slate-200`}
            >
              关闭
            </button>
          </div>

          <p className={`text-xs mb-3 ${textSecondary}`}>
            扫描路径: {scanResult.scanned_path}
          </p>

          {scanResult.errors.length > 0 && (
            <div className="mb-3 p-2 rounded-lg bg-red-50 dark:bg-red-900/20 text-xs text-red-600 dark:text-red-300">
              <div className="font-medium mb-1">扫描错误:</div>
              {scanResult.errors.map((err, i) => (
                <div key={i}>
                  {err.dir_name}: {err.error}
                </div>
              ))}
            </div>
          )}

          {scanResult.skills.length > 0 ? (
            <div className="space-y-2">
              {scanResult.skills.map((skill) => {
                const isInstalled = projectState?.skills_installed.includes(skill.name);
                return (
                  <div
                    key={skill.name}
                    className={`flex items-center justify-between p-3 rounded-lg ${
                      isDarkMode ? "bg-slate-900/50" : "bg-slate-50"
                    }`}
                  >
                    <div>
                      <div className={`font-medium text-sm ${textPrimary}`}>{skill.name}</div>
                      <div className={`text-xs ${textSecondary}`}>{skill.description}</div>
                    </div>
                    {isInstalled ? (
                      <span className="px-2 py-1 rounded text-xs bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300">
                        已安装
                      </span>
                    ) : (
                      <button
                        onClick={() => handleAddSkillToProject(skill.name)}
                        className="px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500 text-white hover:bg-emerald-600"
                      >
                        添加到项目
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <div className={`py-4 text-center ${textSecondary}`}>
              未发现项目 Skills（检查 .claude/skills/ 目录）
            </div>
          )}
        </div>
      )}
    </div>
  );
}
