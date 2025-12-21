"""Unit tests for apply command."""

import os
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from helpers import assert_contains_any
from cc_spec import app
from cc_spec.commands.apply import (
    _display_task_summary,
    _find_resume_wave,
)
from cc_spec.core.state import (
    ChangeState,
    Stage,
    StageInfo,
    TaskStatus,
    load_state,
    update_state,
)
from cc_spec.rag.pipeline import KBUpdateSummary
from cc_spec.rag.scanner import ScanReport
from cc_spec.subagent.executor import ExecutionResult
from cc_spec.subagent.task_parser import (
    Task,
    TasksDocument,
    TaskStatus as ParserTaskStatus,
    Wave,
)

runner = CliRunner()


class TestApplyCommand:
    """Tests for apply command."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.project_root = tmp_path
        self.cc_spec_dir = self.project_root / ".cc-spec"
        self.changes_dir = self.cc_spec_dir / "changes"
        self.change_name = "add-feature"
        self.change_dir = self.changes_dir / self.change_name
        self.cc_spec_dir.mkdir(parents=True, exist_ok=True)
        self.change_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.chdir(self.project_root)

    def _create_tasks_yaml(self, content: str = None) -> Path:
        """Helper to create tasks.yaml with task definitions."""
        if content is None:
            content = """version: "1.6"
change: add-feature
tasks:
  01-SETUP:
    wave: 0
    name: Project Setup
    tokens: 30k
    status: idle
    deps: []
    docs:
      - docs/plan/spec.md
    code:
      - src/config/
    checklist:
      - 创建配置文件
      - 添加环境变量
  02-MODEL:
    wave: 1
    name: Data Model
    tokens: 50k
    status: idle
    deps: [01-SETUP]
    docs:
      - docs/plan/spec.md
    code:
      - src/models/
    checklist:
      - 创建数据模型
      - 添加验证逻辑
  03-API:
    wave: 1
    name: API Endpoints
    tokens: 45k
    status: idle
    deps: [01-SETUP]
    checklist:
      - 创建 API 路由
      - 添加认证中间件
"""
        tasks_path = self.change_dir / "tasks.yaml"
        tasks_path.write_text(content, encoding="utf-8")
        return tasks_path

    def _create_status(self, current_stage: Stage = Stage.PLAN) -> Path:
        """Helper to create status.yaml."""
        state = ChangeState(
            change_name=self.change_name,
            created_at=datetime.now().isoformat(),
            current_stage=current_stage,
            stages={
                Stage.SPECIFY: StageInfo(
                    status=TaskStatus.COMPLETED,
                    started_at=datetime.now().isoformat(),
                    completed_at=datetime.now().isoformat(),
                ),
                Stage.CLARIFY: StageInfo(status=TaskStatus.COMPLETED),
                Stage.PLAN: StageInfo(
                    status=TaskStatus.COMPLETED,
                    started_at=datetime.now().isoformat(),
                    completed_at=datetime.now().isoformat(),
                ),
                Stage.APPLY: StageInfo(status=TaskStatus.PENDING),
                Stage.CHECKLIST: StageInfo(status=TaskStatus.PENDING),
                Stage.ARCHIVE: StageInfo(status=TaskStatus.PENDING),
            },
        )

        status_path = self.change_dir / "status.yaml"
        update_state(status_path, state)
        return status_path

    def test_apply_without_project_root(self) -> None:
        """Test apply command fails when not in a project."""
        # Mock find_project_root to return None (simulates not being in a project)
        with patch("cc_spec.commands.apply.find_project_root", return_value=None):
            result = runner.invoke(app, ["apply", "test-change"])
            assert result.exit_code == 1
            assert "cc-spec" in result.stdout  # Error message contains project name

    def test_apply_without_change(self) -> None:
        """Test apply command fails when change doesn't exist."""
        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["apply", "nonexistent-change"])
        assert result.exit_code == 1
        assert_contains_any(result.stdout, ["未找到", "not found"])

    def test_apply_without_tasks_yaml(self) -> None:
        """Test apply command fails when tasks.yaml doesn't exist."""
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["apply", self.change_name])
        assert result.exit_code == 1
        assert_contains_any(result.stdout, ["tasks.yaml", "tasks"])

    def test_apply_dry_run(self) -> None:
        """Test apply command dry run mode shows execution plan."""
        self._create_tasks_yaml()
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["apply", self.change_name, "--dry-run"])

        assert result.exit_code == 0
        assert_contains_any(result.stdout.lower(), ["dry", "模拟"])
        assert "01-SETUP" in result.stdout
        assert "02-MODEL" in result.stdout

    def test_apply_with_no_pending_tasks(self) -> None:
        """Test apply command when all tasks are completed."""
        # Create tasks.yaml with all completed tasks
        tasks_content = """version: "1.6"
change: add-feature
tasks:
  01-SETUP:
    wave: 0
    name: Project Setup
    tokens: 30k
    status: completed
    deps: []
    checklist:
      - 创建配置文件
      - 添加环境变量
"""
        self._create_tasks_yaml(tasks_content)
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["apply", self.change_name])

        assert result.exit_code == 0
        assert_contains_any(result.stdout, ["没有待执行任务", "No pending tasks", "已完成"])

    def test_apply_displays_task_summary(self) -> None:
        """Test apply command displays task summary."""
        self._create_tasks_yaml()
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["apply", self.change_name, "--dry-run"])

        assert result.exit_code == 0
        # Should display task IDs
        assert "01-SETUP" in result.stdout
        assert "02-MODEL" in result.stdout
        assert "03-API" in result.stdout

    def test_apply_with_max_concurrent_option(self) -> None:
        """Test apply command accepts max-concurrent option."""
        self._create_tasks_yaml()
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(
            app, ["apply", self.change_name, "--max-concurrent", "5", "--dry-run"]
        )

        assert result.exit_code == 0

    def test_apply_without_explicit_change_name(self) -> None:
        """Test apply command uses current active change when name not provided."""
        self._create_tasks_yaml()
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["apply", "--dry-run"])

        assert result.exit_code == 0
        assert_contains_any(result.stdout, [self.change_name, "Dry run mode"])


