"""Unit tests for SubAgent executor module."""

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cc_spec.core.scoring import CheckItem, CheckStatus
from cc_spec.subagent.executor import ExecutionResult, SubAgentExecutor
from cc_spec.subagent.result_collector import ResultCollector, WaveResult
from cc_spec.subagent.task_parser import Task, TaskStatus


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_execution_result_success(self) -> None:
        """Test creating ExecutionResult for successful task."""
        result = ExecutionResult(
            task_id="01-SETUP",
            success=True,
            output="Task completed successfully",
            duration_seconds=1.5,
        )

        assert result.task_id == "01-SETUP"
        assert result.success is True
        assert result.output == "Task completed successfully"
        assert result.error is None
        assert result.duration_seconds == 1.5

    def test_execution_result_failure(self) -> None:
        """Test creating ExecutionResult for failed task."""
        result = ExecutionResult(
            task_id="02-MODEL",
            success=False,
            output="Some output",
            error="Import error: module not found",
            duration_seconds=0.5,
        )

        assert result.task_id == "02-MODEL"
        assert result.success is False
        assert result.output == "Some output"
        assert result.error == "Import error: module not found"
        assert result.duration_seconds == 0.5

    def test_execution_result_defaults(self) -> None:
        """Test ExecutionResult with default values."""
        result = ExecutionResult(
            task_id="03-API",
            success=True,
            output="Done",
        )

        assert result.error is None
        assert result.duration_seconds == 0.0


class TestWaveResult:
    """Tests for WaveResult dataclass."""

    def test_wave_result_creation(self) -> None:
        """Test creating WaveResult."""
        started = datetime.now()
        wave = WaveResult(wave_num=0, started_at=started)

        assert wave.wave_num == 0
        assert wave.started_at == started
        assert wave.completed_at is None
        assert len(wave.results) == 0

    def test_wave_result_all_passed(self) -> None:
        """Test all_passed property when all tasks succeed."""
        wave = WaveResult(
            wave_num=0,
            started_at=datetime.now(),
            results=[
                ExecutionResult("01-A", True, "ok", duration_seconds=1.0),
                ExecutionResult("01-B", True, "ok", duration_seconds=1.0),
            ],
        )

        assert wave.all_passed is True

    def test_wave_result_not_all_passed(self) -> None:
        """Test all_passed property when some tasks fail."""
        wave = WaveResult(
            wave_num=0,
            started_at=datetime.now(),
            results=[
                ExecutionResult("01-A", True, "ok", duration_seconds=1.0),
                ExecutionResult("01-B", False, "err", error="Failed", duration_seconds=0.5),
            ],
        )

        assert wave.all_passed is False

    def test_wave_result_failed_tasks(self) -> None:
        """Test failed_tasks property."""
        wave = WaveResult(
            wave_num=0,
            started_at=datetime.now(),
            results=[
                ExecutionResult("01-A", True, "ok", duration_seconds=1.0),
                ExecutionResult("01-B", False, "err", error="Failed", duration_seconds=0.5),
                ExecutionResult("01-C", False, "err", error="Failed", duration_seconds=0.5),
            ],
        )

        failed = wave.failed_tasks
        assert len(failed) == 2
        assert "01-B" in failed
        assert "01-C" in failed

    def test_wave_result_duration_seconds(self) -> None:
        """Test duration_seconds property."""
        started = datetime(2024, 1, 15, 10, 0, 0)
        completed = datetime(2024, 1, 15, 10, 0, 5)

        wave = WaveResult(
            wave_num=0,
            started_at=started,
            completed_at=completed,
        )

        assert wave.duration_seconds == 5.0

    def test_wave_result_duration_not_completed(self) -> None:
        """Test duration_seconds when wave not completed."""
        wave = WaveResult(
            wave_num=0,
            started_at=datetime.now(),
        )

        assert wave.duration_seconds == 0.0

    def test_wave_result_success_rate(self) -> None:
        """Test success_rate property."""
        wave = WaveResult(
            wave_num=0,
            started_at=datetime.now(),
            results=[
                ExecutionResult("01-A", True, "ok", duration_seconds=1.0),
                ExecutionResult("01-B", True, "ok", duration_seconds=1.0),
                ExecutionResult("01-C", False, "err", error="Failed", duration_seconds=0.5),
            ],
        )

        assert wave.success_rate == pytest.approx(66.67, rel=0.01)

    def test_wave_result_success_rate_empty(self) -> None:
        """Test success_rate with no results."""
        wave = WaveResult(wave_num=0, started_at=datetime.now())

        assert wave.success_rate == 0.0


