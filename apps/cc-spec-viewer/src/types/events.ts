// types/events.ts - 统一事件协议类型定义
// 与 Rust src-tauri/src/events.rs 对应

/**
 * Agent 来源标识
 * - claude: Claude Code (CC) 编排者
 * - codex: Codex (CX) 执行者
 * - system: 系统事件
 * - viewer: Viewer UI 事件
 */
export type AgentSource = "claude" | "codex" | "system" | "viewer";

/**
 * 事件通道类型
 */
export type EventChannel = "stdout" | "stderr" | "system" | "assistant";

/**
 * 统一事件信封
 * 所有 agent.* 事件的通用字段
 */
export interface AgentEventEnvelope {
    /** 事件唯一 ID，格式: evt_xxx */
    id: string;
    /** 事件时间戳 ISO 8601 */
    ts: string;
    /** 事件类型 */
    type: AgentEventType;
    /** 事件来源 */
    source: AgentSource;
    /** 会话 ID */
    session_id: string;
    /** 执行实例 ID */
    run_id: string;
    /** 事件序号，用于排序和去重 */
    seq: number;
    /** 事件负载 */
    payload: AgentEventPayload;
    /** 原始事件数据 (debug 模式) */
    raw?: Record<string, unknown>;
}

/**
 * 事件类型枚举
 */
export type AgentEventType =
    | "agent.started"
    | "agent.stream"
    | "agent.completed"
    | "agent.error"
    | "agent.heartbeat"
    | "agent.tool.request"
    | "agent.tool.approval"
    | "agent.tool.result"
    | "agent.tool.error";

/**
 * 事件负载联合类型
 */
export type AgentEventPayload =
    | StartedPayload
    | StreamPayload
    | CompletedPayload
    | ErrorPayload
    | HeartbeatPayload
    | ToolRequestPayload
    | ToolApprovalPayload
    | ToolResultPayload
    | ToolErrorPayload;

/**
 * agent.started 负载
 */
export interface StartedPayload {
    type: "started";
    /** 进程 ID */
    pid?: number;
    /** 项目根目录 */
    project_root?: string;
    /** 启动参数 */
    args?: string[];
}

/**
 * agent.stream 负载
 */
export interface StreamPayload {
    type: "stream";
    /** 输出文本 */
    text: string;
    /** 输出通道 */
    channel?: EventChannel;
    /** 是否为部分输出 */
    partial?: boolean;
}

/**
 * agent.completed 负载
 */
export interface CompletedPayload {
    type: "completed";
    /** 是否成功 */
    success: boolean;
    /** 退出码 */
    exit_code?: number;
    /** 执行时长 (秒) */
    duration?: number;
}

/**
 * agent.error 负载
 */
export interface ErrorPayload {
    type: "error";
    /** 错误消息 */
    message: string;
    /** 错误类型 */
    error_type?: string;
    /** 是否可恢复 */
    recoverable?: boolean;
}

/**
 * agent.heartbeat 负载
 */
export interface HeartbeatPayload {
    type: "heartbeat";
    /** 上一次活动时间 */
    last_activity?: string;
}

/**
 * agent.tool.request 负载
 */
export interface ToolRequestPayload {
    type: "tool_request";
    /** 工具命名空间.名称 */
    tool_name: string;
    /** 工具参数 */
    arguments?: Record<string, unknown>;
    /** 是否需要用户确认 */
    requires_approval?: boolean;
}

/**
 * agent.tool.approval 负载
 */
export interface ToolApprovalPayload {
    type: "tool_approval";
    /** 工具名称 */
    tool_name: string;
    /** 是否批准 */
    approved: boolean;
    /** 批准者 */
    approver?: string;
}

/**
 * agent.tool.result 负载
 */
export interface ToolResultPayload {
    type: "tool_result";
    /** 工具名称 */
    tool_name: string;
    /** 是否成功 */
    success: boolean;
    /** 执行结果 */
    result?: unknown;
    /** 执行时长 (毫秒) */
    duration_ms?: number;
}

/**
 * agent.tool.error 负载
 */
export interface ToolErrorPayload {
    type: "tool_error";
    /** 工具名称 */
    tool_name: string;
    /** 错误消息 */
    message: string;
    /** 错误码 */
    code?: string;
}

// ============================================================================
// 工具命名空间
// ============================================================================

/**
 * 工具命名空间
 * - claude.*: CC 内置工具
 * - codex.*: CX 内置工具
 * - cc-spec.*: cc-spec 工具
 */
export const TOOL_NAMESPACES = {
    claude: ["read", "write", "bash", "glob", "grep", "ls", "tree"],
    codex: ["shell_command", "apply_patch", "file_edit", "code_search"],
    "cc-spec": ["init-index", "update-index", "check-index", "apply", "plan", "chat"],
} as const;

// ============================================================================
// 简化类型 (用于 Rust 定义兼容)
// ============================================================================

/**
 * 简化的 AgentEvent 类型 (与 Rust events.rs 对应)
 */
export interface SimpleAgentEvent {
    type:
    | "agent.started"
    | "agent.stream"
    | "agent.tool.request"
    | "agent.tool.result"
    | "agent.completed"
    | "agent.error";
    session_id: string;
    source: string;
    // agent.stream 特有
    text?: string;
    // agent.tool.* 特有
    tool_name?: string;
    success?: boolean;
    // agent.error 特有
    message?: string;
}

