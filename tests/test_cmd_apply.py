"""Unit tests for apply command."""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

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

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        self.cc_spec_dir = self.project_root / ".cc-spec"
        self.changes_dir = self.cc_spec_dir / "changes"
        self.change_name = "add-feature"
        self.change_dir = self.changes_dir / self.change_name

        # Create project structure
        self.cc_spec_dir.mkdir(parents=True, exist_ok=True)
        self.change_dir.mkdir(parents=True, exist_ok=True)

        # Save original working directory
        self.original_cwd = os.getcwd()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        import shutil

        # Restore original working directory
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_tasks_md(self, content: str = None) -> Path:
        """Helper to create tasks.md with task definitions."""
        if content is None:
            content = """# Tasks - add-feature

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟦 空闲 | - |
| 1 | 02-MODEL | 50k | 🟦 空闲 | 01-SETUP |
| 1 | 03-API | 45k | 🟦 空闲 | 01-SETUP |

## 任务详情

### 01-SETUP - Project Setup
**预估上下文**: ~30k tokens
**状态**: 🟦 空闲
**依赖**: 无

**必读文档**:
- docs/plan/spec.md

**核心代码入口**:
- src/config/

**Checklist**:
- [ ] 创建配置文件
- [ ] 添加环境变量

---

### 02-MODEL - Data Model
**预估上下文**: ~50k tokens
**状态**: 🟦 空闲
**依赖**: 01-SETUP

**必读文档**:
- docs/plan/spec.md

**核心代码入口**:
- src/models/

**Checklist**:
- [ ] 创建数据模型
- [ ] 添加验证逻辑

---

### 03-API - API Endpoints
**预估上下文**: ~45k tokens
**状态**: 🟦 空闲
**依赖**: 01-SETUP

**Checklist**:
- [ ] 创建 API 路由
- [ ] 添加认证中间件
"""
        tasks_path = self.change_dir / "tasks.md"
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
        assert "未找到" in result.stdout or "not found" in result.stdout

    def test_apply_without_tasks_md(self) -> None:
        """Test apply command fails when tasks.md doesn't exist."""
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["apply", self.change_name])
        assert result.exit_code == 1
        assert "tasks.md" in result.stdout

    def test_apply_dry_run(self) -> None:
        """Test apply command dry run mode shows execution plan."""
        self._create_tasks_md()
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["apply", self.change_name, "--dry-run"])

        assert result.exit_code == 0
        assert "dry" in result.stdout.lower() or "模拟" in result.stdout
        assert "01-SETUP" in result.stdout
        assert "02-MODEL" in result.stdout

    def test_apply_with_no_pending_tasks(self) -> None:
        """Test apply command when all tasks are completed."""
        # Create tasks.md with all completed tasks
        tasks_content = """# Tasks - add-feature

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟩 完成 | - |

## 任务详情

### 01-SETUP - Project Setup
**预估上下文**: ~30k tokens
**状态**: 🟩 完成
**依赖**: 无

**Checklist**:
- [x] 创建配置文件
- [x] 添加环境变量
"""
        self._create_tasks_md(tasks_content)
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["apply", self.change_name])

        assert result.exit_code == 0
        assert "没有待执行任务" in result.stdout or "No pending tasks" in result.stdout or "已完成" in result.stdout

    def test_apply_displays_task_summary(self) -> None:
        """Test apply command displays task summary."""
        self._create_tasks_md()
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
        self._create_tasks_md()
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(
            app, ["apply", self.change_name, "--max-concurrent", "5", "--dry-run"]
        )

        assert result.exit_code == 0

    def test_apply_without_explicit_change_name(self) -> None:
        """Test apply command uses current active change when name not provided."""
        self._create_tasks_md()
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["apply", "--dry-run"])

        assert result.exit_code == 0
        assert self.change_name in result.stdout or "Dry run mode" in result.stdout


class TestApplyExecution:
    """Tests for apply command execution with mocked executor."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        self.cc_spec_dir = self.project_root / ".cc-spec"
        self.changes_dir = self.cc_spec_dir / "changes"
        self.change_name = "add-feature"
        self.change_dir = self.changes_dir / self.change_name

        # Create project structure
        self.cc_spec_dir.mkdir(parents=True, exist_ok=True)
        self.change_dir.mkdir(parents=True, exist_ok=True)

        # Save original working directory
        self.original_cwd = os.getcwd()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        import shutil

        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_tasks_md(self) -> Path:
        """Helper to create tasks.md."""
        content = """# Tasks - add-feature

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟦 空闲 | - |

## 任务详情

### 01-SETUP - Project Setup
**预估上下文**: ~30k tokens
**状态**: 🟦 空闲
**依赖**: 无

**Checklist**:
- [ ] 创建配置文件
"""
        tasks_path = self.change_dir / "tasks.md"
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
        self._create_tasks_md()
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
        async def mock_execute_wave(wave_num, use_lock=True, skip_locked=False):
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
        assert "completed successfully" in result.stdout.lower() or "01-SETUP" in result.stdout

    @patch("cc_spec.commands.apply.SubAgentExecutor")
    def test_apply_failed_execution(self, mock_executor_class) -> None:
        """Test apply command with failed task execution."""
        self._create_tasks_md()
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

        async def mock_execute_wave(wave_num, use_lock=True, skip_locked=False):
            return [mock_result]

        mock_executor.execute_wave = mock_execute_wave

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["apply", self.change_name])

        # Should exit with error code due to failure
        assert result.exit_code == 1
        assert "失败" in result.stdout or "failed" in result.stdout.lower()


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

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        self.cc_spec_dir = self.project_root / ".cc-spec"

        # Create .cc-spec directory
        self.cc_spec_dir.mkdir(parents=True, exist_ok=True)

        # Save original working directory
        self.original_cwd = os.getcwd()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        import shutil

        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_apply_help(self) -> None:
        """Test apply command help display."""
        result = runner.invoke(app, ["apply", "--help"])

        assert result.exit_code == 0
        assert "Execute tasks" in result.stdout or "apply" in result.stdout
        assert "--max-concurrent" in result.stdout
        assert "--resume" in result.stdout
        assert "--dry-run" in result.stdout

    def test_apply_command_registered(self) -> None:
        """Test that apply command is properly registered."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "apply" in result.stdout
