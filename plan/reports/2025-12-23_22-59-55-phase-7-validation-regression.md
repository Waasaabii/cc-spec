# Phase 7 报告：验证与回归流程定义

## 目标
提供最小可执行的验证路径，覆盖 CC/CX 流、事件链路、关键模块。

## 建议验证清单（最小手工回归）
1. Viewer 启动与 SSE 连通
   - 启动 Viewer → 连接状态变为 connected
2. CX 执行与事件展示（codex SSE）
   - 触发一次 codex 任务 → codex.started/stream/completed 正常显示
3. CC 进程启动与事件显示（需接入后）
   - start_claude → agent.started/stream/completed 可见
4. 停止/中断链路
   - stop_session/graceful_stop_session → UI 状态切换到 completed/error
5. 索引初始化提示
   - IndexPrompt 出现 → init_index 成功 → 状态持久化
6. 翻译按钮
   - TranslateButton 翻译成功 → 失败提示可见
7. Sidecar 命令流式输出
   - run_ccspec_stream → stdout/stderr/done 事件到达
8. 数据库/导出
   - start_docker_postgres/check_database_connection/export_history/import_history 全链路通过（或提示降级）

## 建议自动化/半自动验证
- 针对 invoke 命令的 smoke 测试：最小参数调用 + 错误处理
- EventEmitter 事件一致性测试（SSE vs Tauri event）

## 参考
- `apps/cc-spec-tool/src/App.tsx:150`
- `apps/cc-spec-tool/src-tauri/src/main.rs:446`
