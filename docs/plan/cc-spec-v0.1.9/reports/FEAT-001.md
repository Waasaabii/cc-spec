# FEAT-001 Report

已实现 Codex 调用流式可见性（终端 + SSE），并提供 run_id 结束事件供前端停止订阅。

## 变更摘要
- CodexClient._run 改为 Popen 流式读取 stdout/stderr。
- 新增轻量 SSE 服务（仅标准库），输出 codex.started/stream/completed 事件。
- SSE 服务发现文件写入 .cc-spec/runtime/codex/stream.json。
- 更新 codex client 测试以适配 Popen 路径。

## 影响文件
- src/cc_spec/codex/client.py
- src/cc_spec/codex/streaming.py
- tests/codex/test_codex_error_types.py
