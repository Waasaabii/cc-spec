// components/chat/Timeline.tsx - 统一时间线组件

import { useState, useMemo } from "react";
import Ansi from "ansi-to-react";
import { RenderContent } from "./RenderContent";
import { formatTimestamp } from "../../utils/format";
import type { StreamLine, Theme, Language, RunState } from "../../types/viewer";

type EventSource = "all" | "claude" | "codex";

interface TimelineEvent {
    id: string;
    runId: string;
    source: "claude" | "codex";
    timestamp?: string;
    line: StreamLine;
}

interface TimelineProps {
    runs: RunState[];
    theme: Theme;
    lang: Language;
}

interface EventGroupProps {
    runId: string;
    source: "claude" | "codex";
    events: TimelineEvent[];
    theme: Theme;
    lang: Language;
    defaultCollapsed?: boolean;
}

function SourceBadge({ source, theme }: { source: "claude" | "codex"; theme: Theme }) {
    const isClaude = source === "claude";
    const bgColor = isClaude
        ? (theme === "dark" ? "bg-orange-500/20 text-orange-300 border-orange-500/30" : "bg-orange-100 text-orange-700 border-orange-200")
        : (theme === "dark" ? "bg-blue-500/20 text-blue-300 border-blue-500/30" : "bg-blue-100 text-blue-700 border-blue-200");

    return (
        <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border ${bgColor}`}>
            {isClaude ? "CC" : "CX"}
        </span>
    );
}

function EventLine({ event, theme, isToolEvent }: { event: TimelineEvent; theme: Theme; isToolEvent: boolean }) {
    const { line, source } = event;

    const lineStyles: Record<StreamLine["type"], string> = {
        user: theme === "dark" ? "bg-indigo-500/20 border-l-4 border-indigo-300 px-4 py-2" : "bg-indigo-100 border-l-4 border-indigo-400 px-4 py-2",
        agent: theme === "dark" ? "text-slate-200" : "text-slate-800",
        tool_start: theme === "dark" ? "text-amber-400" : "text-amber-600",
        tool_end: "",
        output: theme === "dark" ? "text-slate-500 pl-4 text-[11px]" : "text-slate-600 pl-4 text-[11px]",
        file_op: theme === "dark" ? "text-emerald-400" : "text-emerald-600",
        thinking: "italic text-purple-400/60 pl-3 border-l border-purple-500/30",
        error: theme === "dark" ? "bg-rose-500/10 text-rose-300 px-2 py-1 rounded" : "bg-rose-100 text-rose-700 px-2 py-1 rounded",
        info: "text-slate-500 text-center text-[10px] opacity-50",
    };

    const getPrefix = () => {
        switch (line.type) {
            case "user": return <span className={theme === "dark" ? "text-indigo-300 font-bold" : "text-indigo-600 font-bold"}>›</span>;
            case "agent": return <span className={theme === "dark" ? "text-slate-500" : "text-slate-400"}>•</span>;
            case "tool_start": return <span className="animate-pulse">•</span>;
            case "tool_end": return <span className={`font-bold ${line.status === "success" ? "text-emerald-400" : "text-rose-400"}`}>{line.status === "success" ? "✓" : "✗"}</span>;
            case "file_op": return <span className="font-bold text-emerald-400">✓</span>;
            case "output": return <span className={theme === "dark" ? "text-slate-600" : "text-slate-500"}>└</span>;
            case "thinking": return <span className={theme === "dark" ? "text-slate-600" : "text-slate-500"}>•</span>;
            case "error": return <span className="font-bold text-rose-400">✗</span>;
            default: return null;
        }
    };

    return (
        <div className={`flex items-start gap-2 ${lineStyles[line.type] || ""} ${isToolEvent ? "opacity-70" : ""}`}>
            <div className="flex items-center gap-1.5 flex-shrink-0">
                <SourceBadge source={source} theme={theme} />
                {getPrefix()}
            </div>
            <div className="flex-1 min-w-0">
                {line.type === "agent" || line.type === "user" ? (
                    <RenderContent content={line.content} type={line.type} theme={theme} />
                ) : line.type === "output" ? (
                    <Ansi>{line.content}</Ansi>
                ) : (
                    <span>{line.content}</span>
                )}
                {line.duration && <span className={`ml-2 text-[10px] ${theme === "dark" ? "text-slate-500" : "text-slate-600"}`}>• {line.duration}</span>}
            </div>
        </div>
    );
}

function EventGroup({ runId, source, events, theme, lang, defaultCollapsed = false }: EventGroupProps) {
    const [collapsed, setCollapsed] = useState(defaultCollapsed);
    const toolEvents = events.filter(e => ["tool_start", "tool_end", "file_op", "output"].includes(e.line.type));
    const mainEvents = events.filter(e => !["tool_start", "tool_end", "file_op", "output"].includes(e.line.type));
    const hasToolEvents = toolEvents.length > 0;

    return (
        <div className={`rounded-lg border ${theme === "dark" ? "bg-slate-800/50 border-slate-700" : "bg-white border-slate-200"} mb-3`}>
            <div className={`flex items-center justify-between px-3 py-2 border-b ${theme === "dark" ? "border-slate-700" : "border-slate-200"}`}>
                <div className="flex items-center gap-2">
                    <SourceBadge source={source} theme={theme} />
                    <span className={`text-[11px] font-mono ${theme === "dark" ? "text-slate-400" : "text-slate-500"}`}>{runId.slice(0, 8)}</span>
                </div>
                {hasToolEvents && (
                    <button
                        onClick={() => setCollapsed(!collapsed)}
                        className={`text-[10px] px-2 py-0.5 rounded ${theme === "dark" ? "text-slate-400 hover:bg-slate-700" : "text-slate-500 hover:bg-slate-100"}`}
                    >
                        {collapsed ? `+ ${toolEvents.length} tools` : "- hide tools"}
                    </button>
                )}
            </div>
            <div className="p-3 space-y-1">
                {mainEvents.map((event, idx) => (
                    <EventLine key={`${event.id}-${idx}`} event={event} theme={theme} isToolEvent={false} />
                ))}
                {!collapsed && toolEvents.map((event, idx) => (
                    <EventLine key={`tool-${event.id}-${idx}`} event={event} theme={theme} isToolEvent={true} />
                ))}
            </div>
        </div>
    );
}

export function Timeline({ runs, theme, lang }: TimelineProps) {
    const [filter, setFilter] = useState<EventSource>("all");

    const events = useMemo(() => {
        const allEvents: TimelineEvent[] = [];
        runs.forEach(run => {
            const source: "claude" | "codex" = run.projectRoot?.includes("claude") ? "claude" : "codex";
            run.lines.forEach((line, idx) => {
                allEvents.push({
                    id: `${run.id}-${idx}`,
                    runId: run.id,
                    source,
                    timestamp: run.startedAt,
                    line,
                });
            });
        });
        return allEvents.filter(e => filter === "all" || e.source === filter);
    }, [runs, filter]);

    const groupedByRun = useMemo(() => {
        const groups = new Map<string, TimelineEvent[]>();
        events.forEach(event => {
            const list = groups.get(event.runId) || [];
            list.push(event);
            groups.set(event.runId, list);
        });
        return groups;
    }, [events]);

    const filterButtons: { value: EventSource; label: string }[] = [
        { value: "all", label: "All" },
        { value: "claude", label: "CC" },
        { value: "codex", label: "CX" },
    ];

    return (
        <div className="space-y-4">
            {/* Filter Bar */}
            <div className={`flex items-center gap-2 p-2 rounded-lg ${theme === "dark" ? "bg-slate-800/50" : "bg-slate-100"}`}>
                {filterButtons.map(btn => (
                    <button
                        key={btn.value}
                        onClick={() => setFilter(btn.value)}
                        className={`px-3 py-1 rounded text-[11px] font-semibold transition-colors ${filter === btn.value
                            ? (theme === "dark" ? "bg-slate-600 text-white" : "bg-white text-slate-800 shadow-sm")
                            : (theme === "dark" ? "text-slate-400 hover:text-slate-200" : "text-slate-500 hover:text-slate-700")
                        }`}
                    >
                        {btn.label}
                    </button>
                ))}
                <span className={`ml-auto text-[10px] ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>
                    {events.length} events
                </span>
            </div>

            {/* Event Groups */}
            <div className="space-y-2">
                {Array.from(groupedByRun.entries()).map(([runId, runEvents]) => (
                    <EventGroup
                        key={runId}
                        runId={runId}
                        source={runEvents[0]?.source || "codex"}
                        events={runEvents}
                        theme={theme}
                        lang={lang}
                        defaultCollapsed={runEvents.length > 10}
                    />
                ))}
            </div>

            {events.length === 0 && (
                <div className={`text-center py-8 ${theme === "dark" ? "text-slate-500" : "text-slate-400"}`}>
                    No events to display
                </div>
            )}
        </div>
    );
}
