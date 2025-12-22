# FEAT-004 Report

新增 Viewer 端口设置与用户目录全局配置，Codex 推送读取同一配置。

## 变更摘要
- Viewer 端口设置写入用户目录 ~/.cc-spec/viewer.json，并在启动时读取。
- Viewer 前端提供端口编辑与保存提示（重启后生效）。
- Codex 推送端读取全局配置端口（环境变量可覆盖）。

## 影响文件
- src/cc_spec/codex/streaming.py
- apps/cc-spec-viewer/src/App.tsx
- apps/cc-spec-viewer/src-tauri/src/main.rs

## 测试
- 未运行（建议 tauri dev 验证端口切换与推送）。