class TestResultCollector:
    """Tests for ResultCollector class."""

    def test_result_collector_initialization(self) -> None:
        """Test ResultCollector initialization."""
        collector = ResultCollector()

        assert len(collector.wave_results) == 0
        assert collector.start_time is None
        assert collector.end_time is None

    def test_start_and_end_execution(self) -> None:
        """Test recording start and end of execution."""
        collector = ResultCollector()

        collector.start_execution()
        assert collector.start_time is not None

        collector.end_execution()
        assert collector.end_time is not None
        assert collector.end_time >= collector.start_time

    def test_start_wave(self) -> None:
        """Test starting a wave."""
        collector = ResultCollector()

        collector.start_wave(0)
        assert 0 in collector.wave_results
        assert collector.wave_results[0].wave_num == 0
        assert collector.wave_results[0].started_at is not None

    def test_add_result(self) -> None:
        """Test adding a result to a wave."""
        collector = ResultCollector()
        collector.start_wave(0)

        result = ExecutionResult("01-A", True, "ok", duration_seconds=1.0)
        collector.add_result(0, result)

        assert len(collector.wave_results[0].results) == 1
        assert collector.wave_results[0].results[0] == result

    def test_add_result_wave_not_started(self) -> None:
        """Test adding result to wave that hasn't been started."""
        collector = ResultCollector()

        result = ExecutionResult("01-A", True, "ok", duration_seconds=1.0)

        with pytest.raises(ValueError, match="(has not been started|未启动|尚未开始)"):
            collector.add_result(0, result)

    def test_end_wave(self) -> None:
        """Test ending a wave."""
        collector = ResultCollector()
        collector.start_wave(0)

        collector.end_wave(0)
        assert collector.wave_results[0].completed_at is not None

    def test_end_wave_not_started(self) -> None:
        """Test ending wave that hasn't been started."""
        collector = ResultCollector()

        with pytest.raises(ValueError, match="(has not been started|未启动|尚未开始)"):
            collector.end_wave(0)

    def test_get_summary(self) -> None:
        """Test getting execution summary."""
        collector = ResultCollector()
        collector.start_execution()

        # Wave 0
        collector.start_wave(0)
        collector.add_result(0, ExecutionResult("01-A", True, "ok", duration_seconds=1.0))
        collector.add_result(0, ExecutionResult("01-B", True, "ok", duration_seconds=1.0))
        collector.end_wave(0)

        # Wave 1
        collector.start_wave(1)
        collector.add_result(1, ExecutionResult("02-A", True, "ok", duration_seconds=1.0))
        collector.add_result(1, ExecutionResult("02-B", False, "err", error="Fail", duration_seconds=0.5))
        collector.end_wave(1)

        collector.end_execution()

        summary = collector.get_summary()

        assert summary["total_waves"] == 2
        assert summary["total_tasks"] == 4
        assert summary["successful_tasks"] == 3
        assert summary["failed_tasks"] == 1
        assert summary["success_rate"] == 75.0
        assert summary["total_duration_seconds"] >= 0

    def test_generate_report(self) -> None:
        """Test generating markdown report."""
        collector = ResultCollector()
        collector.start_execution()

        collector.start_wave(0)
        collector.add_result(0, ExecutionResult("01-A", True, "ok", duration_seconds=1.0))
        collector.end_wave(0)

        collector.end_execution()

        report = collector.generate_report()

        # Support Chinese and English output
        assert ("# SubAgent 执行报告" in report or "# SubAgent Execution Report" in report)
        assert ("## 汇总" in report or "## Summary" in report)
        assert ("## 波次详情" in report or "## Wave Details" in report)
        assert ("### 波次 0" in report or "### Wave 0" in report)
        assert "01-A" in report

    def test_has_failures(self) -> None:
        """Test checking if execution has failures."""
        collector = ResultCollector()

        collector.start_wave(0)
        collector.add_result(0, ExecutionResult("01-A", True, "ok", duration_seconds=1.0))
        collector.end_wave(0)

        assert collector.has_failures() is False

        collector.start_wave(1)
        collector.add_result(1, ExecutionResult("02-A", False, "err", error="Fail", duration_seconds=0.5))
        collector.end_wave(1)

        assert collector.has_failures() is True

    def test_get_failed_waves(self) -> None:
        """Test getting list of failed waves."""
        collector = ResultCollector()

        collector.start_wave(0)
        collector.add_result(0, ExecutionResult("01-A", True, "ok", duration_seconds=1.0))
        collector.end_wave(0)

        collector.start_wave(1)
        collector.add_result(1, ExecutionResult("02-A", False, "err", error="Fail", duration_seconds=0.5))
        collector.end_wave(1)

        failed_waves = collector.get_failed_waves()
        assert len(failed_waves) == 1
        assert 1 in failed_waves


