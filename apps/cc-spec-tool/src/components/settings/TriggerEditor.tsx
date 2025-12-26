// TriggerEditor.tsx - 触发规则编辑器组件

import { useState, useCallback, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { Skill, SkillTrigger, MatchResult, SkillMatch } from "../../types/skills";
import type { translations } from "../../types/viewer";
import { Icons } from "../icons/Icons";

interface TriggerEditorProps {
  skill: Skill;
  isDarkMode: boolean;
  onSave: (skill: Skill) => Promise<void>;
  onClose: () => void;
  t: typeof translations['zh']; // 翻译对象
}

export function TriggerEditor({ skill, isDarkMode, onSave, onClose, t }: TriggerEditorProps) {
  const [keywords, setKeywords] = useState<string[]>(skill.triggers?.keywords || []);
  const [patterns, setPatterns] = useState<string[]>(skill.triggers?.patterns || []);
  const [newKeyword, setNewKeyword] = useState("");
  const [newPattern, setNewPattern] = useState("");
  const [testInput, setTestInput] = useState("");
  const [matchResult, setMatchResult] = useState<MatchResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [patternError, setPatternError] = useState<string | null>(null);

  // 样式定义
  const cardClass = isDarkMode
    ? "bg-slate-800 border-slate-700"
    : "bg-white border-slate-200";
  const textPrimary = isDarkMode ? "text-slate-100" : "text-slate-900";
  const textSecondary = isDarkMode ? "text-slate-400" : "text-slate-500";
  const borderClass = isDarkMode ? "border-slate-700" : "border-slate-200";
  const inputClass = `w-full px-3 py-2 rounded-lg text-sm border focus:outline-none focus:ring-2 focus:ring-opacity-50 transition-all ${isDarkMode
      ? "bg-slate-900 border-slate-700 text-slate-100 focus:ring-purple-500 focus:border-purple-500"
      : "bg-white border-slate-200 text-slate-800 focus:ring-blue-500 focus:border-blue-500"
    }`;
  const tagClass = isDarkMode
    ? "bg-slate-700 text-slate-200 border-slate-600"
    : "bg-slate-100 text-slate-700 border-slate-200";

  // 添加关键词
  const handleAddKeyword = () => {
    const trimmed = newKeyword.trim();
    if (!trimmed) return;
    if (keywords.includes(trimmed)) {
      setError(t.keywordExists);
      return;
    }
    setKeywords([...keywords, trimmed]);
    setNewKeyword("");
    setError(null);
  };

  // 移除关键词
  const handleRemoveKeyword = (kw: string) => {
    setKeywords(keywords.filter((k) => k !== kw));
  };

  // 验证正则表达式
  const validatePattern = (pattern: string): boolean => {
    try {
      new RegExp(pattern);
      return true;
    } catch {
      return false;
    }
  };

  // 添加正则模式
  const handleAddPattern = () => {
    const trimmed = newPattern.trim();
    if (!trimmed) return;
    if (!validatePattern(trimmed)) {
      setPatternError(t.invalidRegex);
      return;
    }
    if (patterns.includes(trimmed)) {
      setPatternError(t.patternExists);
      return;
    }
    setPatterns([...patterns, trimmed]);
    setNewPattern("");
    setPatternError(null);
  };

  // 移除正则模式
  const handleRemovePattern = (pattern: string) => {
    setPatterns(patterns.filter((p) => p !== pattern));
  };

  // 实时匹配测试
  const handleTest = useCallback(async () => {
    if (!testInput.trim()) {
      setMatchResult(null);
      return;
    }

    setTesting(true);
    try {
      const result = await invoke<MatchResult>("match_skills_cmd", {
        input: testInput,
      });
      setMatchResult(result);
    } catch (err) {
      console.error("匹配测试失败:", err);
    } finally {
      setTesting(false);
    }
  }, [testInput]);

  // 测试输入变化时自动测试（防抖）
  useEffect(() => {
    const timer = setTimeout(() => {
      if (testInput.trim()) {
        handleTest();
      } else {
        setMatchResult(null);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [testInput, handleTest]);

  // 保存修改
  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const updatedSkill: Skill = {
        ...skill,
        triggers: {
          keywords,
          patterns,
        },
      };
      await onSave(updatedSkill);
      onClose();
    } catch (err) {
      setError(`保存失败: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  // 渲染匹配结果中当前 Skill 的匹配
  const currentSkillMatch = matchResult?.matches.find((m) => m.skill.name === skill.name);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div
        className={`w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl border shadow-2xl ${cardClass}`}
      >
        {/* 头部 */}
        <div className={`sticky top-0 z-10 p-4 border-b ${borderClass} ${cardClass}`}>
          <div className="flex items-center justify-between">
            <div>
              <h2 className={`text-lg font-bold ${textPrimary}`}>
                编辑触发规则: {skill.name}
              </h2>
              <p className={`text-sm mt-0.5 ${textSecondary}`}>
                配置关键词和正则模式来触发此 Skill
              </p>
            </div>
            <button
              onClick={onClose}
              className={`p-2 rounded-lg transition-colors ${isDarkMode ? "hover:bg-slate-700" : "hover:bg-slate-100"
                }`}
            >
              <Icons.Close className="w-5 h-5" />
            </button>
          </div>
        </div>

        <div className="p-4 space-y-6">
          {/* 功能说明 */}
          <div className={`p-3 rounded-xl text-sm ${isDarkMode ? "bg-blue-900/20 border border-blue-500/30" : "bg-blue-50 border border-blue-200"}`}>
            <div className={`font-medium mb-1 ${isDarkMode ? "text-blue-300" : "text-blue-700"}`}>
              💡 什么是触发器？
            </div>
            <p className={`text-xs leading-relaxed ${isDarkMode ? "text-blue-200/80" : "text-blue-600"}`}>
              触发器用于自动激活 Skill。当用户的输入包含设定的<strong>关键词</strong>或匹配<strong>正则模式</strong>时，
              该 Skill 的知识内容会自动注入到 AI 的上下文中，帮助 AI 更好地理解和处理相关任务。
              匹配得分越高，优先级越高。
            </p>
          </div>

          {/* 错误提示 */}
          {error && (
            <div className="p-3 rounded-xl text-sm font-medium bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300">
              {error}
            </div>
          )}

          {/* 关键词编辑 */}
          <div>
            <h3 className={`text-sm font-semibold mb-3 ${textPrimary}`}>
              关键词 ({keywords.length})
              <span className={`ml-2 text-xs font-normal ${textSecondary}`}>
                每个匹配得 10 分
              </span>
            </h3>
            <div className="flex gap-2 mb-3">
              <input
                type="text"
                value={newKeyword}
                onChange={(e) => setNewKeyword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleAddKeyword()}
                placeholder={t.enterKeyword}
                className={inputClass}
              />
              <button
                onClick={handleAddKeyword}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${isDarkMode
                    ? "bg-purple-600 text-white hover:bg-purple-500"
                    : "bg-blue-600 text-white hover:bg-blue-500"
                  }`}
              >
                添加
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {keywords.length === 0 ? (
                <span className={`text-sm ${textSecondary}`}>暂无关键词</span>
              ) : (
                keywords.map((kw) => (
                  <span
                    key={kw}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm border ${tagClass}`}
                  >
                    {kw}
                    <button
                      onClick={() => handleRemoveKeyword(kw)}
                      className="opacity-60 hover:opacity-100"
                    >
                      <Icons.Close className="w-3 h-3" />
                    </button>
                  </span>
                ))
              )}
            </div>
          </div>

          {/* 正则模式编辑 */}
          <div>
            <h3 className={`text-sm font-semibold mb-3 ${textPrimary}`}>
              正则模式 ({patterns.length})
              <span className={`ml-2 text-xs font-normal ${textSecondary}`}>
                每个匹配得 20 分
              </span>
            </h3>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={newPattern}
                onChange={(e) => {
                  setNewPattern(e.target.value);
                  setPatternError(null);
                }}
                onKeyDown={(e) => e.key === "Enter" && handleAddPattern()}
                placeholder="输入正则表达式，按回车添加"
                className={`${inputClass} font-mono`}
              />
              <button
                onClick={handleAddPattern}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${isDarkMode
                    ? "bg-purple-600 text-white hover:bg-purple-500"
                    : "bg-blue-600 text-white hover:bg-blue-500"
                  }`}
              >
                添加
              </button>
            </div>
            {patternError && (
              <p className="text-xs text-red-500 mb-2">{patternError}</p>
            )}
            <div className="flex flex-wrap gap-2">
              {patterns.length === 0 ? (
                <span className={`text-sm ${textSecondary}`}>暂无正则模式</span>
              ) : (
                patterns.map((pattern) => (
                  <span
                    key={pattern}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm font-mono border ${tagClass}`}
                  >
                    {pattern}
                    <button
                      onClick={() => handleRemovePattern(pattern)}
                      className="opacity-60 hover:opacity-100"
                    >
                      <Icons.Close className="w-3 h-3" />
                    </button>
                  </span>
                ))
              )}
            </div>
          </div>

          {/* 实时匹配测试 */}
          <div className={`p-4 rounded-xl border ${borderClass} ${isDarkMode ? "bg-slate-900/50" : "bg-slate-50"}`}>
            <h3 className={`text-sm font-semibold mb-3 ${textPrimary}`}>
              实时匹配测试
            </h3>
            <textarea
              value={testInput}
              onChange={(e) => setTestInput(e.target.value)}
              placeholder="输入测试文本，实时查看匹配结果..."
              rows={3}
              className={`${inputClass} resize-none`}
            />

            {testing && (
              <div className={`mt-3 text-sm ${textSecondary}`}>测试中...</div>
            )}

            {matchResult && !testing && (
              <div className="mt-3 space-y-2">
                <div className={`text-xs ${textSecondary}`}>
                  共匹配到 {matchResult.matches.length} 个 Skills
                </div>

                {/* 当前 Skill 的匹配结果 */}
                {currentSkillMatch ? (
                  <div className={`p-3 rounded-lg border ${isDarkMode ? "bg-emerald-900/20 border-emerald-500/30" : "bg-emerald-50 border-emerald-200"
                    }`}>
                    <div className="flex items-center justify-between mb-2">
                      <span className={`font-medium ${isDarkMode ? "text-emerald-300" : "text-emerald-700"}`}>
                        {currentSkillMatch.skill.name}
                      </span>
                      <span className={`text-sm font-bold ${isDarkMode ? "text-emerald-400" : "text-emerald-600"}`}>
                        得分: {currentSkillMatch.score}
                      </span>
                    </div>
                    {currentSkillMatch.matched_keywords.length > 0 && (
                      <div className="text-xs mb-1">
                        <span className={textSecondary}>匹配关键词: </span>
                        <span className={isDarkMode ? "text-emerald-300" : "text-emerald-600"}>
                          {currentSkillMatch.matched_keywords.join(", ")}
                        </span>
                      </div>
                    )}
                    {currentSkillMatch.matched_patterns.length > 0 && (
                      <div className="text-xs">
                        <span className={textSecondary}>匹配模式: </span>
                        <span className={`font-mono ${isDarkMode ? "text-emerald-300" : "text-emerald-600"}`}>
                          {currentSkillMatch.matched_patterns.join(", ")}
                        </span>
                      </div>
                    )}
                  </div>
                ) : testInput.trim() ? (
                  <div className={`p-3 rounded-lg border ${isDarkMode ? "bg-slate-800 border-slate-700" : "bg-white border-slate-200"
                    }`}>
                    <span className={`text-sm ${textSecondary}`}>
                      当前 Skill 未匹配到此输入
                    </span>
                  </div>
                ) : null}

                {/* 其他匹配的 Skills */}
                {matchResult.matches.filter((m) => m.skill.name !== skill.name).length > 0 && (
                  <div className="mt-2">
                    <div className={`text-xs mb-1 ${textSecondary}`}>其他匹配的 Skills:</div>
                    <div className="space-y-1">
                      {matchResult.matches
                        .filter((m) => m.skill.name !== skill.name)
                        .slice(0, 3)
                        .map((match) => (
                          <div
                            key={match.skill.name}
                            className={`flex items-center justify-between px-2 py-1 rounded text-xs ${isDarkMode ? "bg-slate-800" : "bg-white"
                              }`}
                          >
                            <span className={textSecondary}>{match.skill.name}</span>
                            <span className={textSecondary}>得分: {match.score}</span>
                          </div>
                        ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* 底部按钮 */}
        <div className={`sticky bottom-0 p-4 border-t ${borderClass} ${cardClass}`}>
          <div className="flex justify-end gap-3">
            <button
              onClick={onClose}
              className={`px-4 py-2 rounded-xl text-sm font-semibold transition-colors border ${borderClass} ${textSecondary} hover:bg-slate-50 dark:hover:bg-slate-800`}
            >
              取消
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className={`px-4 py-2 rounded-xl text-sm font-semibold text-white shadow-md transition-all active:scale-95 ${saving
                  ? "bg-slate-500 cursor-wait"
                  : isDarkMode
                    ? "bg-purple-600 hover:bg-purple-500"
                    : "bg-blue-600 hover:bg-blue-500"
                }`}
            >
              {saving ? "保存中..." : "保存修改"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
