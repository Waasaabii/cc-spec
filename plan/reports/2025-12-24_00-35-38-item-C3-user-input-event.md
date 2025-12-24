# 完成报告：C3 user_input 事件保留

## 完成内容
- Codex 执行前发送 codex.user_input 事件
- 事件包含 session_id 与文本，供 Viewer 侧展示

## 代码变更
- 修改 `apps/cc-spec-tool/src-tauri/src/codex_runner.rs`

## 参考
- `apps/cc-spec-tool/src-tauri/src/codex_runner.rs:136`
