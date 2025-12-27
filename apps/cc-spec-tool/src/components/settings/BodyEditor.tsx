// BodyEditor.tsx - Skill Body Markdown 编辑器

import { useState, useEffect, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { Skill, SkillBody, ToolsConfig } from "../../types/skills";

// 简单的 Markdown 渲染函数
function renderMarkdown(markdown: string): string {
  let html = markdown
    // 转义 HTML 特殊字符
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    // 代码块 (```code```)
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-slate-800 text-slate-100 p-3 rounded-lg overflow-x-auto my-2"><code>$2</code></pre>')
    // 行内代码 (`code`)
    .replace(/`([^`]+)`/g, '<code class="bg-slate-200 dark:bg-slate-700 px-1 py-0.5 rounded text-sm">$1</code>')
    // 标题
    .replace(/^### (.+)$/gm, '<h3 class="text-lg font-semibold mt-4 mb-2">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-xl font-bold mt-5 mb-3">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-2xl font-bold mt-6 mb-4">$1</h1>')
    // 粗体和斜体
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // 无序列表
    .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    // 有序列表 (简化处理)
    .replace(/^\d+\. (.+)$/gm, '<li class="ml-4 list-decimal">$1</li>')
    // 换行
    .replace(/\n\n/g, '</p><p class="my-2">')
    .replace(/\n/g, '<br/>');

  return `<div class="markdown-content"><p class="my-2">${html}</p></div>`;
}

interface BodyEditorProps {
  skill: Skill;
  isDarkMode: boolean;
  onSave: (updatedSkill: Skill) => Promise<void>;
  onClose: () => void;
}

export function BodyEditor({ skill, isDarkMode, onSave, onClose }: BodyEditorProps) {
  const [content, setContent] = useState<string>("");
  const [originalContent, setOriginalContent] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPreview, setIsPreview] = useState(false);

  // 样式
  const overlayClass = isDarkMode ? "bg-black/60" : "bg-black/40";
  const modalClass = isDarkMode ? "bg-slate-800 border-slate-700" : "bg-white border-slate-200";
  const textPrimary = isDarkMode ? "text-slate-100" : "text-slate-900";
  const textSecondary = isDarkMode ? "text-slate-400" : "text-slate-500";
  const borderClass = isDarkMode ? "border-slate-700" : "border-slate-200";
  const inputClass = isDarkMode
    ? "bg-slate-900 border-slate-700 text-slate-100 placeholder-slate-500"
    : "bg-white border-slate-300 text-slate-900 placeholder-slate-400";

  // 加载 Skill Body
  const loadBody = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const body = await invoke<SkillBody>("load_skill_body_cmd", { skillName: skill.name });
      setContent(body.content);
      setOriginalContent(body.content);
    } catch (err) {
      setError(`加载内容失败: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [skill.name]);

  useEffect(() => {
    loadBody();
  }, [loadBody]);

  // 保存
  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);
      await invoke<ToolsConfig>("update_skill_body", {
        skillName: skill.name,
        body: content,
      });
      // 更新 skill 对象并调用 onSave
      const updatedSkill = { ...skill, body: content };
      await onSave(updatedSkill);
      onClose();
    } catch (err) {
      setError(`保存失败: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  // 重置
  const handleReset = () => {
    setContent(originalContent);
  };

  // 是否有修改
  const hasChanges = content !== originalContent;

  // 统计
  const wordCount = content.split(/\s+/).filter(Boolean).length;
  const lineCount = content.split("\n").length;

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center ${overlayClass}`}
      onClick={onClose}
    >
      <div
        className={`w-[90vw] max-w-5xl h-[85vh] max-h-[90vh] rounded-2xl border shadow-2xl flex flex-col ${modalClass}`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="flex items-center justify-between p-5 border-b border-inherit">
          <div>
            <h2 className={`text-xl font-bold ${textPrimary}`}>
              编辑 Skill 内容
            </h2>
            <p className={`text-sm mt-1 ${textSecondary}`}>
              {skill.name} - Markdown 格式
            </p>
          </div>
          <div className="flex items-center gap-2">
            {/* 预览切换 */}
            <button
              onClick={() => setIsPreview(!isPreview)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${isPreview
                ? "bg-purple-500 text-white"
                : isDarkMode
                  ? "bg-slate-700 text-slate-300 hover:bg-slate-600"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                }`}
            >
              {isPreview ? "编辑" : "预览"}
            </button>
            <button
              onClick={onClose}
              className={`p-2 rounded-lg transition-colors ${isDarkMode ? "hover:bg-slate-700" : "hover:bg-slate-100"
                }`}
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* 内容区 */}
        {/* 内容区 */}
        <div className="flex-1 min-h-0 overflow-hidden p-5 flex flex-col">
          {loading ? (
            <div className={`flex items-center justify-center h-full ${textSecondary}`}>
              加载中...
            </div>
          ) : error && !content ? (
            <div className="p-4 rounded-lg bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-300 text-sm">
              {error}
            </div>
          ) : isPreview ? (
            // 预览模式 - 简单 Markdown 渲染
            <div
              className={`flex-1 overflow-y-auto p-4 rounded-xl border ${borderClass
                } ${isDarkMode ? "bg-slate-900" : "bg-slate-50"
                }`}
            >
              <div
                className={`prose prose-sm max-w-none ${isDarkMode ? "prose-invert" : ""
                  }`}
                dangerouslySetInnerHTML={{
                  __html: renderMarkdown(content),
                }}
              />
            </div>
          ) : (
            // 编辑模式
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="在这里编写 Markdown 内容..."
              className={`flex-1 w-full resize-none rounded-xl border p-4 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 overflow-y-auto ${inputClass}`}
              spellCheck={false}
            />
          )}
        </div>

        {/* 错误提示 */}
        {error && content && (
          <div className="px-5 pb-2">
            <div className="p-3 rounded-lg bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-300 text-sm">
              {error}
            </div>
          </div>
        )}

        {/* 底部 */}
        <div className="flex items-center justify-between p-5 border-t border-inherit">
          <div className={`text-sm ${textSecondary}`}>
            {wordCount} 词 / {lineCount} 行
            {hasChanges && (
              <span className="ml-3 text-amber-500">* 有未保存的修改</span>
            )}
          </div>
          <div className="flex gap-3">
            <button
              onClick={handleReset}
              disabled={!hasChanges}
              className={`px-4 py-2 rounded-xl text-sm font-medium transition-colors border ${hasChanges
                ? isDarkMode
                  ? "border-slate-600 text-slate-300 hover:bg-slate-700"
                  : "border-slate-300 text-slate-600 hover:bg-slate-50"
                : "border-slate-200 dark:border-slate-700 text-slate-400 cursor-not-allowed"
                }`}
            >
              重置
            </button>
            <button
              onClick={onClose}
              className={`px-4 py-2 rounded-xl text-sm font-medium transition-colors border ${isDarkMode
                ? "border-slate-600 text-slate-300 hover:bg-slate-700"
                : "border-slate-300 text-slate-600 hover:bg-slate-50"
                }`}
            >
              取消
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !hasChanges}
              className={`px-4 py-2 rounded-xl text-sm font-semibold transition-colors ${saving || !hasChanges
                ? "bg-slate-200 dark:bg-slate-700 text-slate-400 cursor-not-allowed"
                : "bg-[var(--accent)] text-white hover:brightness-110"
                }`}
            >
              {saving ? "保存中..." : "保存"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
