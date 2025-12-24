---
mode: plan
cwd: C:\develop\cc-spec
task: Viewer 功能连线与注册核查计划
complexity: complex
planning_method: builtin
created_at: 2025-12-23T22:22:03.1166387+08:00
---

# Plan: Viewer 功能连线与注册核查

🎯 任务概述
当前 tasks 已标注完成，但 Viewer 侧多项功能（事件、命令、UI）可能未真正连线与注册。此计划用于系统性调研现状、定位断点，并产出可执行的集成与验证步骤，确保 CC/CX 与 Viewer 端功能完整闭环。

📋 执行计划
1. 盘点后端命令/事件与前端消费路径，建立“功能-命令-事件-UI”对照表，明确已连通与缺口。
2. 明确事件通路的主干（SSE vs Tauri event），制定统一事件封装与兼容迁移策略，补齐 CC/CX 事件分发入口。
3. 统一前端事件消费模型（agent.* 为主），补充适配层以兼容 codex.*，并更新类型定义与解析逻辑。
4. 校验会话/运行态模型在前后端的映射关系（session_id/run_id），补齐状态同步与展示逻辑。
5. 逐项验证并连线功能模块：索引提示/skills 安装、翻译、数据库/导出、sidecar 调用、并发控制与设置持久化。
6. 校验 Tauri invoke 注册与前端调用覆盖，新增遗漏的调用入口与错误处理分支。
7. 制定验证流程：最小手工回归（CC 启动→CX 调用→暂停/停止→事件回放）+ 关键命令 smoke 测试。
8. 输出验收清单与里程碑，更新任务追踪与风险标注，形成可跟踪交付计划。

⚠️ 风险与注意事项
- 事件通路双轨（SSE/Tauri）并存期间可能出现重复/丢失，需要明确去重与过渡策略。
- CC/CX 状态模型与前端 UI 的映射差异可能导致状态不同步或展示错乱。
- 翻译/数据库/sidecar 涉及外部依赖与性能，需预留降级与错误提示路径。

📎 参考
- `apps/cc-spec-tool/src-tauri/src/main.rs:446`
- `apps/cc-spec-tool/src-tauri/src/main.rs:888`
- `apps/cc-spec-tool/src-tauri/src/claude.rs:288`
- `apps/cc-spec-tool/src/App.tsx:171`
- `apps/cc-spec-tool/src/types/events.ts:362`
