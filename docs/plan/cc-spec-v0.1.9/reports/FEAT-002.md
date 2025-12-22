# FEAT-002 Report

新增外置 Codex SSE 查看器（React + Vite + Tailwind v4 + Tauri）。

## 变更摘要
- 新增 apps/cc-spec-viewer 目录与 Vite + React + Tailwind v4 配置。
- Tauri v2 基础骨架 + dialog/fs 插件权限与入口。
- 实现 stream.json 读取、SSE 连接、run_id 聚合与完成态停止渲染。
- 增加连接/断开/错误/空态提示与运行概览。

## 影响文件
- apps/cc-spec-viewer/.gitignore
- apps/cc-spec-viewer/index.html
- apps/cc-spec-viewer/package.json
- apps/cc-spec-viewer/tsconfig.json
- apps/cc-spec-viewer/tsconfig.node.json
- apps/cc-spec-viewer/vite.config.ts
- apps/cc-spec-viewer/src/App.tsx
- apps/cc-spec-viewer/src/main.tsx
- apps/cc-spec-viewer/src/styles.css
- apps/cc-spec-viewer/src-tauri/Cargo.toml
- apps/cc-spec-viewer/src-tauri/tauri.conf.json
- apps/cc-spec-viewer/src-tauri/capabilities/default.json
- apps/cc-spec-viewer/src-tauri/src/main.rs

## 测试
- 未运行（新增前端/tauri 模板）。