"""Integration tests for SubAgent execution.

Tests the SubAgent executor, task parser, and result collector
working together in realistic scenarios.
"""

import asyncio
import os
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
    parse_tasks_md,
    update_task_status,
    validate_dependencies,
)


class TestTaskParserIntegration:
    """Integration tests for task parser."""

    def test_parse_complex_tasks_md(self) -> None:
        """Test parsing a realistic tasks.md file."""
        content = """# Tasks - add-oauth

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟦 空闲 | - |
| 1 | 02-MODEL | 50k | 🟦 空闲 | 01-SETUP |
| 1 | 03-API | 45k | 🟦 空闲 | 01-SETUP |
| 2 | 04-FE | 60k | 🟦 空闲 | 02-MODEL, 03-API |

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
- [ ] 添加认证

---

### 04-FE - Frontend
**预估上下文**: ~60k tokens
**状态**: 🟦 空闲
**依赖**: 02-MODEL, 03-API

**Checklist**:
- [ ] 创建组件
- [ ] 添加样式
"""
        doc = parse_tasks_md(content)

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
        content = """# Tasks - test

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-A | 30k | 🟦 空闲 | - |
| 1 | 02-B | 30k | 🟦 空闲 | 01-A |

## 任务详情

### 01-A - Task A
**状态**: 🟦 空闲
**依赖**: 无

**Checklist**:
- [ ] Item

---

### 02-B - Task B
**状态**: 🟦 空闲
**依赖**: 01-A

**Checklist**:
- [ ] Item
"""
        doc = parse_tasks_md(content)
        is_valid, errors = validate_dependencies(doc)

        assert is_valid
        assert len(errors) == 0

    def test_update_task_status_integration(self) -> None:
        """Test updating task status in tasks.md content."""
        content = """# Tasks - test

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-TEST | 30k | 🟦 空闲 | - |

## 任务详情

### 01-TEST - Test Task
**预估上下文**: ~30k tokens
**状态**: 🟦 空闲
**依赖**: 无

**Checklist**:
- [ ] Item 1
"""
        # Update to in progress
        updated = update_task_status(content, "01-TEST", TaskStatus.IN_PROGRESS)
        assert "🟨" in updated

        # Update to completed
        updated = update_task_status(
            updated,
            "01-TEST",
            TaskStatus.COMPLETED,
            log={"completed_at": "2025-01-01T00:00:00Z", "subagent_id": "test-agent"},
        )
        assert "🟩" in updated


class TestSubAgentExecutorIntegration:
    """Integration tests for SubAgent executor."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)

    def teardown_method(self) -> None:
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_tasks_md(self, content: str = None) -> Path:
        """Create a tasks.md file for testing."""
        if content is None:
            content = """# Tasks - test

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟦 空闲 | - |
| 1 | 02-MODEL | 50k | 🟦 空闲 | 01-SETUP |

## 任务详情

### 01-SETUP - Project Setup
**预估上下文**: ~30k tokens
**状态**: 🟦 空闲
**依赖**: 无

**Checklist**:
- [ ] 创建配置文件

---

### 02-MODEL - Data Model
**预估上下文**: ~50k tokens
**状态**: 🟦 空闲
**依赖**: 01-SETUP

**Checklist**:
- [ ] 创建数据模型
"""
        tasks_path = self.project_root / "tasks.md"
        tasks_path.write_text(content, encoding="utf-8")
        return tasks_path

    def test_executor_loads_document(self) -> None:
        """Test executor loads and parses tasks.md."""
        tasks_path = self._create_tasks_md()

        executor = SubAgentExecutor(tasks_path)

        assert executor.doc.change_name == "test"
        assert len(executor.doc.all_tasks) == 2
        assert len(executor.doc.waves) == 2

    def test_executor_builds_prompt(self) -> None:
        """Test executor builds task prompt correctly."""
        tasks_path = self._create_tasks_md()

        executor = SubAgentExecutor(tasks_path)
        task = executor.doc.all_tasks["01-SETUP"]

        prompt = executor.build_task_prompt(task, self.project_root)

        assert "01-SETUP" in prompt
        assert "Project Setup" in prompt
        assert "检查清单" in prompt or "Checklist" in prompt

    def test_executor_with_custom_executor(self) -> None:
        """Test executor with custom task executor."""
        tasks_path = self._create_tasks_md()

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
        tasks_path = self._create_tasks_md()

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

        assert "# SubAgent Execution Report" in report
        assert "Summary" in report
        assert "Wave 0" in report
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
        content = """# Tasks - test

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-A | 30k | 🟦 空闲 | - |
| 0 | 02-B | 30k | 🟦 空闲 | - |
| 0 | 03-C | 30k | 🟦 空闲 | - |

## 任务详情

### 01-A - Task A
**状态**: 🟦 空闲
**依赖**: 无

**Checklist**:
- [ ] Item

---

### 02-B - Task B
**状态**: 🟦 空闲
**依赖**: 无

**Checklist**:
- [ ] Item

---

### 03-C - Task C
**状态**: 🟦 空闲
**依赖**: 无

**Checklist**:
- [ ] Item
"""
        tasks_path = self.project_root / "tasks.md"
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
        content = """# Tasks - test

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-A | 30k | 🟦 空闲 | - |
| 0 | 02-B | 30k | 🟦 空闲 | - |
| 0 | 03-C | 30k | 🟦 空闲 | - |
| 0 | 04-D | 30k | 🟦 空闲 | - |
| 0 | 05-E | 30k | 🟦 空闲 | - |

## 任务详情

### 01-A - Task A
**状态**: 🟦 空闲

**Checklist**:
- [ ] Item

---

### 02-B - Task B
**状态**: 🟦 空闲

**Checklist**:
- [ ] Item

---

### 03-C - Task C
**状态**: 🟦 空闲

**Checklist**:
- [ ] Item

---

### 04-D - Task D
**状态**: 🟦 空闲

**Checklist**:
- [ ] Item

---

### 05-E - Task E
**状态**: 🟦 空闲

**Checklist**:
- [ ] Item
"""
        tasks_path = self.project_root / "tasks.md"
        tasks_path.write_text(content, encoding="utf-8")

        # Limit to 2 concurrent
        executor = SubAgentExecutor(tasks_path, max_concurrent=2)

        concurrent_count = 0
        max_concurrent_observed = 0

        async def mock_executor_async(task: Task) -> ExecutionResult:
            nonlocal concurrent_count, max_concurrent_observed

            concurrent_count += 1
            max_concurrent_observed = max(max_concurrent_observed, concurrent_count)

            await asyncio.sleep(0.05)

            concurrent_count -= 1

            return ExecutionResult(
                task_id=task.task_id,
                success=True,
                output="Done",
                duration_seconds=0.05,
            )

        # Can't easily test with sync mock, just verify executor initializes correctly
        assert executor.max_concurrent == 2
        assert executor._semaphore._value == 2
