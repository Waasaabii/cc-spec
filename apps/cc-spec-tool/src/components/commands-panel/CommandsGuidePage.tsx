// CommandsGuidePage.tsx - Commands 使用技巧页面
import { Icons } from "../icons/Icons";
import { COMMAND_USAGE_INFO, type CommandName } from "../../types/commands";

interface CommandsGuidePageProps {
    onClose: () => void;
    isDarkMode: boolean;
}

// 阶段图标映射
const stageIcons: Record<string, React.ReactNode> = {
    specify: <Icons.FileText />,
    clarify: <Icons.Users />,
    plan: <Icons.List />,
    apply: <Icons.Play />,
    accept: <Icons.CheckCircle />,
    archive: <Icons.Archive />,
};

// 阶段颜色映射
const stageColors: Record<string, { bg: string; text: string; border: string; darkBg: string; darkText: string; darkBorder: string }> = {
    specify: { bg: "bg-blue-50", text: "text-blue-700", border: "border-blue-200", darkBg: "bg-blue-900/20", darkText: "text-blue-300", darkBorder: "border-blue-700" },
    clarify: { bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-200", darkBg: "bg-amber-900/20", darkText: "text-amber-300", darkBorder: "border-amber-700" },
    plan: { bg: "bg-purple-50", text: "text-purple-700", border: "border-purple-200", darkBg: "bg-purple-900/20", darkText: "text-purple-300", darkBorder: "border-purple-700" },
    apply: { bg: "bg-green-50", text: "text-green-700", border: "border-green-200", darkBg: "bg-green-900/20", darkText: "text-green-300", darkBorder: "border-green-700" },
    accept: { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-200", darkBg: "bg-emerald-900/20", darkText: "text-emerald-300", darkBorder: "border-emerald-700" },
    archive: { bg: "bg-slate-50", text: "text-slate-700", border: "border-slate-200", darkBg: "bg-slate-800", darkText: "text-slate-300", darkBorder: "border-slate-600" },
};

export function CommandsGuidePage({ onClose, isDarkMode }: CommandsGuidePageProps) {
    const cardClass = isDarkMode
        ? "bg-slate-800 border-slate-700 shadow-sm"
        : "bg-white border-slate-200 shadow-sm";

    const textPrimary = isDarkMode ? "text-slate-100" : "text-slate-900";
    const textSecondary = isDarkMode ? "text-slate-400" : "text-slate-500";

    return (
        <div className="flex flex-col gap-8 pb-10">
            {/* 页面头部 */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className={`text-2xl font-bold ${textPrimary}`}>Commands 使用指南</h1>
                    <p className={`text-sm mt-1 ${textSecondary}`}>
                        cc-spec 提供标准化的 7 步工作流，帮助您高效管理 AI 辅助开发
                    </p>
                </div>
                <button
                    onClick={onClose}
                    className={`px-4 py-2 rounded-xl text-sm font-semibold transition-colors border ${isDarkMode ? "bg-transparent border-slate-600 text-slate-300 hover:bg-slate-800" : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"}`}
                >
                    返回
                </button>
            </div>

            {/* 工作流概览 */}
            <div className={`p-6 rounded-2xl border ${cardClass}`}>
                <h2 className={`text-lg font-semibold mb-4 ${textPrimary}`}>工作流概览</h2>
                <div className="flex flex-wrap items-center gap-2 text-sm">
                    {COMMAND_USAGE_INFO.map((cmd, idx) => {
                        const color = stageColors[cmd.stage];
                        return (
                            <div key={cmd.name} className="flex items-center gap-2">
                                <span className={`px-3 py-1.5 rounded-lg font-medium ${isDarkMode ? `${color.darkBg} ${color.darkText} border ${color.darkBorder}` : `${color.bg} ${color.text} border ${color.border}`}`}>
                                    {idx + 1}. {cmd.stage}
                                </span>
                                {idx < COMMAND_USAGE_INFO.length - 1 && (
                                    <span className={textSecondary}>→</span>
                                )}
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* Commands 详情卡片 */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {COMMAND_USAGE_INFO.map((cmd) => {
                    const color = stageColors[cmd.stage];
                    return (
                        <div key={cmd.name} className={`p-6 rounded-2xl border ${cardClass}`}>
                            {/* 头部 */}
                            <div className="flex items-start gap-4 mb-4">
                                <div className={`p-3 rounded-xl ${isDarkMode ? `${color.darkBg} ${color.darkText}` : `${color.bg} ${color.text}`}`}>
                                    {stageIcons[cmd.stage] || <Icons.Play />}
                                </div>
                                <div className="flex-1">
                                    <div className="flex items-center gap-2 mb-1">
                                        <h3 className={`text-lg font-bold ${textPrimary}`}>{cmd.name}</h3>
                                        <span className={`px-2 py-0.5 rounded text-xs font-semibold ${isDarkMode ? `${color.darkBg} ${color.darkText}` : `${color.bg} ${color.text}`}`}>
                                            {cmd.stage}
                                        </span>
                                    </div>
                                    <p className={`text-sm ${textSecondary}`}>{cmd.description}</p>
                                </div>
                            </div>

                            {/* 使用示例 */}
                            <div className="mb-4">
                                <div className={`text-xs font-semibold mb-2 ${textSecondary}`}>使用示例</div>
                                <code className={`block px-3 py-2 rounded-lg text-sm font-mono ${isDarkMode ? "bg-slate-900 text-emerald-400" : "bg-slate-100 text-emerald-600"}`}>
                                    {cmd.example}
                                </code>
                            </div>

                            {/* 使用技巧 */}
                            <div>
                                <div className={`text-xs font-semibold mb-2 ${textSecondary}`}>使用技巧</div>
                                <ul className="space-y-2">
                                    {cmd.tips.map((tip, idx) => (
                                        <li key={idx} className="flex items-start gap-2">
                                            <span className={`mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${isDarkMode ? color.darkText : color.text}`} style={{ backgroundColor: "currentColor" }} />
                                            <span className={`text-sm ${textSecondary}`}>{tip}</span>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* 额外提示 */}
            <div className={`p-6 rounded-2xl border ${cardClass}`}>
                <h2 className={`text-lg font-semibold mb-4 ${textPrimary}`}>常见问题</h2>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div>
                        <h3 className={`text-sm font-semibold mb-2 ${textPrimary}`}>如何开始使用？</h3>
                        <p className={`text-sm ${textSecondary}`}>
                            首先确保已完成项目初始化。在 Claude Code 中输入 <code className={`px-1.5 py-0.5 rounded ${isDarkMode ? "bg-slate-700" : "bg-slate-100"}`}>/cc-spec:specify</code> 开始描述需求，系统将引导您完成整个工作流。
                        </p>
                    </div>
                    <div>
                        <h3 className={`text-sm font-semibold mb-2 ${textPrimary}`}>可以跳过某些阶段吗？</h3>
                        <p className={`text-sm ${textSecondary}`}>
                            工作流设计为顺序执行，但对于简单任务，您可以使用 <code className={`px-1.5 py-0.5 rounded ${isDarkMode ? "bg-slate-700" : "bg-slate-100"}`}>/cc-spec:quick-delta</code> 快速记录小变更。
                        </p>
                    </div>
                    <div>
                        <h3 className={`text-sm font-semibold mb-2 ${textPrimary}`}>任务执行失败怎么办？</h3>
                        <p className={`text-sm ${textSecondary}`}>
                            使用 <code className={`px-1.5 py-0.5 rounded ${isDarkMode ? "bg-slate-700" : "bg-slate-100"}`}>/cc-spec:clarify</code> 审查任务结果，可以标记返工项让系统重新执行。
                        </p>
                    </div>
                    <div>
                        <h3 className={`text-sm font-semibold mb-2 ${textPrimary}`}>如何查看变更历史？</h3>
                        <p className={`text-sm ${textSecondary}`}>
                            使用 <code className={`px-1.5 py-0.5 rounded ${isDarkMode ? "bg-slate-700" : "bg-slate-100"}`}>/cc-spec:list</code> 查看活跃变更和归档记录，支持按类型和状态筛选。
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}