// ============================================================================
// CC 原始事件映射 (stream-json 格式)
// ============================================================================

/**
 * CC stream-json 原始事件类型
 */
export type CCRawEventType = "system" | "assistant" | "user" | "result";

/**
 * CC stream-json 原始事件
 */
export interface CCRawEvent {
    type: CCRawEventType;
    content?: string | CCContentBlock[];
    timestamp?: string;
    // result 类型特有
    success?: boolean;
    error?: string;
}

/**
 * CC 内容块
 */
export interface CCContentBlock {
    type: "text" | "tool_use" | "tool_result";
    text?: string;
    name?: string;
    input?: Record<string, unknown>;
    tool_use_id?: string;
    content?: string;
}

/**
 * 将 CC 原始事件映射为统一事件
 */
export function mapCCEventToAgentEvent(
    raw: CCRawEvent,
    sessionId: string,
    runId: string,
    seq: number
): AgentEventEnvelope | null {
    const baseEvent = {
        id: `evt_${Date.now()}_${seq}`,
        ts: new Date().toISOString(),
        source: "claude" as AgentSource,
        session_id: sessionId,
        run_id: runId,
        seq,
        raw: raw as unknown as Record<string, unknown>,
    };

    switch (raw.type) {
        case "system":
            return {
                ...baseEvent,
                type: "agent.started",
                payload: { type: "started" },
            };

        case "assistant": {
            // 检查是否包含 tool_use
            if (Array.isArray(raw.content)) {
                const toolUse = raw.content.find((b) => b.type === "tool_use");
                if (toolUse) {
                    return {
                        ...baseEvent,
                        type: "agent.tool.request",
                        payload: {
                            type: "tool_request",
                            tool_name: `claude.${toolUse.name}`,
                            arguments: toolUse.input,
                        },
                    };
                }
                // 合并文本内容
                const text = raw.content
                    .filter((b) => b.type === "text")
                    .map((b) => b.text || "")
                    .join("");
                return {
                    ...baseEvent,
                    type: "agent.stream",
                    payload: { type: "stream", text, channel: "assistant" },
                };
            }
            return {
                ...baseEvent,
                type: "agent.stream",
                payload: {
                    type: "stream",
                    text: typeof raw.content === "string" ? raw.content : "",
                    channel: "assistant",
                },
            };
        }

        case "result":
            if (raw.success) {
                return {
                    ...baseEvent,
                    type: "agent.completed",
                    payload: { type: "completed", success: true },
                };
            } else {
                return {
                    ...baseEvent,
                    type: "agent.error",
                    payload: { type: "error", message: raw.error || "Unknown error" },
                };
            }

        case "user":
            // 用户输入，可以作为 stream 事件
            return {
                ...baseEvent,
                type: "agent.stream",
                payload: {
                    type: "stream",
                    text: typeof raw.content === "string" ? raw.content : "",
                    channel: "system",
                },
            };

        default:
            return null;
    }
}

// ============================================================================
// CX 事件映射
// ============================================================================

/**
 * CX SSE 事件类型 (codex.*)
 */
export type CXEventType =
    | "codex.started"
    | "codex.stream"
    | "codex.completed"
    | "codex.error"
    | "codex.tool_start"
    | "codex.tool_end";

/**
 * CX SSE 原始事件
 */
export interface CXRawEvent {
    type: CXEventType;
    session_id?: string;
    run_id?: string;
    pid?: number;
    project_root?: string;
    content?: string;
    success?: boolean;
    exit_code?: number;
    error?: string;
    tool_name?: string;
    duration?: string;
}

/**
 * 将 CX 原始事件映射为统一事件
 */
export function mapCXEventToAgentEvent(
    raw: CXRawEvent,
    seq: number
): AgentEventEnvelope | null {
    const sessionId = raw.session_id || "unknown";
    const runId = raw.run_id || sessionId;

    const baseEvent = {
        id: `evt_${Date.now()}_${seq}`,
        ts: new Date().toISOString(),
        source: "codex" as AgentSource,
        session_id: sessionId,
        run_id: runId,
        seq,
        raw: raw as unknown as Record<string, unknown>,
    };

    switch (raw.type) {
        case "codex.started":
            return {
                ...baseEvent,
                type: "agent.started",
                payload: {
                    type: "started",
                    pid: raw.pid,
                    project_root: raw.project_root,
                },
            };

        case "codex.stream":
            return {
                ...baseEvent,
                type: "agent.stream",
                payload: {
                    type: "stream",
                    text: raw.content || "",
                    channel: "stdout",
                },
            };

        case "codex.completed":
            return {
                ...baseEvent,
                type: "agent.completed",
                payload: {
                    type: "completed",
                    success: raw.success ?? true,
                    exit_code: raw.exit_code,
                },
            };

        case "codex.error":
            return {
                ...baseEvent,
                type: "agent.error",
                payload: {
                    type: "error",
                    message: raw.error || "Unknown error",
                },
            };

        case "codex.tool_start":
            return {
                ...baseEvent,
                type: "agent.tool.request",
                payload: {
                    type: "tool_request",
                    tool_name: `codex.${raw.tool_name || "unknown"}`,
                },
            };

        case "codex.tool_end":
            return {
                ...baseEvent,
                type: "agent.tool.result",
                payload: {
                    type: "tool_result",
                    tool_name: `codex.${raw.tool_name || "unknown"}`,
                    success: raw.success ?? true,
                },
            };

        default:
            return null;
    }
}
