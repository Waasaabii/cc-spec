// utils/format.ts - 格式化工具函数

import type { Language } from "../types/viewer";

export const formatDuration = (duration?: number) => {
    if (!duration && duration !== 0) return "-";
    if (duration < 1) return `${Math.round(duration * 1000)}ms`;
    if (duration < 60) return `${duration.toFixed(1)}s`;
    const minutes = Math.floor(duration / 60);
    const seconds = Math.round(duration % 60);
    return `${minutes}m ${seconds}s`;
};

export const formatTimestamp = (value?: string, lang: Language = "zh") => {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.valueOf())) return value;
    return date.toLocaleTimeString(lang === "zh" ? "zh-CN" : "en-US", { hour12: false });
};

export const fmtElapsedCompact = (secs: number): string => {
    if (secs < 60) return `${secs}s`;
    if (secs < 3600) {
        const m = Math.floor(secs / 60);
        const s = secs % 60;
        return `${m}m ${s.toString().padStart(2, '0')}s`;
    }
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    return `${h}h ${m.toString().padStart(2, '0')}m ${s.toString().padStart(2, '0')}s`;
};

export const shortFileName = (path: string): string => path.split(/[/\\]/).slice(-2).join('/');

export const shortCommand = (cmd: string, maxLen = 60): string => {
    const cleaned = cmd.replace(/^bash\s+-lc\s+/, '').replace(/^['"]|['"]$/g, '');
    return cleaned.length > maxLen ? cleaned.slice(0, maxLen) + "..." : cleaned;
};

export const formatJsonCompact = (text: string): string | null => {
    try {
        const json = JSON.parse(text);
        return JSON.stringify(json, null, 0)
            .replace(/,/g, ', ')
            .replace(/:/g, ': ');
    } catch {
        return null;
    }
};

export const truncateOutputLines = (output: string, maxLines: number): string => {
    const lines = output.split('\n');
    if (lines.length <= maxLines * 2) {
        return output;
    }
    const head = lines.slice(0, maxLines);
    const tail = lines.slice(-maxLines);
    const omitted = lines.length - maxLines * 2;
    return [...head, `  ... (${omitted} lines omitted) ...`, ...tail].join('\n');
};
