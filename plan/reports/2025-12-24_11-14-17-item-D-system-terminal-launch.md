# 完成报告：D 系统终端启动（Claude 入口）

## 完成内容
- 接入 Tauri 命令 `launch_claude_terminal`，可从 Viewer 触发系统终端启动 Claude
- RunCard 增加“打开 Claude 终端”入口，携带 project_path 与可选 session_id
- 终端环境变量注入与终端选择逻辑使用现有 `terminal.rs` 实现

## 代码变更
- `apps/cc-spec-tool/src-tauri/src/main.rs`
- `apps/cc-spec-tool/src/components/chat/RunCard.tsx`

## 备注
- 终端启动默认使用 PowerShell，并支持 `CC_SPEC_TERMINAL` 覆盖
- 注入变量包含 `CC_SPEC_PROJECT_ROOT` / `CC_SPEC_VIEWER_URL` / `CC_SPEC_SESSION_ID` / `CC_SPEC_CODEX_RUNNER`

## 参考
- `apps/cc-spec-tool/src-tauri/src/terminal.rs:6`
- `apps/cc-spec-tool/src-tauri/src/main.rs:696`
- `apps/cc-spec-tool/src/components/chat/RunCard.tsx:90`
