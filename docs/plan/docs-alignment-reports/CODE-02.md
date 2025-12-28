# CODE-02 Report

pytest 结构已按层级重组（cli/unit/rag/codex/integration），并引入统一 fixtures 与 markers 以避免重复造轮子。

## 变更摘要
- 新增 pytest markers（unit/cli/rag/codex/integration/slow），并基于目录自动打标。
- CLI 测试移至 tests/cli 并改为 autouse fixture + tmp_path/monkeypatch，移除手写 tempfile/teardown。
- core 与根目录测试迁移至 tests/unit；codex 与 rag 测试归位。
- 移除 tests/__init__.py 与 tests/core/__init__.py（tests/core 目录已清理）。

## 涉及文件
- pyproject.toml
- tests/conftest.py
- tests/cli/test_cmd_apply.py
- tests/cli/test_cmd_archive.py
- tests/cli/test_cmd_checklist.py
- tests/cli/test_cmd_clarify.py
- tests/cli/test_cmd_goto.py
- tests/cli/test_cmd_init.py
- tests/cli/test_cmd_plan.py
- tests/cli/test_cmd_quick_delta.py
- tests/cli/test_cmd_specify.py
- tests/cli/test_cmd_update.py
- tests/cli/test_quick_delta_v13.py
- tests/unit/test_command_generator.py
- tests/unit/test_config.py
- tests/unit/test_config_core.py
- tests/unit/test_delta.py
- tests/unit/test_id_manager.py
- tests/unit/test_lock.py
- tests/unit/test_scoring.py
- tests/unit/test_scoring_v13.py
- tests/unit/test_state.py
- tests/unit/test_subagent_executor.py
- tests/unit/test_task_parser.py
- tests/unit/test_templates.py
- tests/unit/test_ui.py
- tests/unit/test_ambiguity.py
- tests/unit/test_command_templates.py
- tests/unit/test_plan_template.py
- tests/unit/test_tech_check.py
- tests/rag/test_kb_verbose.py
- tests/codex/test_codex_error_types.py
