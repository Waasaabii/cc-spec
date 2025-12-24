# 完成报告：E “暂停/继续”语义接入

## 完成内容
- 新增 codex_pause/codex_resume Tauri 命令，支持 soft_stop 暂停与 resume 继续
- pause 时更新 sessions.json 为 idle 并清空 pid；可选发送 codex.completed( paused ) 事件
- resume 通过 codex exec resume <session_id> 启动新进程并输出 SSE 事件

## 代码变更
- `apps/cc-spec-tool/src-tauri/src/main.rs`
- `apps/cc-spec-tool/src-tauri/src/codex_runner.rs`

## 备注
- pause 需要传入 session_id；如提供 run_id，将向 Viewer 推送 codex.completed
- resume 需要传入 prompt（非空），并可指定 timeout_ms

## 参考
- `apps/cc-spec-tool/src-tauri/src/main.rs:714`
- `apps/cc-spec-tool/src-tauri/src/main.rs:723`
- `apps/cc-spec-tool/src-tauri/src/codex_runner.rs:687`
