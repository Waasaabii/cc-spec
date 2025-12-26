// SkillsPage.tsx - Skills 管理页面

import { useEffect, useState, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import type {
  ToolsConfig,
  Skill,
  SkillScanResult,
  SkillMetadata,
  SkillBody,
} from "../../types/skills";
import type { translations } from "../../types/viewer";
import { Icons } from "../icons/Icons";
import { ProjectSkillsPanel } from "./ProjectSkillsPanel";
import { renderMarkdown } from "../../utils/markdown";

interface SkillsPageProps {
  onClose: () => void;
  isDarkMode: boolean;
  currentProjectPath?: string | null;
  t: typeof translations["zh"];
}

// Skill 类型标签颜色映射
const skillTypeColors: Record<string, { bg: string; text: string }> = {
  workflow: { bg: "bg-purple-100 dark:bg-purple-900/30", text: "text-purple-700 dark:text-purple-300" },
  domain: { bg: "bg-blue-100 dark:bg-blue-900/30", text: "text-blue-700 dark:text-blue-300" },
  execution: { bg: "bg-emerald-100 dark:bg-emerald-900/30", text: "text-emerald-700 dark:text-emerald-300" },
};

// 默认颜色（用于未知类型）
const defaultColors = { bg: "bg-slate-100 dark:bg-slate-700", text: "text-slate-700 dark:text-slate-300" };

// Skill 类型中文映射
const skillTypeLabels: Record<string, string> = {
  workflow: "工作流",
  domain: "领域",
  execution: "执行",
};

export function SkillsPage({ onClose, isDarkMode, currentProjectPath, t }: SkillsPageProps) {
  const [config, setConfig] = useState<ToolsConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState<SkillScanResult | null>(null);
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null);
  const [skillBody, setSkillBody] = useState<Record<string, SkillBody>>({});
  const [loadingBody, setLoadingBody] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // 样式定义
  const cardClass = isDarkMode
    ? "bg-slate-800 border-slate-700"
    : "bg-white border-slate-200";
  const textPrimary = isDarkMode ? "text-slate-100" : "text-slate-900";
  const textSecondary = isDarkMode ? "text-slate-400" : "text-slate-500";
  const borderClass = isDarkMode ? "border-slate-700" : "border-slate-200";

  // 加载配置
  const loadConfig = useCallback(async () => {
    try {
      setLoading(true);
      const cfg = await invoke<ToolsConfig>("get_tools_config");
      setConfig(cfg);
      setError(null);
    } catch (err) {
      setError(`加载配置失败: ${err}`);
    } finally {
      setLoading(false);
    }
  }, []);

  // 初始化加载
  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  // 显示操作消息（自动消失）
  const showMessage = (type: "success" | "error", text: string) => {
    setActionMessage({ type, text });
    setTimeout(() => setActionMessage(null), 3000);
  };

  // 切换 Skill 启用状态
  const handleToggleSkill = async (skillName: string, currentEnabled: boolean) => {
    try {
      await invoke("toggle_skill_enabled", { skillName, enabled: !currentEnabled });
      await loadConfig();
      showMessage("success", `已${!currentEnabled ? "启用" : "禁用"} ${skillName}`);
    } catch (err) {
      showMessage("error", `操作失败: ${err}`);
    }
  };

  // 扫描用户 Skills 目录
  const handleScanUserSkills = async () => {
    try {
      setScanning(true);
      const result = await invoke<SkillScanResult>("scan_user_skills");
      setScanResult(result);
      showMessage("success", `扫描完成，发现 ${result.skills.length} 个 Skills`);
    } catch (err) {
      showMessage("error", `扫描失败: ${err}`);
    } finally {
      setScanning(false);
    }
  };

  // 加载 Skill Body（渐进式加载 L2）
  const handleLoadSkillBody = async (skillName: string) => {
    if (skillBody[skillName]) {
      // 已加载，直接展开/收起
      setExpandedSkill(expandedSkill === skillName ? null : skillName);
      return;
    }

    try {
      setLoadingBody(skillName);
      const body = await invoke<SkillBody>("load_skill_body_cmd", { skillName });
      setSkillBody((prev) => ({ ...prev, [skillName]: body }));
      setExpandedSkill(skillName);
    } catch (err) {
      showMessage("error", `加载内容失败: ${err}`);
    } finally {
      setLoadingBody(null);
    }
  };

  // 添加扫描结果中的 Skill
  const handleAddSkill = async (skill: Skill) => {
    try {
      await invoke("add_user_skill", { skill });
      await loadConfig();
      showMessage("success", `已添加 ${skill.name}`);
    } catch (err) {
      showMessage("error", `添加失败: ${err}`);
    }
  };

  // 移除用户 Skill
  const handleRemoveSkill = async (skillName: string) => {
    try {
      await invoke("remove_user_skill", { skillName });
      await loadConfig();
      showMessage("success", `已移除 ${skillName}`);
    } catch (err) {
      showMessage("error", `移除失败: ${err}`);
    }
  };

  const handleOpenToolsConfigInVSCode = async () => {
    try {
      await invoke("open_tools_config_in_vscode");
    } catch (err) {
      showMessage("error", `打开失败: ${err}`);
    }
  };

  const handleOpenSkillToolsYamlInVSCode = async (skillName: string) => {
    try {
      await invoke("open_skill_in_vscode", { skillName, target: "tools_yaml" });
    } catch (err) {
      showMessage("error", `打开失败: ${err}`);
    }
  };

  const handleOpenSkillMdInVSCode = async (skillName: string) => {
    try {
      await invoke("open_skill_in_vscode", { skillName, target: "skill_md" });
    } catch (err) {
      showMessage("error", `打开失败: ${err}`);
    }
  };

  // 渲染单个 Skill 卡片
  const renderSkillCard = (skill: Skill, isBuiltin: boolean) => {
    const colors = skillTypeColors[skill.skill_type] || defaultColors;
    const isExpanded = expandedSkill === skill.name;
    const body = skillBody[skill.name];

    return (
      <div
        key={skill.name}
        className={`p-4 rounded-xl border transition-all ${cardClass} ${skill.enabled
            ? isDarkMode
              ? "ring-1 ring-emerald-500/30"
              : "ring-1 ring-emerald-500/20"
            : "opacity-60"
          }`}
      >
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h4 className={`font-semibold ${textPrimary}`}>{skill.name}</h4>
              <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${colors.bg} ${colors.text}`}>
                {skillTypeLabels[skill.skill_type] || skill.skill_type}
              </span>
              {isBuiltin && (
                <span className="px-1.5 py-0.5 rounded text-xs bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                  内置
                </span>
              )}
              <span className={`text-xs ${textSecondary}`}>v{skill.version}</span>
            </div>
            <p className={`text-sm mt-1 ${textSecondary}`}>{skill.description}</p>

            {/* 触发器信息 */}
            {skill.triggers && (skill.triggers.keywords.length > 0 || skill.triggers.patterns.length > 0) && (
              <div className="mt-2 flex flex-wrap gap-1">
                {skill.triggers.keywords.slice(0, 5).map((kw) => (
                  <span
                    key={kw}
                    className={`px-1.5 py-0.5 rounded text-xs font-mono ${isDarkMode ? "bg-slate-700 text-slate-300" : "bg-slate-100 text-slate-600"
                      }`}
                  >
                    {kw}
                  </span>
                ))}
                {skill.triggers.keywords.length > 5 && (
                  <span className={`text-xs ${textSecondary}`}>+{skill.triggers.keywords.length - 5} more</span>
                )}
              </div>
            )}
          </div>

          <div className="flex items-center gap-2 ml-4">
            {/* 查看详情按钮 */}
            <button
              onClick={() => handleLoadSkillBody(skill.name)}
              disabled={loadingBody === skill.name}
              className={`px-2 py-1 rounded-lg text-xs border transition-colors ${borderClass} ${textSecondary} hover:bg-slate-50 dark:hover:bg-slate-700`}
            >
              {loadingBody === skill.name ? "加载中..." : isExpanded ? "收起" : "详情"}
            </button>

            {/* VS Code 打开（不在工具内编辑） */}
            {skill.source && (
              <button
                onClick={() => handleOpenSkillMdInVSCode(skill.name)}
                className={`px-2 py-1 rounded-lg text-xs border transition-colors ${borderClass} ${textSecondary} hover:bg-slate-50 dark:hover:bg-slate-700`}
                title="在 VS Code 打开 SKILL.md"
              >
                SKILL.md
              </button>
            )}
            <button
              onClick={() => handleOpenSkillToolsYamlInVSCode(skill.name)}
              className={`px-2 py-1 rounded-lg text-xs border transition-colors ${borderClass} ${textSecondary} hover:bg-slate-50 dark:hover:bg-slate-700`}
              title="在 VS Code 打开 tools.yaml 并定位到该 Skill（用于编辑触发器等）"
            >
              tools.yaml
            </button>

            {/* 启用/禁用开关 */}
            <button
              onClick={() => handleToggleSkill(skill.name, skill.enabled)}
              className={`relative w-11 h-6 rounded-full transition-colors ${skill.enabled
                  ? "bg-emerald-500"
                  : isDarkMode
                    ? "bg-slate-600"
                    : "bg-slate-300"
                }`}
            >
              <span
                className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${skill.enabled ? "left-6" : "left-1"
                  }`}
              />
            </button>

            {/* 移除按钮（仅用户 Skill） */}
            {!isBuiltin && (
              <button
                onClick={() => handleRemoveSkill(skill.name)}
                className="px-2 py-1 rounded-lg text-xs border border-red-500 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
              >
                移除
              </button>
            )}
          </div>
        </div>

        {/* 展开的详情内容 */}
        {isExpanded && body && (
          <div className={`mt-4 pt-4 border-t ${borderClass}`}>
            <div className={`text-xs mb-2 ${textSecondary}`}>
              内容 ({body.word_count} 词)
            </div>
            <div
              className={`text-xs p-3 rounded-lg overflow-x-auto max-h-96 overflow-y-auto prose prose-sm max-w-none ${isDarkMode ? "bg-slate-900 text-slate-300 prose-invert" : "bg-slate-50 text-slate-700"
                }`}
              dangerouslySetInnerHTML={{
                __html: renderMarkdown(body.content),
              }}
            />
          </div>
        )}
      </div>
    );
  };

  // 渲染扫描结果
  const renderScanResult = () => {
    if (!scanResult) return null;

    return (
      <div className={`p-4 rounded-xl border ${cardClass}`}>
        <div className="flex items-center justify-between mb-4">
          <h3 className={`text-sm font-semibold ${textPrimary}`}>
            扫描结果 ({scanResult.skills.length} 个 Skills)
          </h3>
          <button
            onClick={() => setScanResult(null)}
            className={`text-xs ${textSecondary} hover:text-slate-700 dark:hover:text-slate-200`}
          >
            关闭
          </button>
        </div>
        <p className={`text-xs mb-4 ${textSecondary}`}>
          扫描路径: {scanResult.scanned_path}
        </p>

        {scanResult.errors.length > 0 && (
          <div className="mb-4 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-xs text-red-600 dark:text-red-300">
            <div className="font-medium mb-1">扫描错误:</div>
            {scanResult.errors.map((err, i) => (
              <div key={i}>
                {err.dir_name}: {err.error}
              </div>
            ))}
          </div>
        )}

        {scanResult.skills.length > 0 && (
          <div className="space-y-2">
            {scanResult.skills.map((skill) => (
              <div
                key={skill.name}
                className={`flex items-center justify-between p-3 rounded-lg ${isDarkMode ? "bg-slate-900/50" : "bg-slate-50"
                  }`}
              >
                <div>
                  <div className={`font-medium text-sm ${textPrimary}`}>{skill.name}</div>
                  <div className={`text-xs ${textSecondary}`}>{skill.description}</div>
                </div>
                <button
                  onClick={() => handleAddSkill(skill)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500 text-white hover:bg-emerald-600"
                >
                  添加
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-6 pb-10">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className={`text-2xl font-bold ${textPrimary}`}>Skills 管理</h1>
          <p className={`text-sm mt-1 ${textSecondary}`}>
            管理自动触发的知识包，为 AI 提供领域上下文
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={handleScanUserSkills}
            disabled={scanning}
            className={`px-4 py-2 rounded-xl text-sm font-semibold transition-colors border ${borderClass} ${textSecondary} hover:bg-slate-50 dark:hover:bg-slate-800`}
          >
            {scanning ? "扫描中..." : "扫描目录"}
          </button>
          <button
            onClick={loadConfig}
            disabled={loading}
            className={`px-4 py-2 rounded-xl text-sm font-semibold transition-colors border ${borderClass} ${textSecondary} hover:bg-slate-50 dark:hover:bg-slate-800`}
          >
            刷新
          </button>
          <button
            onClick={onClose}
            className={`px-4 py-2 rounded-xl text-sm font-semibold transition-colors border ${isDarkMode
                ? "bg-transparent border-slate-600 text-slate-300 hover:bg-slate-800"
                : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
              }`}
          >
            返回
          </button>
        </div>
      </div>

      {/* 操作消息 */}
      {actionMessage && (
        <div
          className={`p-3 rounded-xl text-sm font-medium ${actionMessage.type === "error"
              ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300"
              : "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
            }`}
        >
          {actionMessage.text}
        </div>
      )}

      {/* 错误提示 */}
      {error && (
        <div className="p-3 rounded-xl text-sm font-medium bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300">
          {error}
        </div>
      )}

      {/* 扫描结果 */}
      {renderScanResult()}

      {loading && !config ? (
        <div className={`p-8 text-center ${textSecondary}`}>加载中...</div>
      ) : config ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* 左侧：统计信息 */}
          <div className="lg:col-span-2">
            <div className={`p-4 rounded-xl border ${cardClass}`}>
              <div className="grid grid-cols-4 gap-4">
                <div className={`p-3 rounded-lg ${isDarkMode ? "bg-slate-900/50" : "bg-slate-50"}`}>
                  <div className={`text-xs ${textSecondary}`}>内置 Skills</div>
                  <div className={`text-2xl font-bold ${textPrimary}`}>
                    {config.skills.builtin.length}
                  </div>
                </div>
                <div className={`p-3 rounded-lg ${isDarkMode ? "bg-slate-900/50" : "bg-slate-50"}`}>
                  <div className={`text-xs ${textSecondary}`}>用户 Skills</div>
                  <div className={`text-2xl font-bold ${textPrimary}`}>
                    {config.skills.user.length}
                  </div>
                </div>
                <div className={`p-3 rounded-lg ${isDarkMode ? "bg-slate-900/50" : "bg-slate-50"}`}>
                  <div className={`text-xs ${textSecondary}`}>已启用</div>
                  <div className={`text-2xl font-bold text-emerald-500`}>
                    {[...config.skills.builtin, ...config.skills.user].filter((s) => s.enabled).length}
                  </div>
                </div>
                <div className={`p-3 rounded-lg ${isDarkMode ? "bg-slate-900/50" : "bg-slate-50"}`}>
                  <div className={`text-xs ${textSecondary}`}>配置版本</div>
                  <div className={`text-2xl font-bold ${textPrimary}`}>{config.version}</div>
                </div>
              </div>
            </div>
          </div>

          {/* 内置 Skills */}
          <div>
            <h3 className={`text-lg font-semibold mb-4 ${textPrimary}`}>
              内置 Skills ({config.skills.builtin.length})
            </h3>
            <div className="space-y-3">
              {config.skills.builtin.map((skill) => renderSkillCard(skill, true))}
            </div>
          </div>

          {/* 用户 Skills */}
          <div>
            <h3 className={`text-lg font-semibold mb-4 ${textPrimary}`}>
              用户 Skills ({config.skills.user.length})
            </h3>
            {config.skills.user.length > 0 ? (
              <div className="space-y-3">
                {config.skills.user.map((skill) => renderSkillCard(skill, false))}
              </div>
            ) : (
              <div className={`p-6 rounded-xl border ${borderClass} text-center ${textSecondary}`}>
                <p>暂无用户 Skills</p>
                <p className="text-xs mt-2">点击"扫描目录"从 ~/.cc-spec/skills/ 导入</p>
              </div>
            )}
          </div>

          {/* 项目 Skills 状态 */}
          <div className="lg:col-span-2">
            <h3 className={`text-lg font-semibold mb-4 ${textPrimary}`}>当前项目 Skills</h3>
            <ProjectSkillsPanel
              projectPath={currentProjectPath || null}
              isDarkMode={isDarkMode}
              t={t}
            />
          </div>

          {/* 设置区域 */}
          <div className="lg:col-span-2">
            <div className={`p-4 rounded-xl border ${cardClass}`}>
              <h3 className={`text-lg font-semibold mb-4 ${textPrimary}`}>触发设置</h3>
              <div className="flex items-center justify-end mb-3">
                <button
                  onClick={handleOpenToolsConfigInVSCode}
                  className={`px-3 py-1.5 rounded-lg text-xs border transition-colors ${borderClass} ${textSecondary} hover:bg-slate-50 dark:hover:bg-slate-700`}
                  title="在 VS Code 打开 ~/.cc-spec/tools.yaml"
                >
                  <span className="inline-flex items-center gap-1.5">
                    <Icons.FileText />
                    VS Code 打开
                  </span>
                </button>
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className={`block text-sm font-medium mb-1 ${textPrimary}`}>
                    大小写敏感
                  </label>
                  <div className={`text-sm ${textSecondary}`}>
                    {config.trigger_rules.settings.case_sensitive ? "是" : "否"}
                  </div>
                </div>
                <div>
                  <label className={`block text-sm font-medium mb-1 ${textPrimary}`}>
                    最小关键词长度
                  </label>
                  <div className={`text-sm ${textSecondary}`}>
                    {config.trigger_rules.settings.min_keyword_length} 字符
                  </div>
                </div>
                <div>
                  <label className={`block text-sm font-medium mb-1 ${textPrimary}`}>
                    每次最大匹配数
                  </label>
                  <div className={`text-sm ${textSecondary}`}>
                    {config.trigger_rules.settings.max_matches_per_prompt}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
