# FEAT-002 Report

新增外置 Codex SSE 查看器（React + Vite + Tailwind v4 + Tauri）。

## 变更摘要
- 新增 apps/cc-spec-tool 目录与 Vite + React + Tailwind v4 配置。
- Tauri v2 基础骨架 + dialog/fs 插件权限与入口。
- 实现 stream.json 读取、SSE 连接、run_id 聚合与完成态停止渲染。
- 增加连接/断开/错误/空态提示与运行概览。

## 影响文件
- apps/cc-spec-tool/.gitignore
- apps/cc-spec-tool/index.html
- apps/cc-spec-tool/package.json
- apps/cc-spec-tool/tsconfig.json
- apps/cc-spec-tool/tsconfig.node.json
- apps/cc-spec-tool/vite.config.ts
- apps/cc-spec-tool/src/App.tsx
- apps/cc-spec-tool/src/main.tsx
- apps/cc-spec-tool/src/styles.css
- apps/cc-spec-tool/src-tauri/Cargo.toml
- apps/cc-spec-tool/src-tauri/tauri.conf.json
- apps/cc-spec-tool/src-tauri/capabilities/default.json
- apps/cc-spec-tool/src-tauri/src/main.rs

## 测试
- 未运行（新增前端/tauri 模板）。