class TestSubAgentExecutor:
    """Tests for SubAgentExecutor class."""

    @pytest.fixture
    def sample_tasks_yaml(self, tmp_path: Path) -> Path:
        """Create a sample tasks.yaml file for testing."""
        content = """version: "1.6"
change: test-change
tasks:
  01-SETUP:
    wave: 0
    name: Project Setup
    tokens: 30k
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
    deps: [01-SETUP]
    docs:
      - docs/plan/spec.md
      - src/models/README.md
    code:
      - src/models/
    checklist:
      - 创建数据模型
      - 编写单元测试
  03-API:
    wave: 1
    name: API Implementation
    tokens: 45k
    deps: [01-SETUP]
    docs:
      - docs/api/spec.md
    code:
      - src/api/
    checklist:
      - 实现API端点
"""
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text(content, encoding="utf-8")
        return tasks_file

    def test_executor_initialization(self, sample_tasks_yaml: Path) -> None:
        """Test SubAgentExecutor initialization."""
        executor = SubAgentExecutor(
            tasks_md_path=sample_tasks_yaml,
            max_concurrent=5,
            timeout_ms=60000,
        )

        assert executor.tasks_md_path == sample_tasks_yaml
        assert executor.max_concurrent == 5
        assert executor.timeout_ms == 60000
        assert executor.doc.change_name == "test-change"
        assert len(executor.doc.all_tasks) == 3

    def test_executor_initialization_file_not_found(self, tmp_path: Path) -> None:
        """Test SubAgentExecutor initialization with non-existent file."""
        with pytest.raises(FileNotFoundError):
            SubAgentExecutor(tasks_md_path=tmp_path / "nonexistent.yaml")

    def test_build_task_prompt(self, sample_tasks_yaml: Path) -> None:
        """Test building task prompt (compact format)."""
        executor = SubAgentExecutor(tasks_md_path=sample_tasks_yaml)
        task = executor.doc.all_tasks["01-SETUP"]

        prompt = executor.build_task_prompt(task)

        # 精简格式检查
        assert "## Task: 01-SETUP" in prompt
        assert "**Title**:" in prompt
        assert "**Checklist**:" in prompt
        assert "创建配置文件" in prompt
        assert "添加环境变量" in prompt
        assert "**Execution**:" in prompt

    def test_build_task_prompt_with_dependencies(self, sample_tasks_yaml: Path) -> None:
        """Test building prompt for task with dependencies (compact format)."""
        executor = SubAgentExecutor(tasks_md_path=sample_tasks_yaml)
        task = executor.doc.all_tasks["02-MODEL"]

        prompt = executor.build_task_prompt(task)

        # 依赖检查
        assert "**Dependencies**:" in prompt
        assert "01-SETUP" in prompt

    @pytest.mark.asyncio
    async def test_execute_task(self, sample_tasks_yaml: Path) -> None:
        """Test executing a single task."""
        executor = SubAgentExecutor(tasks_md_path=sample_tasks_yaml)
        task = executor.doc.all_tasks["01-SETUP"]

        result = await executor.execute_task(task)

        assert result.task_id == "01-SETUP"
        assert isinstance(result.success, bool)
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_execute_wave(self, sample_tasks_yaml: Path) -> None:
        """Test executing a wave of tasks."""
        executor = SubAgentExecutor(tasks_md_path=sample_tasks_yaml)

        results = await executor.execute_wave(0)

        assert len(results) == 1
        assert results[0].task_id == "01-SETUP"

        # Verify status was updated
        updated_content = sample_tasks_yaml.read_text(encoding="utf-8")
        assert "01-SETUP" in updated_content

    @pytest.mark.asyncio
    async def test_execute_wave_invalid_wave(self, sample_tasks_yaml: Path) -> None:
        """Test executing invalid wave number."""
        executor = SubAgentExecutor(tasks_md_path=sample_tasks_yaml)

        with pytest.raises(ValueError, match="(No tasks found|未找到.*任务|不存在)"):
            await executor.execute_wave(99)

    @pytest.mark.asyncio
    async def test_execute_wave_already_executed(self, sample_tasks_yaml: Path) -> None:
        """Test executing wave where all tasks already executed."""
        executor = SubAgentExecutor(tasks_md_path=sample_tasks_yaml)

        # Execute wave once
        await executor.execute_wave(0)

        # Reload executor to pick up status changes
        executor = SubAgentExecutor(tasks_md_path=sample_tasks_yaml)

        # Try to execute again
        results = await executor.execute_wave(0)

        # Should return empty list as no IDLE tasks
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_execute_all(self, sample_tasks_yaml: Path) -> None:
        """Test executing all waves."""
        # Mock execute_task to always succeed
        executor = SubAgentExecutor(tasks_md_path=sample_tasks_yaml)

        async def mock_execute_success(task: Task) -> ExecutionResult:
            await asyncio.sleep(0.01)
            return ExecutionResult(
                task_id=task.task_id,
                success=True,
                output=f"Task {task.task_id} completed",
                duration_seconds=0.01,
            )

        executor.execute_task = mock_execute_success  # type: ignore

        results = await executor.execute_all()

        # Should have executed 2 waves
        assert len(results) == 2
        assert 0 in results
        assert 1 in results

    @pytest.mark.asyncio
    async def test_execute_all_stops_on_failure(self, sample_tasks_yaml: Path) -> None:
        """Test that execute_all stops when a task fails."""
        executor = SubAgentExecutor(tasks_md_path=sample_tasks_yaml)

        # Mock execute_task to fail on wave 0
        async def mock_execute_fail(task: Task) -> ExecutionResult:
            await asyncio.sleep(0.01)
            return ExecutionResult(
                task_id=task.task_id,
                success=False,
                output="",
                error="Simulated failure",
                duration_seconds=0.01,
            )

        executor.execute_task = mock_execute_fail  # type: ignore

        results = await executor.execute_all()

        # Should only have wave 0 results (stopped after failure)
        assert len(results) == 1
        assert 0 in results
        assert 1 not in results

    @pytest.mark.asyncio
    async def test_execute_all_with_start_wave(self, sample_tasks_yaml: Path) -> None:
        """Test executing from a specific start wave."""
        executor = SubAgentExecutor(tasks_md_path=sample_tasks_yaml)

        async def mock_execute_success(task: Task) -> ExecutionResult:
            await asyncio.sleep(0.01)
            return ExecutionResult(
                task_id=task.task_id,
                success=True,
                output=f"Task {task.task_id} completed",
                duration_seconds=0.01,
            )

        executor.execute_task = mock_execute_success  # type: ignore

        results = await executor.execute_all(start_wave=1)

        # Should only have wave 1
        assert 0 not in results
        assert 1 in results

    @pytest.mark.asyncio
    async def test_execute_all_invalid_start_wave(self, sample_tasks_yaml: Path) -> None:
        """Test execute_all with invalid start_wave."""
        executor = SubAgentExecutor(tasks_md_path=sample_tasks_yaml)

        with pytest.raises(ValueError, match="(start_wave must be|start_wave 必须|起始波次)"):
            await executor.execute_all(start_wave=-1)

    def test_get_progress_summary(self, sample_tasks_yaml: Path) -> None:
        """Test getting progress summary."""
        executor = SubAgentExecutor(tasks_md_path=sample_tasks_yaml)

        summary = executor.get_progress_summary()

        assert summary["total_tasks"] == 3
        assert summary["idle_tasks"] == 3
        assert summary["completed_tasks"] == 0
        assert summary["failed_tasks"] == 0
        assert summary["in_progress_tasks"] == 0
        assert summary["completion_percentage"] == 0.0