class TestApplyExecution:
    """Tests for apply command execution with mocked executor."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.project_root = tmp_path
        self.cc_spec_dir = self.project_root / ".cc-spec"
        self.changes_dir = self.cc_spec_dir / "changes"
        self.change_name = "add-feature"
        self.change_dir = self.changes_dir / self.change_name
        self.cc_spec_dir.mkdir(parents=True, exist_ok=True)
        self.change_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.chdir(self.project_root)

    def _create_tasks_yaml(self) -> Path:
        """Helper to create tasks.yaml."""
        content = """version: "1.6"
change: add-feature
tasks:
  01-SETUP:
    wave: 0
    name: Project Setup
    tokens: 30k
    status: idle
    deps: []
    checklist:
      - 创建配置文件
"""
        tasks_path = self.change_dir / "tasks.yaml"
        tasks_path.write_text(content, encoding="utf-8")
        return tasks_path

    def _create_status(self) -> Path:
        """Helper to create status.yaml."""
        state = ChangeState(
            change_name=self.change_name,
            created_at=datetime.now().isoformat(),
            current_stage=Stage.PLAN,
            stages={
                Stage.SPECIFY: StageInfo(status=TaskStatus.COMPLETED),
                Stage.CLARIFY: StageInfo(status=TaskStatus.COMPLETED),
                Stage.PLAN: StageInfo(status=TaskStatus.COMPLETED),
                Stage.APPLY: StageInfo(status=TaskStatus.PENDING),
                Stage.CHECKLIST: StageInfo(status=TaskStatus.PENDING),
                Stage.ARCHIVE: StageInfo(status=TaskStatus.PENDING),
            },
        )

        status_path = self.change_dir / "status.yaml"
        update_state(status_path, state)
        return status_path

    @patch("cc_spec.commands.apply.SubAgentExecutor")
    def test_apply_successful_execution(self, mock_executor_class) -> None:
        """Test apply command with successful task execution."""
        self._create_tasks_yaml()
        status_path = self._create_status()

        # Mock executor
        mock_executor = MagicMock()
        mock_executor_class.return_value = mock_executor

        # Create mock document
        mock_task = Task(
            task_id="01-SETUP",
            name="Project Setup",
            wave=0,
            status=ParserTaskStatus.IDLE,
            dependencies=[],
        )
        mock_wave = Wave(wave_number=0, tasks=[mock_task])
        mock_doc = TasksDocument(
            change_name="add-feature",
            waves=[mock_wave],
            all_tasks={"01-SETUP": mock_task},
        )
        mock_executor.doc = mock_doc

        # Mock successful execution result
        mock_result = ExecutionResult(
            task_id="01-SETUP",
            success=True,
            output="Task completed successfully",
            duration_seconds=1.5,
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )

        # Setup async mock for execute_wave
        async def mock_execute_wave(wave_num, use_lock=True, skip_locked=False, resume=False):
            return [mock_result]

        mock_executor.execute_wave = mock_execute_wave

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["apply", self.change_name])

        if result.exit_code != 0:
            print("STDOUT:", result.stdout)
            if result.exception:
                import traceback
                traceback.print_exception(type(result.exception), result.exception, result.exception.__traceback__)

        assert result.exit_code == 0
        assert_contains_any(result.stdout.lower(), ["completed successfully", "01-setup"])

    @patch("cc_spec.commands.apply.update_kb")
    @patch("cc_spec.commands.apply.SubAgentExecutor")
    def test_apply_kb_strict_runs_task_level_kb_updates(
        self,
        mock_executor_class,
        mock_update_kb,
    ) -> None:
        """Test apply --kb-strict triggers baseline + per-task + final KB updates."""
        self._create_tasks_yaml()
        self._create_status()

        mock_update_kb.return_value = (
            KBUpdateSummary(
                scanned=1,
                added=0,
                changed=0,
                removed=0,
                chunks_written=0,
                reference_mode="index",
            ),
            ScanReport(
                included=1,
                excluded=0,
                excluded_reasons={},
                sample_included=[],
                sample_excluded=[],
                excluded_paths=[],
            ),
        )

        # Mock executor
        mock_executor = MagicMock()
        mock_executor_class.return_value = mock_executor

        mock_task = Task(
            task_id="01-SETUP",
            name="Project Setup",
            wave=0,
            status=ParserTaskStatus.IDLE,
            dependencies=[],
        )
        mock_wave = Wave(wave_number=0, tasks=[mock_task])
        mock_doc = TasksDocument(
            change_name="add-feature",
            waves=[mock_wave],
            all_tasks={"01-SETUP": mock_task},
        )
        mock_executor.doc = mock_doc

        mock_result = ExecutionResult(
            task_id="01-SETUP",
            success=True,
            output="Task completed successfully",
            duration_seconds=1.5,
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )

        async def mock_execute_wave_strict(
            wave_num,
            use_lock=True,
            skip_locked=False,
            resume=False,
            on_task_complete=None,
        ):
            if on_task_complete is not None:
                await on_task_complete(mock_result)
            return [mock_result]

        mock_executor.execute_wave_strict = mock_execute_wave_strict
        mock_executor.execute_wave = AsyncMock()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["apply", self.change_name, "--kb-strict", "--no-tech-check"])

        assert result.exit_code == 0

        # baseline + task-level + final sync
        assert mock_update_kb.call_count >= 3

        calls = list(mock_update_kb.call_args_list)
        attributions = [(kwargs.get("attribution") or {}) for _, kwargs in calls]

        # baseline should not touch list fields
        assert any(
            (kwargs.get("skip_list_fields") is True)
            and (attributions[i].get("step") == "apply.baseline")
            for i, (_, kwargs) in enumerate(calls)
        )

        # Ensure at least one call carries task attribution
        assert any(a.get("task_id") == "01-SETUP" for a in attributions)

    @patch("cc_spec.commands.apply.SubAgentExecutor")
    def test_apply_failed_execution(self, mock_executor_class) -> None:
        """Test apply command with failed task execution."""
        self._create_tasks_yaml()
        status_path = self._create_status()

        # Mock executor
        mock_executor = MagicMock()
        mock_executor_class.return_value = mock_executor

        # Create mock document
        mock_task = Task(
            task_id="01-SETUP",
            name="Project Setup",
            wave=0,
            status=ParserTaskStatus.IDLE,
            dependencies=[],
        )
        mock_wave = Wave(wave_number=0, tasks=[mock_task])
        mock_doc = TasksDocument(
            change_name="add-feature",
            waves=[mock_wave],
            all_tasks={"01-SETUP": mock_task},
        )
        mock_executor.doc = mock_doc

        # Mock failed execution result
        mock_result = ExecutionResult(
            task_id="01-SETUP",
            success=False,
            output="Task output",
            error="Simulated failure",
            duration_seconds=1.5,
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )

        async def mock_execute_wave(wave_num, use_lock=True, skip_locked=False, resume=False):
            return [mock_result]

        mock_executor.execute_wave = mock_execute_wave

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["apply", self.change_name])

        # Should exit with error code due to failure
        assert result.exit_code == 1
        assert_contains_any(result.stdout.lower(), ["失败", "failed"])


class TestFindResumeWave:
    """Tests for _find_resume_wave helper function."""

    def test_find_resume_wave_all_idle(self) -> None:
        """Test finding resume wave when all tasks are idle."""
        task1 = Task(task_id="01", name="Task 1", wave=0, status=ParserTaskStatus.IDLE)
        task2 = Task(task_id="02", name="Task 2", wave=1, status=ParserTaskStatus.IDLE)

        doc = TasksDocument(
            change_name="test",
            waves=[
                Wave(wave_number=0, tasks=[task1]),
                Wave(wave_number=1, tasks=[task2]),
            ],
            all_tasks={"01": task1, "02": task2},
        )

        assert _find_resume_wave(doc) == 0

    def test_find_resume_wave_partial_complete(self) -> None:
        """Test finding resume wave when some tasks are completed."""
        task1 = Task(task_id="01", name="Task 1", wave=0, status=ParserTaskStatus.COMPLETED)
        task2 = Task(task_id="02", name="Task 2", wave=1, status=ParserTaskStatus.IDLE)

        doc = TasksDocument(
            change_name="test",
            waves=[
                Wave(wave_number=0, tasks=[task1]),
                Wave(wave_number=1, tasks=[task2]),
            ],
            all_tasks={"01": task1, "02": task2},
        )

        assert _find_resume_wave(doc) == 1

    def test_find_resume_wave_failed_task(self) -> None:
        """Test finding resume wave when a task failed."""
        task1 = Task(task_id="01", name="Task 1", wave=0, status=ParserTaskStatus.FAILED)
        task2 = Task(task_id="02", name="Task 2", wave=1, status=ParserTaskStatus.IDLE)

        doc = TasksDocument(
            change_name="test",
            waves=[
                Wave(wave_number=0, tasks=[task1]),
                Wave(wave_number=1, tasks=[task2]),
            ],
            all_tasks={"01": task1, "02": task2},
        )

        # Should resume from wave with failed task
        assert _find_resume_wave(doc) == 0

    def test_find_resume_wave_all_completed(self) -> None:
        """Test finding resume wave when all tasks are completed."""
        task1 = Task(task_id="01", name="Task 1", wave=0, status=ParserTaskStatus.COMPLETED)
        task2 = Task(task_id="02", name="Task 2", wave=1, status=ParserTaskStatus.COMPLETED)

        doc = TasksDocument(
            change_name="test",
            waves=[
                Wave(wave_number=0, tasks=[task1]),
                Wave(wave_number=1, tasks=[task2]),
            ],
            all_tasks={"01": task1, "02": task2},
        )

        assert _find_resume_wave(doc) == 0


class TestApplyIntegration:
    """Integration tests for apply command."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.project_root = tmp_path
        self.cc_spec_dir = self.project_root / ".cc-spec"
        self.cc_spec_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.chdir(self.project_root)

    def test_apply_help(self) -> None:
        """Test apply command help display."""
        result = runner.invoke(app, ["apply", "--help"])

        assert result.exit_code == 0
        assert_contains_any(result.stdout, ["Execute tasks", "apply"])
        assert "--max-concurrent" in result.stdout
        assert "--resume" in result.stdout
        assert "--dry-run" in result.stdout

    def test_apply_command_registered(self) -> None:
        """Test that apply command is properly registered."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "apply" in result.stdout
