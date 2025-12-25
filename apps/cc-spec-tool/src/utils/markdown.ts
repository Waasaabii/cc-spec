// shared markdown renderer
export function renderMarkdown(markdown: string): string {
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
