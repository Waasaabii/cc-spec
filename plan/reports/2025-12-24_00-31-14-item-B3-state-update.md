# 完成报告：B3 session 状态更新

## 完成内容
- 注册会话时写入 state=running
- idle 监控触发时写入 state=idle
- 结束时写入 state=done/failed + exit_code + elapsed_s + pid=null

## 代码变更
- 修改 `apps/cc-spec-tool/src-tauri/src/codex_runner.rs`

## 参考
- `apps/cc-spec-tool/src-tauri/src/codex_runner.rs:86`
