# 完成报告：P2 事件协议统一接入

## 完成内容
- EventDispatcher 接入 /ingest 流程，codex.* 映射为 agent.* 并同步推送 SSE
- 保持原 codex.* 事件不变，新增 agent.* 统一事件输出

## 代码变更
- `apps/cc-spec-tool/src-tauri/src/main.rs`
- `apps/cc-spec-tool/src-tauri/src/events.rs`

## 风险
- agent.* 与 codex.* 同时输出，前端若重复消费需自行选择协议
- codex.user_input 被映射为 agent.stream(channel=user_input)，语义与真实输出略有差异

## 后续步骤
- P3：前端信息架构/页面重构优化（项目导航/主页拆分）

## 参考
- `apps/cc-spec-tool/src-tauri/src/main.rs:515`
- `apps/cc-spec-tool/src-tauri/src/main.rs:985`
- `apps/cc-spec-tool/src-tauri/src/events.rs:156`
