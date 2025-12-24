# Phase 1 报告：功能-命令-事件-UI 对照

## 范围
- 后端 Tauri 命令注册清单与前端 invoke 使用路径对照
- SSE/事件通路的当前消费情况
- 组件/Hook 的集成情况（是否被实际引用）

## 关键发现
### 1) 后端命令注册 vs 前端调用覆盖
已注册命令（节选，完整列表见 main.rs）：
- Settings/Concurrency: get_settings, set_settings, get_concurrency_status, cancel_queued_task, update_concurrency_limits
- Sessions: save_history, load_history, load_sessions, stop_session, graceful_stop_session
- Claude: cmd_detect_claude_path, cmd_validate_claude_path, start_claude, send_claude_message, stop_claude, graceful_stop_claude, get_claude_session, list_claude_sessions, is_claude_session_active, get_claude_session_count
- Database: check_database_connection, start_docker_postgres, stop_docker_postgres, get_docker_postgres_logs, connect_remote_database
- Index: get_index_status, check_index_exists, init_index, update_index, get_index_settings_prompt_dismissed, set_index_settings_prompt_dismissed
- Translation: check_translation_model, download_translation_model, translate_text, clear_translation_cache, delete_translation_model, get_translation_cache_stats, preload_translation_model
- Export: export_history, import_history, get_export_size_estimate
- Sidecar: run_ccspec_command, run_ccspec_stream, check_sidecar_available, get_ccspec_version
- Skills: check_skills_status, install_skills, uninstall_skills, get_skills_version, check_skills_update_needed

前端实际 invoke 覆盖（当前代码）：
- 已使用：get_settings, set_settings, get_concurrency_status, save_history, load_history, load_sessions, stop_session
- Index：init_index, set_index_settings_prompt_dismissed
- Sidecar：run_ccspec_command, run_ccspec_stream, check_sidecar_available, get_ccspec_version
- Skills：check_skills_status, install_skills, uninstall_skills, get_skills_version, check_skills_update_needed
- Translation：translate_text（仅翻译按钮）

明显缺口：
- Claude 相关命令均未在前端调用（无 CC 启动/对话 UI 入口）
- Database / Export / Index 状态 / Translation 下载与缓存管理 / 并发队列控制（cancel_queued_task、update_concurrency_limits）均未接入 UI

### 2) 事件通路现状
- 前端仅通过 SSE 监听 codex.* 事件（EventSource）
- 后端 SSE ingest 默认事件名为 codex.stream，基于 payload.type 字段路由
- Claude 事件通过 Tauri event emit（agent.* 与 agent.event）推送，但前端未监听
- EventDispatcher 在后端存在，但未接入 main.rs 的 SSE/事件流

### 3) 组件与 Hook 未接入
以下模块存在但未被 App.tsx 或其他组件引用：
- hooks/useSettings.ts（封装 settings/concurrency 逻辑）
- hooks/useSkills.ts（skills 管理）
- hooks/useSidecar.ts（sidecar 调用封装）
- components/index/IndexPrompt.tsx（索引提示 UI）
- components/chat/TranslateButton.tsx（翻译按钮）
- components/chat/Timeline.tsx（统一时间线）

## 结论（Phase 1）
- Viewer 实际运行路径仍以 codex SSE + 旧 sessions.json 为核心；新功能（CC/skills/translation/db/export/统一事件）多数仅完成后端注册或组件封装，尚未连线到 UI。
- 事件通路处于“双轨”（SSE codex.* vs Tauri agent.*），前端仅消费 codex.*，导致 CC/统一事件不可见。

## 建议进入 Phase 2 的输入
- 明确“唯一事件主干”与迁移策略（SSE vs Tauri event）
- 产出一份“事件/命令/组件”接入优先级清单

## 参考证据
- `apps/cc-spec-tool/src-tauri/src/main.rs:888`
- `apps/cc-spec-tool/src-tauri/src/main.rs:446`
- `apps/cc-spec-tool/src-tauri/src/claude.rs:288`
- `apps/cc-spec-tool/src/App.tsx:171`
- `apps/cc-spec-tool/src/components/chat/TranslateButton.tsx:1`
