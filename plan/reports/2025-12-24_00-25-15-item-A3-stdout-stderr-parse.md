# 完成报告：A3 stdout/stderr 逐行读取与 session_id 解析

## 完成内容
- Codex 进程 stdout/stderr 改为逐行读取（read_until + UTF-8 lossy）
- 解析 JSONL 的 `thread.started` 事件，提取并更新 session_id
- 输出行保存为向量，供后续 SSE/解析使用

## 代码变更
- 修改 `apps/cc-spec-tool/src-tauri/src/codex_runner.rs`

## 参考
- `apps/cc-spec-tool/src-tauri/src/codex_runner.rs:33`
