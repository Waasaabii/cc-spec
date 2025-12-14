"""Unit tests for task_parser module."""

import pytest

from cc_spec.core.scoring import CheckItem, CheckStatus
from cc_spec.subagent.task_parser import (
    ExecutionLog,
    Task,
    TaskStatus,
    TasksDocument,
    Wave,
    get_pending_tasks,
    get_task_by_id,
    get_tasks_by_wave,
    parse_tasks_md,
    update_checklist_item,
    update_task_status,
    validate_dependencies,
)


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_enum_values(self) -> None:
        """Test TaskStatus enum values."""
        assert TaskStatus.IDLE.value == "idle"
        assert TaskStatus.IN_PROGRESS.value == "in_progress"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.TIMEOUT.value == "timeout"


class TestExecutionLog:
    """Tests for ExecutionLog dataclass."""

    def test_execution_log_creation(self) -> None:
        """Test creating ExecutionLog."""
        log = ExecutionLog(
            completed_at="2024-01-15T10:40:00Z",
            subagent_id="agent_abc123",
            notes="Completed successfully",
        )
        assert log.completed_at == "2024-01-15T10:40:00Z"
        assert log.subagent_id == "agent_abc123"
        assert log.notes == "Completed successfully"

    def test_execution_log_defaults(self) -> None:
        """Test ExecutionLog with default values."""
        log = ExecutionLog()
        assert log.completed_at is None
        assert log.subagent_id is None
        assert log.notes is None


class TestTask:
    """Tests for Task dataclass."""

    def test_task_creation(self) -> None:
        """Test creating Task with all fields."""
        log = ExecutionLog(completed_at="2024-01-15T10:40:00Z", subagent_id="agent_123")
        checklist_items = [
            CheckItem(description="Setup config", status=CheckStatus.PASSED, score=10),
            CheckItem(description="Run tests", status=CheckStatus.FAILED, score=0),
        ]

        task = Task(
            task_id="01-SETUP",
            name="Project Setup",
            wave=0,
            status=TaskStatus.COMPLETED,
            dependencies=["00-INIT"],
            estimated_tokens=30000,
            required_docs=["docs/plan/spec.md"],
            code_entry_points=["src/config/"],
            checklist_items=checklist_items,
            execution_log=log,
        )

        assert task.task_id == "01-SETUP"
        assert task.name == "Project Setup"
        assert task.wave == 0
        assert task.status == TaskStatus.COMPLETED
        assert task.dependencies == ["00-INIT"]
        assert task.estimated_tokens == 30000
        assert len(task.required_docs) == 1
        assert len(task.code_entry_points) == 1
        assert len(task.checklist_items) == 2
        assert task.execution_log == log

    def test_task_defaults(self) -> None:
        """Test Task with default values."""
        task = Task(
            task_id="01-SETUP",
            name="Project Setup",
            wave=0,
            status=TaskStatus.IDLE,
        )
        assert task.dependencies == []
        assert task.estimated_tokens == 0
        assert task.required_docs == []
        assert task.code_entry_points == []
        assert task.checklist_items == []
        assert task.execution_log is None


class TestWave:
    """Tests for Wave dataclass."""

    def test_wave_creation(self) -> None:
        """Test creating Wave with tasks."""
        tasks = [
            Task(task_id="01-SETUP", name="Setup", wave=0, status=TaskStatus.IDLE),
            Task(task_id="02-MODEL", name="Model", wave=0, status=TaskStatus.IDLE),
        ]
        wave = Wave(wave_number=0, tasks=tasks)

        assert wave.wave_number == 0
        assert len(wave.tasks) == 2
        assert wave.tasks[0].task_id == "01-SETUP"


