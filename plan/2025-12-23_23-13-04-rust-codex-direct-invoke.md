---
mode: plan
cwd: C:\develop\cc-spec
task: Rust 管理 Codex + 系统终端 Claude 的实施计划（细化版-含调研与清单）
complexity: complex
planning_method: builtin
created_at: 2025-12-23T23:13:04.2078487+08:00
---

# Plan: Rust 管理 Codex + 系统终端 Claude（细化版）

任务概述
在不内嵌终端的前提下，通过“系统终端启动 Claude Code + Rust 管理 Codex”实现与现有 Python 版本一致的会话管理（session_id/resume/停止/软中断）。保留 SSE 事件通路供 Viewer 展示。Codex 失败自动重试 5 次，失败后明确提示 Claude 继续。

调研结论（现状基线）
1) Codex CLI 调用方式
- Python 版本通过 `codex exec --skip-git-repo-check --cd <workdir> --json -` 执行，resume 模式为 `codex exec ... resume <session_id> -`。`
  参考：`src/cc_spec/codex/client.py:149`, `src/cc_spec/codex/client.py:163`

2) JSONL 解析与事件输出
- stdout/stderr 逐行读取；对 stdout 解析 thread.started 获取 session_id；将每行作为 codex.stream 事件发送至 Viewer SSE。`
  参考：`src/cc_spec/codex/client.py:238`, `src/cc_spec/codex/client.py:265`
- 进程启动后发送 codex.started（包含 pid），结束时发送 codex.completed。`
  参考：`src/cc_spec/codex/client.py:394`, `src/cc_spec/codex/client.py:520`

3) 会话状态持久化
- sessions.json 存放于 `.cc-spec/runtime/codex/`，含 state/task_summary/pid/elapsed 等字段，带锁文件。`
  参考：`src/cc_spec/codex/session_state.py:21`, `src/cc_spec/codex/session_state.py:31`

4) CLI chat 续会话
- `cc-spec chat` 根据 session_id 调用 resume；失败时输出结构化状态，提示继续会话。`
  参考：`src/cc_spec/commands/chat.py:132`, `src/cc_spec/commands/chat.py:176`

5) Viewer SSE 通路
- Viewer 通过 `/events` 提供 SSE；`/ingest` 接收 JSON 并以 `type` 字段作为 event 名广播。`
  参考：`apps/cc-spec-tool/src-tauri/src/main.rs:446`, `apps/cc-spec-tool/src-tauri/src/main.rs:477`

执行计划（高层）
1. 现状对齐：梳理 Python CodexClient 调用链路（JSONL 解析、sessions.json、SSE 事件）与 Viewer 依赖点，确定需要保持兼容的事件/文件格式。
2. 运行入口设计：确定“当前终端”启动策略（Windows 以 PowerShell 为主），设计 Viewer 注入环境变量与工作目录的方式（不内嵌终端）。
3. Rust Codex Runner：实现 spawn/soft-stop/timeout/kill + stdin 写入 + stdout/stderr 逐行解析的进程模型。
4. 会话与状态：复刻 session_id/run_id 规则与 sessions.json 写入逻辑，确保 resume 继续会话语义一致。
5. SSE 事件输出：Rust 端直接发 codex.*（或 agent.* 兼容映射）到 Viewer SSE，保持前端无大改。
6. “暂停”语义：定义为软中断（SIGINT/CTRL_BREAK），停止当前输出；后续用 resume 继续会话。
7. 失败重试策略：最多自动重试 5 次；连续失败后输出结构化提示给 Claude（提示 resume 或检查环境）。
8. 迁移与回滚：引入 feature flag（Python vs Rust runner），支持快速切回旧链路。
9. 验证计划：覆盖启动/输出/停止/恢复/重试/失败提示的最小回归与 smoke 测试。

执行清单（可追踪）
A. Rust Codex Runner（后端）
- [x] 新增 `codex_runner.rs`：封装 spawn/soft_stop/kill/resume API
- [x] 参数对齐：exec/resume 命令参数与 Python 版本一致
- [x] stdout/stderr 逐行读取（行缓冲、UTF-8 容错）
- [x] JSONL 解析：thread.started 提取 session_id；保留原始行
- [x] idle 监控与 timeout：与 Python 行为一致（默认 60s idle、2h timeout）
- [x] 失败重试 5 次（记录 attempts，输出结构化提示）

B. 会话与持久化
- [x] sessions.json 读写（含 lock）与 schema 对齐
- [x] run_id 规则与 seq 递增规则对齐
- [x] state 更新：running/idle/done/failed 与 exit_code/elapsed

C. SSE 事件输出
- [x] codex.started/codex.stream/codex.completed/codex.error 事件格式对齐
- [x] 事件发送到 Viewer `/ingest` 或共享 Broadcaster（保持 SSE 可用）
- [x] user_input 事件保留（Claude 调用 Codex 时发出）

D. 系统终端启动（Claude 入口）
- [x] Viewer 增加“打开 Claude 终端”命令（调用系统终端）
- [x] 环境注入：`CC_SPEC_PROJECT_ROOT`, `CC_SPEC_VIEWER_URL`, `CC_SPEC_SESSION_ID`, `CC_SPEC_CODEX_RUNNER=rust`
- [x] PowerShell 默认启动；允许 `CC_SPEC_TERMINAL` 覆盖

