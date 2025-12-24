# Phase 4 报告：session/run 状态映射核查

## 范围
- 前端 RunState 模型与 session_id/run_id 使用方式
- 后端事件 payload 中的 session_id/run_id 使用
- sessions.json 读取与 UI 对齐

## 现状
- App.tsx 以 SSE codex.* 事件驱动 RunState
- updateSession 通过 run_id + session_id 合并/更新
- RunCard 同时读取 session 状态（load_sessions → sessions.json）与 RunState
- viewer.ts 中 RunStatus 仅有 running/completed/error，但 RunCard 会将 sessions.json 的 state 映射为 running/done/failed/idle

## 发现
1. session_id/run_id 合并策略依赖 codex SSE 字段
   - 如果只有 run_id 或 session_id 缺失，会导致 runs 合并不稳定
2. sessions.json 的状态来源与事件状态并行
   - RunCard 优先使用 sessions.json 的 state 覆盖本地 RunState
   - 潜在状态漂移：SSE 更新与 sessions.json 轮询间可能不同步
3. 历史与实时模型未统一
   - history 使用 RunState 的 sessionId/id 作为 key
   - 与统一 AgentEvent 模型未衔接

## 缺口
- 未建立明确的“session_id/run_id 一致性规则”（何时用 run_id 聚合、何时以 session_id 为主）
- CC 事件（agent.*）没有映射路径，无法参与当前 session/run 逻辑

## 建议
- 明确统一规则：run_id 作为执行实例主键；session_id 用于会话聚合
- 在迁移到 agent.* 时，统一基于 AgentEvent.run_id 更新 UI
- sessions.json 仅作为回补/历史数据来源，不应覆盖实时状态（或需要优先级策略）

## 参考证据
- `apps/cc-spec-tool/src/App.tsx:190`
- `apps/cc-spec-tool/src/components/chat/RunCard.tsx:32`
- `apps/cc-spec-tool/src/utils/parse.ts:130`