class TestTasksDocument:
    """Tests for TasksDocument dataclass."""

    def test_tasks_document_creation(self) -> None:
        """Test creating TasksDocument."""
        task1 = Task(task_id="01-SETUP", name="Setup", wave=0, status=TaskStatus.IDLE)
        task2 = Task(task_id="02-MODEL", name="Model", wave=1, status=TaskStatus.IDLE)

        wave0 = Wave(wave_number=0, tasks=[task1])
        wave1 = Wave(wave_number=1, tasks=[task2])

        doc = TasksDocument(
            change_name="add-feature",
            waves=[wave0, wave1],
            all_tasks={"01-SETUP": task1, "02-MODEL": task2},
        )

        assert doc.change_name == "add-feature"
        assert len(doc.waves) == 2
        assert len(doc.all_tasks) == 2
        assert doc.all_tasks["01-SETUP"] == task1


class TestParseTasksMd:
    """Tests for parse_tasks_md function."""

    def test_parse_complete_tasks_md(self) -> None:
        """Test parsing a complete tasks.md file."""
        content = """# Tasks - add-feature

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟩 完成 | - |
| 1 | 02-MODEL | 50k | 🟨 进行中 | 01-SETUP |
| 1 | 03-API | 45k | 🟦 空闲 | 01-SETUP |
| 2 | 04-FE | 60k | 🟦 空闲 | 03-API |

## 任务详情

### 01-SETUP - Project Setup
**预估上下文**: ~30k tokens
**状态**: 🟩 完成
**依赖**: 无

**必读文档**:
- docs/plan/spec.md
- .cc-spec/changes/add-feature/design.md

**核心代码入口**:
- src/config/

**Checklist**:
- [x] 创建配置文件
- [x] 添加环境变量

**执行日志**:
- 完成时间: 2024-01-15T10:40:00Z
- SubAgent ID: agent_abc123

---

### 02-MODEL - Data Model
**预估上下文**: ~50k tokens
**状态**: 🟨 进行中
**依赖**: 01-SETUP

**必读文档**:
- docs/plan/spec.md
- src/models/README.md

**核心代码入口**:
- src/models/

**Checklist**:
- [ ] 创建数据模型
- [ ] 添加验证逻辑
- [ ] 编写单元测试

---

### 03-API - API Implementation
**预估上下文**: ~45k tokens
**状态**: 🟦 空闲
**依赖**: 01-SETUP

**必读文档**:
- docs/api/spec.md

**核心代码入口**:
- src/api/

**Checklist**:
- [ ] 实现API端点

---

### 04-FE - Frontend
**预估上下文**: ~60k tokens
**状态**: 🟦 空闲
**依赖**: 03-API

**必读文档**:
- docs/frontend/spec.md

**核心代码入口**:
- src/frontend/

**Checklist**:
- [ ] 实现前端组件
"""

        doc = parse_tasks_md(content)

        # Verify document structure
        assert doc.change_name == "add-feature"
        assert len(doc.waves) == 3
        assert len(doc.all_tasks) == 4

        # Verify wave 0
        wave0_tasks = doc.waves[0].tasks
        assert len(wave0_tasks) == 1
        assert wave0_tasks[0].task_id == "01-SETUP"
        assert wave0_tasks[0].status == TaskStatus.COMPLETED

        # Verify wave 1
        wave1_tasks = doc.waves[1].tasks
        assert len(wave1_tasks) == 2
        assert {t.task_id for t in wave1_tasks} == {"02-MODEL", "03-API"}

        # Verify task details
        task1 = doc.all_tasks["01-SETUP"]
        assert task1.name == "Project Setup"
        assert task1.wave == 0
        assert task1.status == TaskStatus.COMPLETED
        assert task1.dependencies == []
        assert task1.estimated_tokens == 30000
        assert len(task1.required_docs) == 2
        assert len(task1.code_entry_points) == 1
        assert len(task1.checklist_items) == 2
        assert task1.checklist_items[0].status == CheckStatus.PASSED
        assert task1.execution_log is not None
        assert task1.execution_log.completed_at == "2024-01-15T10:40:00Z"
        assert task1.execution_log.subagent_id == "agent_abc123"

        # Verify task with dependencies
        task2 = doc.all_tasks["02-MODEL"]
        assert task2.name == "Data Model"
        assert task2.wave == 1
        assert task2.status == TaskStatus.IN_PROGRESS
        assert task2.dependencies == ["01-SETUP"]
        assert task2.estimated_tokens == 50000
        assert len(task2.checklist_items) == 3

    def test_parse_minimal_tasks_md(self) -> None:
        """Test parsing minimal tasks.md without optional fields."""
        content = """# Tasks - minimal-test

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-BASIC | 10k | 🟦 空闲 | - |

## 任务详情

### 01-BASIC - Basic Task
**预估上下文**: ~10k tokens
**状态**: 🟦 空闲
"""

        doc = parse_tasks_md(content)

        assert doc.change_name == "minimal-test"
        assert len(doc.waves) == 1
        assert len(doc.all_tasks) == 1

        task = doc.all_tasks["01-BASIC"]
        assert task.task_id == "01-BASIC"
        assert task.name == "Basic Task"
        assert task.status == TaskStatus.IDLE
        assert task.dependencies == []
        assert task.required_docs == []
        assert task.code_entry_points == []
        assert task.checklist_items == []

    def test_parse_tasks_md_invalid_title(self) -> None:
        """Test parsing tasks.md with invalid title."""
        content = """# Invalid Title

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-TEST | 10k | 🟦 空闲 | - |
"""

        with pytest.raises(ValueError, match="tasks.md 标题格式无效"):
            parse_tasks_md(content)

    def test_parse_tasks_md_with_multiple_dependencies(self) -> None:
        """Test parsing tasks with multiple dependencies."""
        content = """# Tasks - test-deps

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-A | 10k | 🟦 空闲 | - |
| 0 | 01-B | 10k | 🟦 空闲 | - |
| 1 | 02-C | 10k | 🟦 空闲 | 01-A, 01-B |

## 任务详情

### 01-A - Task A
**预估上下文**: ~10k tokens

---

### 01-B - Task B
**预估上下文**: ~10k tokens

---

### 02-C - Task C
**预估上下文**: ~10k tokens
"""

        doc = parse_tasks_md(content)

        task_c = doc.all_tasks["02-C"]
        assert len(task_c.dependencies) == 2
        assert "01-A" in task_c.dependencies
        assert "01-B" in task_c.dependencies


