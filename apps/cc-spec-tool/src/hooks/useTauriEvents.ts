// hooks/useTauriEvents.ts - 监听 Tauri 事件的 Hook
// 用于接收后端 claude.rs 发出的 agent.* 事件

import { useEffect, useRef, useCallback } from "react";
import { listen, UnlistenFn } from "@tauri-apps/api/event";

/**
 * Tauri agent 事件负载
 * 对应 claude.rs 中的 AgentEvent 结构
 */
export interface TauriAgentEvent {
    event_type: string;
    source: string;
    session_id: string;
    run_id: string;
    data: {
        type?: string;
        content?: string | Array<{ type: string; text?: string; name?: string; input?: Record<string, unknown> }>;
        success?: boolean;
        error?: string;
        tool_use?: unknown;
        [key: string]: unknown;
    };
}

export interface UseTauriEventsOptions {
    onStarted?: (event: TauriAgentEvent) => void;
    onStream?: (event: TauriAgentEvent) => void;
    onCompleted?: (event: TauriAgentEvent) => void;
    onError?: (event: TauriAgentEvent) => void;
    onToolRequest?: (event: TauriAgentEvent) => void;
    onSessionEnded?: (event: TauriAgentEvent) => void;
    onStderr?: (event: { session_id: string; source: string; text: string }) => void;
    enabled?: boolean;
}

/**
 * 监听 Tauri 后端发出的 agent.* 事件
 * 这些事件来自 claude.rs 中的 app_handle.emit()
 */
export function useTauriEvents(options: UseTauriEventsOptions) {
    const {
        onStarted,
        onStream,
        onCompleted,
        onError,
        onToolRequest,
        onSessionEnded,
        onStderr,
        enabled = true,
    } = options;

    const unlistenersRef = useRef<UnlistenFn[]>([]);

    const setupListeners = useCallback(async () => {
        // 清理之前的监听器
        for (const unlisten of unlistenersRef.current) {
            unlisten();
        }
        unlistenersRef.current = [];

        if (!enabled) return;

        try {
            // agent.started - CC 启动
            if (onStarted) {
                const unlisten = await listen<TauriAgentEvent>("agent.started", (event) => {
                    onStarted(event.payload);
                });
                unlistenersRef.current.push(unlisten);
            }

            // agent.stream - CC 输出流
            if (onStream) {
                const unlisten = await listen<TauriAgentEvent>("agent.stream", (event) => {
                    onStream(event.payload);
                });
                unlistenersRef.current.push(unlisten);
            }

            // agent.completed - CC 完成
            if (onCompleted) {
                const unlisten = await listen<TauriAgentEvent>("agent.completed", (event) => {
                    onCompleted(event.payload);
                });
                unlistenersRef.current.push(unlisten);
            }

            // agent.error - CC 错误
            if (onError) {
                const unlisten = await listen<TauriAgentEvent>("agent.error", (event) => {
                    onError(event.payload);
                });
                unlistenersRef.current.push(unlisten);
            }

            // agent.tool.request - 工具请求
            if (onToolRequest) {
                const unlisten = await listen<TauriAgentEvent>("agent.tool.request", (event) => {
                    onToolRequest(event.payload);
                });
                unlistenersRef.current.push(unlisten);
            }

            // agent.session_ended - 会话结束
            if (onSessionEnded) {
                const unlisten = await listen<TauriAgentEvent>("agent.session_ended", (event) => {
                    onSessionEnded(event.payload);
                });
                unlistenersRef.current.push(unlisten);
            }

            // agent.stderr - 标准错误输出
            if (onStderr) {
                const unlisten = await listen<{ session_id: string; source: string; text: string }>(
                    "agent.stderr",
                    (event) => {
                        onStderr(event.payload);
                    }
                );
                unlistenersRef.current.push(unlisten);
            }
        } catch (err) {
            console.error("Failed to setup Tauri event listeners:", err);
        }
    }, [enabled, onStarted, onStream, onCompleted, onError, onToolRequest, onSessionEnded, onStderr]);

    useEffect(() => {
        setupListeners();

        return () => {
            for (const unlisten of unlistenersRef.current) {
                unlisten();
            }
            unlistenersRef.current = [];
        };
    }, [setupListeners]);

    return {
        reconnect: setupListeners,
    };
}
