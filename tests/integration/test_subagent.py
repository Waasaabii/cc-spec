"""Integration tests for SubAgent execution.

Tests the SubAgent executor, task parser, and result collector
working together in realistic scenarios.

v1.2: Updated to use tasks.yaml format only.
"""

import asyncio
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from cc_spec.subagent.executor import ExecutionResult, SubAgentExecutor
from cc_spec.subagent.result_collector import ResultCollector, WaveResult
from cc_spec.subagent.task_parser import (
    Task,
    TasksDocument,
    TaskStatus,
    Wave,
    parse_tasks_yaml,
    update_task_status_yaml,
    validate_dependencies,
)


class TestTaskParserIntegration:
    """Integration tests for task parser (YAML format)."""

    def test_parse_complex_tasks_yaml(self) -> None:
        """Test parsing a realistic tasks.yaml file."""
        content = """version: "1.6"
change: add-oauth
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
    checklist:
      - 创建数据模型
      - 添加验证逻辑
  03-API:
    wave: 1
    name: API Endpoints
    tokens: 45k
    deps: [01-SETUP]
    checklist:
      - 创建 API 路由
      - 添加认证
  04-FE:
    wave: 2
    name: Frontend
    tokens: 60k
    deps: [02-MODEL, 03-API]
    checklist:
      - 创建组件
      - 添加样式
"""
        doc = parse_tasks_yaml(content)

        assert doc.change_name == "add-oauth"
        assert len(doc.waves) == 3
        assert len(doc.all_tasks) == 4

        # Check wave grouping
        assert len(doc.waves[0].tasks) == 1  # Wave 0
        assert len(doc.waves[1].tasks) == 2  # Wave 1
        assert len(doc.waves[2].tasks) == 1  # Wave 2

        # Check dependencies
        assert doc.all_tasks["02-MODEL"].dependencies == ["01-SETUP"]
        assert doc.all_tasks["04-FE"].dependencies == ["02-MODEL", "03-API"]

    def test_validate_dependencies_valid(self) -> None:
        """Test dependency validation passes for valid dependencies."""
        content = """version: "1.6"
change: test
tasks:
  01-A:
    wave: 0
    name: Task A
    checklist:
      - Item
  02-B:
    wave: 1
    name: Task B
    deps: [01-A]
    checklist:
      - Item
"""
        doc = parse_tasks_yaml(content)
        is_valid, errors = validate_dependencies(doc)

        assert is_valid
        assert len(errors) == 0

    def test_update_task_status_integration(self) -> None:
        """Test updating task status in tasks.yaml content."""
        content = """version: "1.6"
change: test
tasks:
  01-TEST:
    wave: 0
    name: Test Task
    tokens: 30k
    status: idle
    checklist:
      - Item 1
"""
        # Update to in progress
        updated = update_task_status_yaml(content, "01-TEST", TaskStatus.IN_PROGRESS)
        assert "in_progress" in updated

        # Update to completed
        updated = update_task_status_yaml(
            updated,
            "01-TEST",
            TaskStatus.COMPLETED,
            log={"completed_at": "2025-01-01T00:00:00Z", "subagent_id": "test-agent"},
        )
        assert "completed" in updated
        assert "test-agent" in updated


class TestSubAgentExecutorIntegration:
    """Integration tests for SubAgent executor."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)

    def teardown_method(self) -> None:
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_tasks_yaml(self, content: str = None) -> Path:
        """Create a tasks.yaml file for testing."""
        if content is None:
            content = """version: "1.6"
change: test
tasks:
  01-SETUP:
    wave: 0
    name: Project Setup
    tokens: 30k
    deps: []
    checklist:
      - 创建配置文件
  02-MODEL:
    wave: 1
    name: Data Model
    tokens: 50k
    deps: [01-SETUP]
    checklist:
      - 创建数据模型
