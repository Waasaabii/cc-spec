# Phase 2 报告：事件通路主干与迁移策略

## 范围
- SSE 事件通路（/events + /ingest）
- Tauri event 通路（agent.* / 模块事件 emit）
- EventDispatcher 统一事件模型的落地点

## 现状
### SSE 通路
- main.rs 内置 `Broadcaster` 与 `handle_events/handle_ingest`，提供 `GET /events` 与 `POST /ingest`
- ingest 以 payload.type 作为 event name（默认 codex.stream），直接广播到 SSE 客户端
- 前端 App.tsx 只通过 EventSource 监听 codex.*

### Tauri event 通路
- Claude 事件通过 `app_handle.emit` 推送 `agent.*` 与 `agent.event`
- index/translation/export/sidecar 等模块也 emit 各自事件名
- 前端没有 `listen` 订阅（除 sidecar 的 cc-spec stream）

### EventDispatcher
- 已实现统一 AgentEvent 结构、历史缓存、过滤查询
- 当前未接入 main.rs 的 SSE 或 Tauri event 流，处于“孤立模块”状态

## 缺口与风险
- 双轨并行：SSE(codex.*) 与 Tauri event(agent.*) 无桥接，导致 CC/统一事件不可见
- 事件命名不统一：模块事件各自命名（index.* / translation.* / export.*），难以在前端统一消费
- EventDispatcher 未融入主链路，历史查询/过滤能力未被使用

## 迁移策略建议（分阶段）
### 方案 A：以 SSE 为主干（低改动、兼容现有）
1. 在 SSE ingest 侧增加“agent.* 兼容封装”
   - 对来自 CC/CX 的事件统一封装为 AgentEvent，再推送 SSE
2. 将 Claude 事件也桥接到 SSE
   - 在 claude.rs 内将 agent.event 同时写入 SSE 广播（通过共享 dispatcher/broadcaster）
3. 前端逐步切换为消费 agent.*（保留 codex.* 兼容）

### 方案 B：以 Tauri event 为主干（更现代，但前端改动大）
1. 前端新增 listen 订阅 agent.event，并重写状态更新逻辑
2. SSE 仅作为 legacy codex 流（可逐步废弃）
3. EventDispatcher 作为统一事件源 + 历史缓存入口

### 推荐路径
- 先采用方案 A（SSE 兼容）确保最小改动与可回滚
- 中期引入 EventDispatcher 统一封装，逐步让 SSE 只承载 AgentEvent
- 最终迁移到 Tauri event 为主干（可选）

## Phase 2 结论
- 当前主干仍是 SSE(codex.*)，要让 CC/统一事件可见，必须建立桥接或替换
- EventDispatcher 是统一事件模型的关键点，建议在 SSE 层引入它作为过渡层

## 参考证据
- `apps/cc-spec-tool/src-tauri/src/main.rs:446`
- `apps/cc-spec-tool/src-tauri/src/main.rs:477`
- `apps/cc-spec-tool/src-tauri/src/claude.rs:287`
- `apps/cc-spec-tool/src-tauri/src/events.rs:125`