class TestGetTasksByWave:
    """Tests for get_tasks_by_wave function."""

    def test_get_tasks_by_wave_existing(self) -> None:
        """Test getting tasks from an existing wave."""
        task1 = Task(task_id="01-A", name="A", wave=0, status=TaskStatus.IDLE)
        task2 = Task(task_id="02-B", name="B", wave=1, status=TaskStatus.IDLE)

        doc = TasksDocument(
            change_name="test",
            waves=[Wave(wave_number=0, tasks=[task1]), Wave(wave_number=1, tasks=[task2])],
            all_tasks={"01-A": task1, "02-B": task2},
        )

        tasks = get_tasks_by_wave(doc, 0)
        assert len(tasks) == 1
        assert tasks[0].task_id == "01-A"

    def test_get_tasks_by_wave_nonexistent(self) -> None:
        """Test getting tasks from a non-existent wave."""
        doc = TasksDocument(change_name="test", waves=[], all_tasks={})
        tasks = get_tasks_by_wave(doc, 99)
        assert len(tasks) == 0


class TestGetPendingTasks:
    """Tests for get_pending_tasks function."""

    def test_get_pending_tasks(self) -> None:
        """Test getting all pending (IDLE) tasks."""
        task1 = Task(task_id="01-A", name="A", wave=0, status=TaskStatus.IDLE)
        task2 = Task(task_id="02-B", name="B", wave=0, status=TaskStatus.COMPLETED)
        task3 = Task(task_id="03-C", name="C", wave=1, status=TaskStatus.IDLE)

        doc = TasksDocument(
            change_name="test",
            waves=[Wave(wave_number=0, tasks=[task1, task2]), Wave(wave_number=1, tasks=[task3])],
            all_tasks={"01-A": task1, "02-B": task2, "03-C": task3},
        )

        pending = get_pending_tasks(doc)
        assert len(pending) == 2
        assert {t.task_id for t in pending} == {"01-A", "03-C"}

    def test_get_pending_tasks_empty(self) -> None:
        """Test getting pending tasks when none exist."""
        task1 = Task(task_id="01-A", name="A", wave=0, status=TaskStatus.COMPLETED)
        doc = TasksDocument(
            change_name="test",
            waves=[Wave(wave_number=0, tasks=[task1])],
            all_tasks={"01-A": task1},
        )

        pending = get_pending_tasks(doc)
        assert len(pending) == 0


