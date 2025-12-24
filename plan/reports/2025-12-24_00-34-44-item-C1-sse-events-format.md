# 完成报告：C1 codex.* 事件格式对齐

## 完成内容
- codex.started / codex.stream / codex.completed / codex.error 事件在 Rust 端生成
- 字段对齐：ts/run_id/session_id/stream/seq/text/pid/project_root/exit_code/error_type/duration_s

## 代码变更
- 修改 `apps/cc-spec-tool/src-tauri/src/codex_runner.rs`

## 参考
- `apps/cc-spec-tool/src-tauri/src/codex_runner.rs:131`
