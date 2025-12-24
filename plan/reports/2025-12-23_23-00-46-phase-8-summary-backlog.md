# Phase 8 报告：缺口汇总与执行建议

## 缺口总览（按优先级）
### P0 事件链路统一
- 双轨：SSE(codex.*) 与 Tauri event(agent.*) 未桥接
- EventDispatcher 未接入主链路
- 前端仅消费 codex.*，CC/统一事件不可见

### P1 前端模型与 UI 接入
- types/events.ts 与实际消费割裂
- Timeline/IndexPrompt/TranslateButton/Skills/Sidecar Hooks 未接入
- Settings/Viewer 类型与 Hooks 重复定义

### P1 会话与状态一致性
- session_id/run_id 合并策略不清
- sessions.json 与 SSE 状态覆盖导致漂移风险

### P2 功能入口缺失
- CC 启动/对话 UI 缺失（start_claude 系列）
- 数据库/导出/索引状态/翻译下载/并发队列控制缺少入口

## 建议执行顺序（建议里程碑）
1. 事件主干统一（SSE 兼容路线）
   - 引入 EventDispatcher → SSE 推送 AgentEvent
   - codex.* 映射为 agent.*（保留兼容）
2. 前端统一事件层
   - 建立 AgentEvent store
   - App.tsx 逐步替换 codex.* 直接处理
3. CC 接入
   - 基础 UI 触发 start_claude/send/stop
   - 事件落到统一事件层
4. 模块连线
   - IndexPrompt/Skills/Translation 下载与缓存
   - Database/Export/Sidecar
   - 并发队列控制
5. 会话模型一致性收敛
   - run_id 为主键、session_id 作为聚合
   - sessions.json 只做回补
6. 验证/回归
   - 按 Phase 7 清单执行

## 交付清单（建议）
- 统一事件协议落地与迁移说明
- Viewer UI 入口与设置面板补齐
- 关键命令 smoke 测试

## 参考
- `plan/reports/2025-12-23_22-34-38-phase-1-command-event-ui-mapping.md`
- `plan/reports/2025-12-23_22-53-51-phase-2-event-pipeline-strategy.md`
- `plan/reports/2025-12-23_22-59-11-phase-6-tauri-invoke-coverage.md`