class TestGetTaskById:
    """Tests for get_task_by_id function."""

    def test_get_task_by_id_existing(self) -> None:
        """Test getting an existing task by ID."""
        task = Task(task_id="01-A", name="A", wave=0, status=TaskStatus.IDLE)
        doc = TasksDocument(
            change_name="test",
            waves=[Wave(wave_number=0, tasks=[task])],
            all_tasks={"01-A": task},
        )

        result = get_task_by_id(doc, "01-A")
        assert result is not None
        assert result.task_id == "01-A"

    def test_get_task_by_id_nonexistent(self) -> None:
        """Test getting a non-existent task by ID."""
        doc = TasksDocument(change_name="test", waves=[], all_tasks={})
        result = get_task_by_id(doc, "99-NONE")
        assert result is None


class TestValidateDependencies:
    """Tests for validate_dependencies function."""

    def test_validate_dependencies_valid(self) -> None:
        """Test validating valid dependencies."""
        task1 = Task(task_id="01-A", name="A", wave=0, status=TaskStatus.IDLE)
        task2 = Task(task_id="02-B", name="B", wave=1, status=TaskStatus.IDLE, dependencies=["01-A"])

        doc = TasksDocument(
            change_name="test",
            waves=[Wave(wave_number=0, tasks=[task1]), Wave(wave_number=1, tasks=[task2])],
            all_tasks={"01-A": task1, "02-B": task2},
        )

        is_valid, errors = validate_dependencies(doc)
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_dependencies_nonexistent(self) -> None:
        """Test validating dependencies with non-existent task."""
        task = Task(task_id="01-A", name="A", wave=0, status=TaskStatus.IDLE, dependencies=["99-NONE"])

        doc = TasksDocument(
            change_name="test",
            waves=[Wave(wave_number=0, tasks=[task])],
            all_tasks={"01-A": task},
        )

        is_valid, errors = validate_dependencies(doc)
        assert is_valid is False
        assert len(errors) == 1
        assert "依赖了不存在的任务 99-NONE" in errors[0]

    def test_validate_dependencies_circular(self) -> None:
        """Test validating circular dependencies."""
        task1 = Task(task_id="01-A", name="A", wave=0, status=TaskStatus.IDLE, dependencies=["02-B"])
        task2 = Task(task_id="02-B", name="B", wave=0, status=TaskStatus.IDLE, dependencies=["01-A"])

        doc = TasksDocument(
            change_name="test",
            waves=[Wave(wave_number=0, tasks=[task1, task2])],
            all_tasks={"01-A": task1, "02-B": task2},
        )

        is_valid, errors = validate_dependencies(doc)
        assert is_valid is False
        assert any("循环依赖" in e for e in errors)

    def test_validate_dependencies_wrong_wave_order(self) -> None:
        """Test validating dependencies with wrong wave order."""
        task1 = Task(task_id="01-A", name="A", wave=1, status=TaskStatus.IDLE, dependencies=["02-B"])
        task2 = Task(task_id="02-B", name="B", wave=2, status=TaskStatus.IDLE)

        doc = TasksDocument(
            change_name="test",
            waves=[Wave(wave_number=1, tasks=[task1]), Wave(wave_number=2, tasks=[task2])],
            all_tasks={"01-A": task1, "02-B": task2},
        )

        is_valid, errors = validate_dependencies(doc)
        assert is_valid is False
        assert any("更晚的波次" in e for e in errors)


