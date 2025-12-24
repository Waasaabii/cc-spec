# FEAT-003 Report

实现零配置 Viewer（固定端口 38888）并将 Codex 事件推送到 Viewer ingest。

## 变更摘要
- Viewer 侧新增内置 HTTP 服务器（/events + /ingest），固定监听 127.0.0.1:38888。
- Codex 侧不再自建 SSE 服务器，改为向 Viewer /ingest POST 事件（失败可忽略）。
- 事件默认携带 project_root，Viewer 按项目分组展示。
- Viewer 前端改为固定端口连接，移除 manifest/目录选择流程。

## 影响文件
- src/cc_spec/codex/streaming.py
- src/cc_spec/codex/client.py
- apps/cc-spec-tool/package.json
- apps/cc-spec-tool/src/App.tsx
- apps/cc-spec-tool/src-tauri/Cargo.toml
- apps/cc-spec-tool/src-tauri/capabilities/default.json
- apps/cc-spec-tool/src-tauri/src/main.rs
- apps/cc-spec-tool/src-tauri/tauri.conf.json

## 测试
- 未运行（建议 tauri dev 验证 SSE 与 ingest）。