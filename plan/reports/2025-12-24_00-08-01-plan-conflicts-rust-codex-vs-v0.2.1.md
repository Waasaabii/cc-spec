# 计划冲突调研：Rust Codex + 系统终端 Claude vs v0.2.1 既定方案

## 冲突清单（结论）
1) Viewer 内置 CC 对话 vs 系统终端 Claude
- v0.2.1 目标：Viewer 内直接与 CC 对话、作为主入口。`
  参考：`docs/plan/cc-spec-v0.2.1/proposal.md:38`, `docs/plan/cc-spec-v0.2.1/proposal.md:119`
- 新方案：Claude 在系统终端启动（不内嵌、不在 Viewer 内显示输出）。
- 影响：W2 CC 集成相关任务（claude.rs + start_claude + UI 对话区）将被降级或替换。`
  参考：`docs/plan/cc-spec-v0.2.1/tasks.md:183`, `docs/plan/cc-spec-v0.2.1/tasks.md:225`

2) 统一时间线/输出分离目标
- v0.2.1 要求 CC/CX 输出统一在 Viewer 显示、可分离/过滤。`
  参考：`docs/plan/cc-spec-v0.2.1/proposal.md:69`, `docs/plan/cc-spec-v0.2.1/proposal.md:116`
- 新方案不要求 Claude 输出回流 Viewer，仅 Codex 由 SSE 展示。
- 影响：Timeline/agent.* 事件统一路径的优先级下降。

3) CX 暂停/继续语义冲突
- v0.2.1 明确“OS 级挂起（SIGSTOP/SuspendThread）”。`
  参考：`docs/plan/cc-spec-v0.2.1/proposal.md:342`
- 新方案：暂停=软中断（SIGINT/CTRL_BREAK），后续 resume session_id。
- 影响：暂停/继续实现路径与 UI 文案需调整。

4) Codex 调用栈冲突（Python sidecar vs Rust runner）
- 既有方案以 Python codex client 为主，sidecar 打包并由 Viewer 调用。`
  参考：`docs/plan/cc-spec-v0.2.1/proposal.md:213`, `docs/plan/cc-spec-v0.2.1/tasks.md:870`
- 新方案新增 Rust 直接管理 Codex，需引入 feature flag 并确定默认路径。

5) 事件协议统一方向冲突
- v0.2.1 目标是 agent.* 统一事件模型。`
  参考：`docs/plan/cc-spec-v0.2.1/proposal.md:373`
- 新方案强调维持 codex.* SSE 兼容，agent.* 可选映射。

## 需要决策的分歧点（建议标注为变更）
- 是否放弃“Viewer 内 CC 对话主入口”目标，改为“系统终端 + 环境注入”。
- 是否将“暂停”定义从 OS suspend 改为 soft-stop + resume。
- 是否保留 Python runner 为默认路径，Rust runner 仅在 Viewer 内启用。

## 建议处理方式
- 为上述分歧建立变更记录（更新 proposal/tasks 的决策部分）
- 在实现上引入 feature flag，允许并行路线，降低切换风险

## 参考文件
- `plan/2025-12-23_23-13-04-rust-codex-direct-invoke.md`
- `docs/plan/cc-spec-v0.2.1/proposal.md`
- `docs/plan/cc-spec-v0.2.1/tasks.md`