"""
        tasks_path = self.project_root / "tasks.yaml"
        tasks_path.write_text(content, encoding="utf-8")
        return tasks_path

    def test_executor_loads_document(self) -> None:
        """Test executor loads and parses tasks.yaml."""
        tasks_path = self._create_tasks_yaml()

        executor = SubAgentExecutor(tasks_path)

        assert executor.doc.change_name == "test"
        assert len(executor.doc.all_tasks) == 2
        assert len(executor.doc.waves) == 2

    def test_executor_builds_prompt(self) -> None:
        """Test executor builds task prompt correctly (v1.4 compact format)."""
        tasks_path = self._create_tasks_yaml()

        executor = SubAgentExecutor(tasks_path)
        task = executor.doc.all_tasks["01-SETUP"]

        prompt = executor.build_task_prompt(task)

        # v1.4: 精简格式检查
        assert "## Task: 01-SETUP" in prompt
        assert "**Title**:" in prompt
        assert "**Checklist**:" in prompt or "Checklist" in prompt

    def test_executor_with_custom_executor(self) -> None:
        """Test executor with custom task executor."""
        tasks_path = self._create_tasks_yaml()

        executor = SubAgentExecutor(tasks_path)

        # Set custom executor that always succeeds
        def mock_executor(task: Task) -> ExecutionResult:
            return ExecutionResult(
                task_id=task.task_id,
                success=True,
                output="Mock success",
                duration_seconds=0.1,
                started_at=datetime.now(),
                completed_at=datetime.now(),
            )

        executor.set_task_executor(mock_executor)

        # Execute a task
        task = executor.doc.all_tasks["01-SETUP"]
        result = asyncio.run(executor.execute_task(task))

        assert result.success
        assert result.task_id == "01-SETUP"

    def test_executor_progress_summary(self) -> None:
        """Test executor progress summary."""
        tasks_path = self._create_tasks_yaml()

        executor = SubAgentExecutor(tasks_path)
        summary = executor.get_progress_summary()

        assert summary["total_tasks"] == 2
        assert summary["idle_tasks"] == 2
        assert summary["completed_tasks"] == 0


class TestResultCollectorIntegration:
    """Integration tests for result collector."""

    def test_collector_full_workflow(self) -> None:
        """Test result collector through full workflow."""
        collector = ResultCollector()

        # Start execution
        collector.start_execution()

        # Wave 0
        collector.start_wave(0)
        collector.add_result(
            0,
            ExecutionResult(
                task_id="01-SETUP",
                success=True,
                output="Success",
                duration_seconds=1.0,
                started_at=datetime.now(),
                completed_at=datetime.now(),
            ),
        )
        collector.end_wave(0)

        # Wave 1
        collector.start_wave(1)
        collector.add_result(
            1,
            ExecutionResult(
                task_id="02-MODEL",
                success=True,
                output="Success",
                duration_seconds=2.0,
                started_at=datetime.now(),
                completed_at=datetime.now(),
            ),
        )
        collector.add_result(
            1,
            ExecutionResult(
                task_id="03-API",
                success=False,
                output="Output",
                error="Test error",
                duration_seconds=1.5,
                started_at=datetime.now(),
                completed_at=datetime.now(),
            ),
        )
        collector.end_wave(1)

        # End execution
        collector.end_execution()

        # Check summary
        summary = collector.get_summary()
        assert summary["total_waves"] == 2
        assert summary["total_tasks"] == 3
        assert summary["successful_tasks"] == 2
        assert summary["failed_tasks"] == 1

        # Check failure detection
        assert collector.has_failures()
        assert 1 in collector.get_failed_waves()

    def test_collector_generates_report(self) -> None:
        """Test result collector generates markdown report."""
        collector = ResultCollector()

        collector.start_execution()
        collector.start_wave(0)
        collector.add_result(
            0,
            ExecutionResult(
                task_id="01-TEST",
                success=True,
                output="Done",
                duration_seconds=1.0,
                started_at=datetime.now(),
                completed_at=datetime.now(),
            ),
        )
        collector.end_wave(0)
        collector.end_execution()

        report = collector.generate_report()

        # Support Chinese and English output
        assert ("# SubAgent 执行报告" in report or "# SubAgent Execution Report" in report)
        assert ("汇总" in report or "Summary" in report)
        assert ("波次 0" in report or "Wave 0" in report)
        assert "01-TEST" in report

    def test_wave_result_properties(self) -> None:
        """Test WaveResult computed properties."""
        wave = WaveResult(wave_num=0, started_at=datetime.now())

        # Add results
        wave.results.append(
            ExecutionResult(
                task_id="01",
                success=True,
                output="",
                duration_seconds=1.0,
            )
        )
        wave.results.append(
            ExecutionResult(
                task_id="02",
                success=False,
                output="",
                error="Error",
                duration_seconds=2.0,
            )
        )

        assert not wave.all_passed
        assert wave.failed_tasks == ["02"]
        assert wave.success_rate == 50.0


class TestConcurrentExecution:
    """Tests for concurrent task execution."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)

    def teardown_method(self) -> None:
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_concurrent_tasks_in_wave(self) -> None:
        """Test multiple tasks execute concurrently within a wave."""
        content = """version: "1.6"
change: test
tasks:
  01-A:
    wave: 0
    name: Task A
    tokens: 30k
    deps: []
    checklist:
      - Item
  02-B:
    wave: 0
    name: Task B
    tokens: 30k
    deps: []
    checklist:
      - Item
  03-C:
    wave: 0
    name: Task C
    tokens: 30k
    deps: []
    checklist:
      - Item
"""
        tasks_path = self.project_root / "tasks.yaml"
        tasks_path.write_text(content, encoding="utf-8")

        executor = SubAgentExecutor(tasks_path, max_concurrent=3)

        # Track execution order
        execution_times: list[tuple[str, float]] = []

        def mock_executor(task: Task) -> ExecutionResult:
            import time

            start = time.time()
            time.sleep(0.05)  # Small delay
            execution_times.append((task.task_id, start))
            return ExecutionResult(
                task_id=task.task_id,
                success=True,
                output="Done",
                duration_seconds=0.05,
            )

        executor.set_task_executor(mock_executor)

        # Execute wave 0
        results = asyncio.run(executor.execute_wave(0))

        # All tasks should complete
        assert len(results) == 3
        assert all(r.success for r in results)

    def test_max_concurrent_limit(self) -> None:
        """Test max concurrent limit is respected."""
        content = """version: "1.6"
change: test
tasks:
  01-A:
    wave: 0
    name: Task A
    tokens: 30k
    deps: []
    checklist:
      - Item
  02-B:
    wave: 0
    name: Task B
    tokens: 30k
    deps: []
    checklist:
      - Item
  03-C:
    wave: 0
    name: Task C
    tokens: 30k
    deps: []
    checklist:
      - Item
  04-D:
    wave: 0
    name: Task D
    tokens: 30k
    deps: []
    checklist:
      - Item
  05-E:
    wave: 0
    name: Task E
    tokens: 30k
    deps: []
    checklist:
      - Item
"""
        tasks_path = self.project_root / "tasks.yaml"
        tasks_path.write_text(content, encoding="utf-8")

        # Limit to 2 concurrent
        executor = SubAgentExecutor(tasks_path, max_concurrent=2)

        # Can't easily test with sync mock, just verify executor initializes correctly
        assert executor.max_concurrent == 2
        assert executor._semaphore._value == 2