class TestUpdateTaskStatus:
    """Tests for update_task_status function."""

    def test_update_task_status_basic(self) -> None:
        """Test updating task status in overview table."""
        content = """# Tasks - test

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟦 空闲 | - |

## 任务详情

### 01-SETUP - Project Setup
**预估上下文**: ~30k tokens
**状态**: 🟦 空闲
"""

        updated = update_task_status(content, "01-SETUP", TaskStatus.IN_PROGRESS)

        assert "🟨" in updated
        assert "🟦" not in updated.split("01-SETUP")[1].split("\n")[0]

    def test_update_task_status_with_log(self) -> None:
        """Test updating task status with execution log."""
        content = """# Tasks - test

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟦 空闲 | - |

## 任务详情

### 01-SETUP - Project Setup
**预估上下文**: ~30k tokens

**Checklist**:
- [x] Done

"""

        log = {"completed_at": "2024-01-15T10:40:00Z", "subagent_id": "agent_123"}
        updated = update_task_status(content, "01-SETUP", TaskStatus.COMPLETED, log=log)

        assert "🟩" in updated
        assert "执行日志" in updated
        assert "2024-01-15T10:40:00Z" in updated
        assert "agent_123" in updated

    def test_update_task_status_not_found(self) -> None:
        """Test updating status for non-existent task."""
        content = """# Tasks - test

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟦 空闲 | - |
"""

        with pytest.raises(ValueError, match="概览表中未找到任务"):
            update_task_status(content, "99-NONE", TaskStatus.COMPLETED)


class TestUpdateChecklistItem:
    """Tests for update_checklist_item function."""

    def test_update_checklist_item_check(self) -> None:
        """Test checking a checklist item."""
        content = """# Tasks - test

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟦 空闲 | - |

## 任务详情

### 01-SETUP - Project Setup
**Checklist**:
- [ ] First item
- [ ] Second item
- [ ] Third item
"""

        updated = update_checklist_item(content, "01-SETUP", 1, checked=True)

        lines = updated.split("\n")
        checklist_lines = [l for l in lines if "[ ]" in l or "[x]" in l]

        assert "[ ] First item" in updated
        assert "[x] Second item" in updated
        assert "[ ] Third item" in updated

    def test_update_checklist_item_uncheck(self) -> None:
        """Test unchecking a checklist item."""
        content = """# Tasks - test

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟦 空闲 | - |

## 任务详情

### 01-SETUP - Project Setup
**Checklist**:
- [x] First item
- [x] Second item
"""

        updated = update_checklist_item(content, "01-SETUP", 0, checked=False)

        assert "[ ] First item" in updated
        assert "[x] Second item" in updated

    def test_update_checklist_item_task_not_found(self) -> None:
        """Test updating checklist for non-existent task."""
        content = """# Tasks - test

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟦 空闲 | - |
"""

        with pytest.raises(ValueError, match="在内容中未找到任务"):
            update_checklist_item(content, "99-NONE", 0, checked=True)

    def test_update_checklist_item_no_checklist(self) -> None:
        """Test updating checklist when task has no checklist."""
        content = """# Tasks - test

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟦 空闲 | - |

## 任务详情

### 01-SETUP - Project Setup
**预估上下文**: ~30k tokens
"""

        with pytest.raises(ValueError, match="未找到任务.*的检查清单"):
            update_checklist_item(content, "01-SETUP", 0, checked=True)

    def test_update_checklist_item_index_out_of_range(self) -> None:
        """Test updating checklist with invalid index."""
        content = """# Tasks - test

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟦 空闲 | - |

## 任务详情

### 01-SETUP - Project Setup
**Checklist**:
- [ ] First item
"""

        with pytest.raises(ValueError, match="索引.*超出范围"):
            update_checklist_item(content, "01-SETUP", 5, checked=True)
