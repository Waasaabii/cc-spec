---
mode: plan
cwd: C:\develop\cc-spec
task: Codex 交互会话托管（ConPTY）+ 原生终端桥接（tool 可控，Claude Code 调度）
complexity: complex
planning_method: builtin
created_at: 2025-12-25T17:13:13.4221308+08:00
---

# Plan: Codex ConPTY 会话托管与原生终端桥接（简化版）

🎯 任务概述
在 Win11 上实现“Codex 交互会话托管 + 原生终端窗口交互 + tool/Claude 可控重试/暂停/恢复”。

目标拆分：
- 用户：只在原生终端窗口里原生操作 `codex`（TUI），不被限制。
- tool：只负责会话生命周期（创建/暂停/恢复/重试/重启/销毁）、基础状态采集与对外通知。
- Claude Code：主导调度方；只需要拿到“最后结果”（turn complete）与关键状态变化，不需要实时终端输出。

核心约束：
- 不要求用户额外安装依赖（仅系统已有终端/PowerShell/VS Code）；允许随 tool 发布 relay/notifier sidecar。
- 不侵入系统变量/全局配置：仅对 tool 启动的 codex 子进程设置环境变量（如 `CODEX_HOME`），项目内注入写入 `<project>/.cc-spec/`。
- tool 不尝试解析/渲染 Codex TUI 屏幕，避免复杂化。

📋 执行计划
1. MVP 行为确认
   - 明确 session 的 API：create/list/attach/send_input/pause/resume/retry/restart/kill。
   - 明确“重试”定义：仅当 Codex 进程完全退出且存在 pending 的 Claude Code 请求时，tool 触发重试；用户自由输入不触发调度。

2. 结果输出通道（Claude Code 只要最后结果）
   - 使用 Codex `notify` hook 获取 `agent-turn-complete` JSON（含 `thread-id`、`input-messages`、`last-assistant-message`）。
   - tool 为 codex 子进程设置 `CODEX_HOME=<tool-managed-dir>` 并写入 `config.toml` 启用 `notify = ["cc-spec-codex-notify", ...]`，做到“无需用户改全局配置”。
   - notifier 只把“最后结果 + session/thread 标识 + 时间戳”回传给 tool；tool 再转发给 Claude Code。

3. 会话 Host（tool 后端）
   - Win11 使用 ConPTY 托管 `codex` 交互 TUI：获得可读写 PTY（支持 resize、Ctrl+C 等）。
   - 维护 session 元数据：`session_id/pid/thread_id?(由 notify 反推)/cwd/created_at/last_activity/attached_count/pending_request_id`。

4. 原生终端桥（relay sidecar）
   - `cc-spec-codex-relay --session <id> --endpoint <...> --token <...>`：
     - 读取当前终端输入并转发到 tool 的 session（保持尽量原生，包括 Ctrl+C/窗口 resize）。
     - 将 tool session 的输出直接写回当前终端 stdout。
     - 上报 attach/detach/resize，以及用户中断信号（如 Ctrl+C/EOF）给 tool 用于“退出原因”判断。

5. 终端拉起与 attach
   - tool 负责打开新窗口：优先 `wt.exe`，fallback `pwsh`/`powershell`/`cmd.exe start`。
   - 新窗口命令行只做一件事：运行 relay 并连接到指定 session。

6. 退出原因区分（你要求：用户/自己/Claude Code）
   - tool 统一记录：
     - `last_stop_requested_by = tool | claude_code | none`
     - `last_user_interrupt_at`（来自 relay）
     - `last_control_event`（例如 tool 触发 pause/restart）
   - codex 进程退出时按优先级判定：
     1) 若 `last_stop_requested_by=tool` → `exit_reason=tool_requested`
     2) 若 `last_stop_requested_by=claude_code` → `exit_reason=claude_requested`
     3) 若退出前短窗口（如 1–2s）内收到 user interrupt（Ctrl+C/EOF）或检测到用户输入 `exit/quit` → `exit_reason=user_requested`
     4) 否则 → `exit_reason=crash_or_unknown`

7. 重试策略（保持简单）
   - 只对 `exit_reason=crash_or_unknown` 且 `pending_request_id!=null` 做自动重试（可配置最多 N 次，带 backoff）。
   - 对 `user_requested` 不自动重试；对 `claude_requested/tool_requested` 由调用方决定是否重启。

8. 对外通知与最小可视化
   - Claude Code：订阅/轮询 tool 的事件流，只接收：
     - `turn_complete`（来自 notify 的最后结果）
     - `session_state_changed`（start/exit/restart/pause/resume/attach/detach，含 exit_reason）
   - tool UI：只展示 session 列表与状态（running/exited、pid、last_activity、attached_count、pending_request）；端口展示可选用 `netstat -ano` 映射 pid。

9. 验收清单（手工回归优先）
   - 多会话：并行启动 2–3 个 codex session，分别 attach 到不同终端窗口。
   - 退出原因：分别验证 user exit、Claude Code stop、tool stop、崩溃/异常退出的分类。
   - 重试：模拟 codex 异常退出，tool 自动重试一次并最终能产出 `turn_complete` 通知。
   - notify：确认 `last-assistant-message` 能稳定拿到，且不会因为用户手工操作导致 Claude Code 收到噪声（只转发与 pending_request 对应的 turn_complete）。

⚠️ 风险与注意事项
- `notify` 事件能否覆盖 TUI 的所有“完成时刻”：若存在漏报，需要 fallback（例如检测长期 idle + 最后一段输出截断），但优先以 notify 为准。
- 终端输入竞争：用户输入优先，Claude Code 注入应做节流；MVP 不追求“完全无打架”。
- `wt.exe` 不可用场景必须兜底；以及 PowerShell 7/Windows PowerShell 的差异。

📎 参考
- `apps/cc-spec-tool/src-tauri/src/codex_runner.rs:1`（现有 codex 非交互 runner 与事件推送）
- `apps/cc-spec-tool/src-tauri/src/main.rs:1035`（内置 HTTP `/ingest` 入口，可复用作为事件/IPC 思路）
- `apps/cc-spec-tool/src-tauri/src/terminal.rs:10`（Windows 新控制台窗口 `creation_flags`）
- `reference/codex/docs/config.md:655`（Codex `notify` hook：`agent-turn-complete` JSON）
