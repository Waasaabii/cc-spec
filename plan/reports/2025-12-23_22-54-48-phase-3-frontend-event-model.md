# Phase 3 报告：前端事件模型统一/适配

## 范围
- 前端事件类型定义与映射（types/events.ts）
- 实际运行时事件消费路径（App.tsx / SSE）

## 现状
- types/events.ts 定义了完整 agent.* 统一事件模型及 CC/CX 映射函数
- App.tsx 仍直接消费 codex.* 事件，未使用 mapCCEventToAgentEvent / mapCXEventToAgentEvent
- 前端未监听 Tauri event（agent.event），也未建立统一事件缓存/过滤逻辑

## 缺口
1. 类型定义与实际消费割裂
   - mapCCEventToAgentEvent / mapCXEventToAgentEvent 未被调用
   - AgentEventEnvelope 未进入 UI 运行态
2. 事件源不统一
   - SSE 仍以 codex.* 分发，无法直接复用 agent.* 结构
   - Tauri event 只在 sidecar 流式输出场景有 listen
3. UI 组件（Timeline）与事件模型未连接
   - Timeline.tsx 存在，但未被 App 引入

## 建议方向
- 在前端引入“统一事件层”
  - 将 SSE codex.* 转换为 AgentEventEnvelope 并存入统一 event store
  - 为 Tauri event（agent.event）提供同样入口
- UI 层统一消费 AgentEventEnvelope
  - RunCard/Timeline 从统一事件数据派生
- 迁移策略
  - 先建立兼容适配（codex.* → agent.*）
  - 再逐步替换 App.tsx 内直接处理逻辑

## 参考证据
- `apps/cc-spec-tool/src/types/events.ts:1`
- `apps/cc-spec-tool/src/App.tsx:171`
- `apps/cc-spec-tool/src/components/chat/Timeline.tsx:1`
