# 完成报告：A4 idle 监控与超时策略

## 完成内容
- Codex 运行加入超时控制（默认 2h，支持 CODEX_TIMEOUT 覆盖）
- idle 监控线程（默认 60s，可通过 CC_SPEC_CODEX_IDLE_TIMEOUT 覆盖）
- 超时后执行 soft_stop → 等待 → kill

## 代码变更
- 修改 `apps/cc-spec-tool/src-tauri/src/codex_runner.rs`

## 参考
- `apps/cc-spec-tool/src-tauri/src/codex_runner.rs:76`
