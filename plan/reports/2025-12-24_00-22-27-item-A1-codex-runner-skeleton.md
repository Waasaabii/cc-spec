# 完成报告：A1 新增 codex_runner.rs 基础骨架

## 完成内容
- 新增 Rust 模块 `codex_runner.rs`，提供基础 exec/resume 命令构建与进程启动逻辑
- 提供 `run_codex`、`soft_stop`、`force_kill` API 骨架（后续补充 JSONL 解析/SSE/会话持久化）

## 代码变更
- 新增 `apps/cc-spec-tool/src-tauri/src/codex_runner.rs`

## 备注
- 当前实现为基础骨架，尚未引入 streaming 解析、sessions.json 持久化、SSE 事件输出与重试策略

## 参考
- `apps/cc-spec-tool/src-tauri/src/codex_runner.rs:1`
