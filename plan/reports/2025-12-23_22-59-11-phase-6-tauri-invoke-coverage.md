# Phase 6 报告：Tauri invoke 注册与前端调用覆盖

## 覆盖统计
- 已注册命令：约 40+（见 main.rs）
- 前端实际调用：19 个（通过正则扫描 invoke(...)）

## 已调用命令（前端）
check_sidecar_available, check_skills_status, check_skills_update_needed, get_ccspec_version, get_concurrency_status, get_settings, get_skills_version, init_index, install_skills, load_history, load_sessions, run_ccspec_command, run_ccspec_stream, save_history, set_index_settings_prompt_dismissed, set_settings, stop_session, translate_text, uninstall_skills

## 未覆盖命令（注册但前端未调用）
- 并发与会话：cancel_queued_task, update_concurrency_limits, graceful_stop_session
- Claude：cmd_detect_claude_path, cmd_validate_claude_path, start_claude, send_claude_message, stop_claude, graceful_stop_claude, get_claude_session, list_claude_sessions, is_claude_session_active, get_claude_session_count
- Index：get_index_status, check_index_exists, update_index, get_index_settings_prompt_dismissed
- Translation：check_translation_model, download_translation_model, clear_translation_cache, delete_translation_model, get_translation_cache_stats, preload_translation_model
- Database：check_database_connection, start_docker_postgres, stop_docker_postgres, get_docker_postgres_logs, connect_remote_database
- Export：export_history, import_history, get_export_size_estimate

## 结论
- 关键功能（CC 启动、数据库、导出、索引状态、翻译下载/缓存、并发队列控制）仍处于“仅后端注册”状态
- 当前 UI 仅覆盖基础设置、SSE 会话展示、少量 sidecar/skills 调用

## 参考证据
- `apps/cc-spec-tool/src-tauri/src/main.rs:888`
- `apps/cc-spec-tool/src/App.tsx:171`
