use serde::{Deserialize, Serialize};
use std::collections::VecDeque;
use std::sync::{Arc, RwLock};
use tokio::sync::broadcast;

/// 历史缓存容量
const HISTORY_CAPACITY: usize = 1000;

/// Agent 来源
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum AgentSource {
    Claude,
    Codex,
    System,
    Viewer,
}

impl Default for AgentSource {
    fn default() -> Self {
        Self::System
    }
}

/// 统一事件结构
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AgentEvent {
    /// 事件唯一 ID
    pub id: String,
    /// 事件时间戳 ISO 8601
    pub ts: String,
    /// 事件类型
    #[serde(flatten)]
    pub event_type: AgentEventType,
    /// 事件来源
    pub source: AgentSource,
    /// 会话 ID
    pub session_id: String,
    /// 执行实例 ID
    pub run_id: String,
    /// 事件序号
    pub seq: u64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum AgentEventType {
    #[serde(rename = "agent.started")]
    Started {
        #[serde(skip_serializing_if = "Option::is_none")]
        pid: Option<u32>,
        #[serde(skip_serializing_if = "Option::is_none")]
        project_root: Option<String>,
    },

    #[serde(rename = "agent.stream")]
    Stream {
        text: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        channel: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        partial: Option<bool>,
    },

    #[serde(rename = "agent.tool.request")]
    ToolRequest {
        tool_name: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        arguments: Option<serde_json::Value>,
        #[serde(skip_serializing_if = "Option::is_none")]
        requires_approval: Option<bool>,
    },

    #[serde(rename = "agent.tool.result")]
    ToolResult {
        tool_name: String,
        success: bool,
        #[serde(skip_serializing_if = "Option::is_none")]
        result: Option<serde_json::Value>,
        #[serde(skip_serializing_if = "Option::is_none")]
        duration_ms: Option<u64>,
    },

    #[serde(rename = "agent.completed")]
    Completed {
        success: bool,
        #[serde(skip_serializing_if = "Option::is_none")]
        exit_code: Option<i32>,
        #[serde(skip_serializing_if = "Option::is_none")]
        duration: Option<f64>,
    },

    #[serde(rename = "agent.error")]
    Error {
        message: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        error_type: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        recoverable: Option<bool>,
    },

    #[serde(rename = "agent.heartbeat")]
    Heartbeat {
        #[serde(skip_serializing_if = "Option::is_none")]
        last_activity: Option<String>,
    },
}

/// 事件查询参数
#[derive(Clone, Debug, Deserialize)]
pub struct EventQuery {
    /// 过滤的会话 ID
    pub session_id: Option<String>,
    /// 过滤的执行实例 ID
    pub run_id: Option<String>,
    /// 起始序号（不包含）
    pub after_seq: Option<u64>,
    /// 最大返回数量
    pub limit: Option<usize>,
    /// 过滤的事件类型
    pub types: Option<Vec<String>>,
}

/// 事件分发器
pub struct EventDispatcher {
    sender: broadcast::Sender<AgentEvent>,
    /// 环形历史缓存
    history: Arc<RwLock<VecDeque<AgentEvent>>>,
    /// 序号计数器
    seq_counter: Arc<RwLock<u64>>,
}

impl EventDispatcher {
    pub fn new() -> Self {
        let (sender, _) = broadcast::channel(100);
        Self {
            sender,
            history: Arc::new(RwLock::new(VecDeque::with_capacity(HISTORY_CAPACITY))),
            seq_counter: Arc::new(RwLock::new(0)),
        }
    }

    /// 生成下一个序号
    fn next_seq(&self) -> u64 {
        let mut counter = self.seq_counter.write().unwrap();
        *counter += 1;
        *counter
    }

    /// 生成事件 ID
    fn generate_id(&self, seq: u64) -> String {
        format!("evt_{:012}", seq)
    }

    /// 发布事件（自动添加元数据）
    pub fn publish_raw(
        &self,
        event_type: AgentEventType,
        source: AgentSource,
        session_id: String,
        run_id: String,
    ) -> AgentEvent {
        let seq = self.next_seq();
        let event = AgentEvent {
            id: self.generate_id(seq),
            ts: chrono::Utc::now().to_rfc3339(),
            event_type,
            source,
            session_id,
            run_id,
            seq,
        };
        self.publish(event.clone());
        event
    }

    /// 发布完整事件
    pub fn publish(&self, event: AgentEvent) {
        // 添加到历史缓存
        {
            let mut history = self.history.write().unwrap();
            if history.len() >= HISTORY_CAPACITY {
                history.pop_front();
            }
            history.push_back(event.clone());
        }
        // 广播给订阅者
        let _ = self.sender.send(event);
    }

    /// 订阅事件流
    pub fn subscribe(&self) -> broadcast::Receiver<AgentEvent> {
        self.sender.subscribe()
    }

    /// 查询历史事件
    pub fn query(&self, query: EventQuery) -> Vec<AgentEvent> {
        let history = self.history.read().unwrap();
        let limit = query.limit.unwrap_or(100).min(500);

        history
            .iter()
            .filter(|e| {
                // 过滤 session_id
                if let Some(ref sid) = query.session_id {
                    if &e.session_id != sid {
                        return false;
                    }
                }
                // 过滤 run_id
                if let Some(ref rid) = query.run_id {
                    if &e.run_id != rid {
                        return false;
                    }
                }
                // 过滤 after_seq
                if let Some(after) = query.after_seq {
                    if e.seq <= after {
                        return false;
                    }
                }
                // 过滤事件类型
                if let Some(ref types) = query.types {
                    let event_type_str = match &e.event_type {
                        AgentEventType::Started { .. } => "agent.started",
                        AgentEventType::Stream { .. } => "agent.stream",
                        AgentEventType::ToolRequest { .. } => "agent.tool.request",
                        AgentEventType::ToolResult { .. } => "agent.tool.result",
                        AgentEventType::Completed { .. } => "agent.completed",
                        AgentEventType::Error { .. } => "agent.error",
                        AgentEventType::Heartbeat { .. } => "agent.heartbeat",
                    };
                    if !types.iter().any(|t| t == event_type_str) {
                        return false;
                    }
                }
                true
            })
            .take(limit)
            .cloned()
            .collect()
    }

    /// 获取最新序号
    pub fn last_seq(&self) -> u64 {
        *self.seq_counter.read().unwrap()
    }

    /// 清空历史
    pub fn clear_history(&self) {
        let mut history = self.history.write().unwrap();
        history.clear();
    }
}

impl Default for EventDispatcher {
    fn default() -> Self {
        Self::new()
    }
}

// ============================================================================
// 兼容旧版简化事件类型
// ============================================================================

/// 旧版简化事件类型（保持向后兼容）
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum SimpleAgentEvent {
    #[serde(rename = "agent.started")]
    Started { session_id: String, source: String },

    #[serde(rename = "agent.stream")]
    Stream {
        session_id: String,
        source: String,
        text: String,
    },

    #[serde(rename = "agent.tool.request")]
    ToolRequest {
        session_id: String,
        source: String,
        tool_name: String,
    },

    #[serde(rename = "agent.tool.result")]
    ToolResult {
        session_id: String,
        source: String,
        success: bool,
    },

    #[serde(rename = "agent.completed")]
    Completed {
        session_id: String,
        source: String,
        success: bool,
    },

    #[serde(rename = "agent.error")]
    Error {
        session_id: String,
        source: String,
        message: String,
    },
}

impl From<&AgentEvent> for SimpleAgentEvent {
    fn from(event: &AgentEvent) -> Self {
        let source = match event.source {
            AgentSource::Claude => "claude",
            AgentSource::Codex => "codex",
            AgentSource::System => "system",
            AgentSource::Viewer => "viewer",
        }
        .to_string();

        match &event.event_type {
            AgentEventType::Started { .. } => SimpleAgentEvent::Started {
                session_id: event.session_id.clone(),
                source,
            },
            AgentEventType::Stream { text, .. } => SimpleAgentEvent::Stream {
                session_id: event.session_id.clone(),
                source,
                text: text.clone(),
            },
            AgentEventType::ToolRequest { tool_name, .. } => SimpleAgentEvent::ToolRequest {
                session_id: event.session_id.clone(),
                source,
                tool_name: tool_name.clone(),
            },
            AgentEventType::ToolResult { success, .. } => SimpleAgentEvent::ToolResult {
                session_id: event.session_id.clone(),
                source,
                success: *success,
            },
            AgentEventType::Completed { success, .. } => SimpleAgentEvent::Completed {
                session_id: event.session_id.clone(),
                source,
                success: *success,
            },
            AgentEventType::Error { message, .. } => SimpleAgentEvent::Error {
                session_id: event.session_id.clone(),
                source,
                message: message.clone(),
            },
            AgentEventType::Heartbeat { .. } => SimpleAgentEvent::Started {
                session_id: event.session_id.clone(),
                source,
            },
        }
    }
}