E. “暂停/继续”语义
- [x] pause = soft_stop（SIGINT/CTRL_BREAK）
- [x] resume = 调用 `codex exec resume <session_id>` 新进程继续
- [x] sessions.json 与事件同步更新

F. 验证与回归
- [x] 启动：Rust Runner 执行一次 codex exec
- [x] 输出：codex.stream 连续到达 Viewer
- [x] 软中断：停止后可 resume，session_id 不变
- [x] 重试：连续失败 5 次后输出结构化提示
- [x] 回滚：切换回 Python runner 可正常执行

代码变更清单（文件级）
1) Rust 后端（Tauri）
- 新增 `apps/cc-spec-tool/src-tauri/src/codex_runner.rs`：Codex 进程管理（spawn/resume/soft_stop/kill）、JSONL 解析、5 次重试、sessions.json 读写
- 新增 `apps/cc-spec-tool/src-tauri/src/terminal.rs`：系统终端启动 Claude（注入环境变量与工作目录）
- 修改 `apps/cc-spec-tool/src-tauri/src/main.rs`：注册新命令（start/resume/soft_stop/launch_terminal），将 SSE Broadcaster 暴露给 codex_runner
- 修改 `apps/cc-spec-tool/src-tauri/src/events.rs`：如需，将 codex.* 映射到统一事件（可选，不破坏前端）

2) 前端（Viewer）
- 修改 `apps/cc-spec-tool/src/App.tsx`：新增“打开 Claude 终端”入口按钮并调用 Tauri 命令
- 新增 `apps/cc-spec-tool/src/hooks/useClaudeTerminal.ts`（可选）：封装终端启动与错误提示
- 如需，修改 `apps/cc-spec-tool/src/components/settings/SettingsPage.tsx`：增加终端启动设置（可选）

3) Python 路径（降级/移除旧路线）
- 仅保留 CLI 使用场景；Viewer 端不再通过 Python runner 调用 Codex
- 删除或禁用 Viewer 侧对 Python/sidecar 路线的依赖（不再作为 fallback）

关键假设/取舍
- “当前终端”解释为系统默认终端/PowerShell，可通过环境变量显式指定；不做内嵌终端。
- Claude 不需要在 Viewer 内显示输出，仅通过终端输出与返回码感知 Codex 运行结果。
- 事件通路继续使用 SSE，不改前端消费逻辑。

风险与注意事项
- 风险不只沙盒：跨平台信号/终端启动差异、JSONL 解析稳定性、session_id/run_id 一致性、重试导致副作用。
- Claude 输出不回流 Viewer，需要清晰的“失败提示/继续指引”格式。
- Codex CLI 协议变化时 Rust 解析需要同步升级，必须保留回退路径。

参考
- `src/cc_spec/codex/client.py:149`
- `src/cc_spec/codex/client.py:238`
- `src/cc_spec/codex/client.py:394`
- `src/cc_spec/codex/session_state.py:21`
- `src/cc_spec/commands/chat.py:132`
- `apps/cc-spec-tool/src-tauri/src/main.rs:446`
- `apps/cc-spec-tool/src-tauri/src/main.rs:477`
## 变更记录
- 2025-12-24 12:27:09: 根据 @plan 确认 CC 交互已调整为“系统终端启动 Claude Code（不内嵌）”，移除“Viewer 内直接对话启动 CC”的缺口判断；新增“从项目上下文一键打开系统终端 Claude”作为项目管理入口的需求。
- 2025-12-24 12:47:02: 完成项目管理前端入口与项目筛选视图接入，缺口 1 闭环。
- 2025-12-24 12:51:32: 增加项目上下文“一键打开 Claude 终端”入口并完成调用接入，缺口 2 闭环。
- 2025-12-24 12:56:34: 增加 Skills 管理 UI 面板与状态展示，缺口 3 闭环。
- 2025-12-24 13:01:59: 接入 IndexPrompt 自动弹出逻辑（按项目检查 index/已关闭标记），缺口 4 闭环。
- 2025-12-24 13:13:05: 接入翻译设置下载与消息翻译按钮，缺口 5 闭环。
- 2025-12-24 13:21:26: 接入 EventDispatcher 并将 codex.* 映射为 agent.* 推送 SSE，缺口 6 闭环。
- 2025-12-24 13:32:03: 重构前端 IA，新增侧边栏导航并拆分 Projects/Runs 视图，缺口 7 闭环。

## 缺口清单（更新）
1. 项目导入/管理缺失（已完成：前端项目面板 + 后端注册表）
2. 从项目上下文一键打开系统终端 Claude（已完成：项目面板入口 + launch_claude_terminal 调用）
3. Skills 管理 UI 缺失（已完成：Skills 面板 + useSkills 接入）
4. 索引初始化提示未接入（已完成：IndexPrompt 自动弹出接入）
5. 翻译入口未接入（已完成：设置页下载 + 消息翻译按钮）
6. 事件协议统一未落地主链路（已完成：EventDispatcher 映射并桥接 SSE）
7. 前端信息架构/页面重构缺失（已完成：侧边栏导航 + Projects/Runs 视图拆分）
