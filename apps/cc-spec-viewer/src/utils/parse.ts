// utils/parse.ts - 解析工具函数

import type { StreamLine, CodeChanges, RunState } from "../types/viewer";
import { MAX_LINES, TOOL_CALL_MAX_LINES } from "../types/viewer";
import { shortFileName, shortCommand, truncateOutputLines, formatJsonCompact } from "./format";

export const parseCodeChanges = (raw: string): CodeChanges | null => {
    try {
        const obj = JSON.parse(raw);
        if (obj.type === "item.completed") {
            const item = obj.item;
            if (item?.type === "file_edit" || item?.type === "file_change") {
                let added = 0, removed = 0, files = 0;

                if (item.changes && Array.isArray(item.changes)) {
                    files = item.changes.length;
                    for (const c of item.changes) {
                        added += c.lines_added || c.insertions || 0;
                        removed += c.lines_removed || c.deletions || 0;
                    }
                } else {
                    files = 1;
                    added = item.lines_added || item.insertions || 0;
                    removed = item.lines_removed || item.deletions || 0;
                }

                if (files > 0) {
                    return { filesChanged: files, linesAdded: added, linesRemoved: removed };
                }
            }
        }
        return null;
    } catch {
        return null;
    }
};

export const parseCodeBlocks = (text: string): Array<{ type: "text" | "code"; content: string; lang?: string }> => {
    const parts: Array<{ type: "text" | "code"; content: string; lang?: string }> = [];
    const codeBlockRegex = /```(\w*)\n?([\s\S]*?)```/g;
    let lastIndex = 0;
    let match;

    while ((match = codeBlockRegex.exec(text)) !== null) {
        if (match.index > lastIndex) {
            const before = text.slice(lastIndex, match.index).trim();
            if (before) parts.push({ type: "text", content: before });
        }
        parts.push({ type: "code", content: match[2].trim(), lang: match[1] || "text" });
        lastIndex = match.index + match[0].length;
    }

    if (lastIndex < text.length) {
        const after = text.slice(lastIndex).trim();
        if (after) parts.push({ type: "text", content: after });
    }
    return parts.length > 0 ? parts : [{ type: "text", content: text }];
};

export const parseStreamLine = (raw: string): StreamLine | null => {
    try {
        const obj = JSON.parse(raw);
        const type = obj.type;

        if (type === "item.started") {
            const item = obj.item;
            if (item?.type === "command_execution") {
                return { type: "tool_start", content: shortCommand(item.command || ""), status: "running" };
            }
            if (item?.type === "file_edit" || item?.type === "file_write") {
                return { type: "tool_start", content: `Edit ${shortFileName(item.file_path || item.path || "")}`, status: "running" };
            }
            if (item?.type === "file_read") {
                return { type: "tool_start", content: `Read ${shortFileName(item.file_path || item.path || "")}`, status: "running" };
            }
        }

        if (type === "item.completed") {
            const item = obj.item;

            if (item?.type === "reasoning" && item?.text) {
                return { type: "thinking", content: item.text };
            }

            if (item?.type === "agent_message" && item?.text) {
                return { type: "agent", content: item.text };
            }

            if (item?.type === "command_execution") {
                const cmd = item.command || "";
                const output = item.aggregated_output || "";
                const exitCode = item.exit_code;
                const duration = item.duration_s;
                const durationStr = duration ? `${duration.toFixed(1)}s` : "";
                const isSuccess = exitCode === 0;

                const isReadCmd = /Get-Content|cat |head |tail |less |more |type /i.test(cmd);
                if (isReadCmd && isSuccess) {
                    const lineCount = output.split('\n').length;
                    return {
                        type: "tool_end",
                        content: `Read ${lineCount} lines`,
                        status: "success",
                        duration: durationStr
                    };
                }

                const truncated = truncateOutputLines(output, TOOL_CALL_MAX_LINES);
                const formatted = formatJsonCompact(truncated) || truncated;
                return {
                    type: "tool_end",
                    content: shortCommand(cmd),
                    status: isSuccess ? "success" : "failed",
                    duration: durationStr
                };
            }

            if (item?.type === "file_edit" || item?.type === "file_change") {
                if (item.changes && Array.isArray(item.changes)) {
                    const fileList = item.changes.map((c: { path?: string; kind?: string }) =>
                        `${c.kind || "edit"} ${shortFileName(c.path || "")}`
                    ).join(", ");
                    return { type: "file_op", content: fileList, status: "success" };
                }
                return { type: "file_op", content: `Edit ${shortFileName(item.file_path || item.path || "")}`, status: "success" };
            }

            if (item?.type === "file_read") {
                return { type: "file_op", content: `Read ${shortFileName(item.file_path || item.path || "")}`, status: "success" };
            }
        }

        if (type === "error") {
            const msg = obj.message || obj.error || "unknown error";
            return { type: "error", content: msg };
        }

        return null;
    } catch {
        if (raw.trim()) return { type: "agent", content: raw };
        return null;
    }
};

export const historyKey = (run: RunState): string => run.sessionId || run.id;

export const normalizeHistoryRuns = (runs: RunState[]): RunState[] => runs.map((run) => {
    const runIds = Array.isArray(run.runIds) ? run.runIds : [];
    return {
        ...run,
        runIds: runIds.length > 0 ? runIds : [run.id],
        lines: Array.isArray(run.lines) ? run.lines.slice(-MAX_LINES) : [],
        turnCount: run.turnCount ?? 1,
        codeChanges: run.codeChanges ?? { filesChanged: 0, linesAdded: 0, linesRemoved: 0 },
    };
});

export const parseHistoryPayload = (raw: string): RunState[] | null => {
    try {
        const data = JSON.parse(raw) as RunState[];
        if (!Array.isArray(data)) return null;
        return normalizeHistoryRuns(data);
    } catch {
        return null;
    }
};

export const mergeHistoryRuns = (current: RunState[], loaded: RunState[]): RunState[] => {
    if (loaded.length === 0) return current;
    const existing = new Set(current.map(historyKey));
    const merged = [...current];
    let added = false;
    for (const run of loaded) {
        const key = historyKey(run);
        if (!existing.has(key)) {
            merged.push(run);
            existing.add(key);
            added = true;
        }
    }
    return added ? merged : current;
};

export const groupRunsByProject = (runs: RunState[]): Map<string, RunState[]> => {
    const grouped = new Map<string, RunState[]>();
    for (const run of runs) {
        if (!run.projectRoot) continue;
        const list = grouped.get(run.projectRoot);
        if (list) {
            list.push(run);
        } else {
            grouped.set(run.projectRoot, [run]);
        }
    }
    return grouped;
};
