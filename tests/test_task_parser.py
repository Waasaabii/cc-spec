"""Unit tests for task_parser module (YAML only)."""

import pytest

from cc_spec.core.scoring import CheckItem, CheckStatus
from cc_spec.subagent.task_parser import (
    ExecutionLog,
    Task,
    TasksDocument,
    TaskStatus,
    Wave,
    generate_tasks_yaml,
    get_pending_tasks,
    get_task_by_id,
    get_tasks_by_wave,
    parse_tasks_yaml,
    update_checklist_item_yaml,
    update_task_status_yaml,
    validate_dependencies,
)


class TestTaskStatus:
    """Tests for TaskStatus constants."""

    def test_status_values(self) -> None:
        """Test TaskStatus constant values."""
        assert TaskStatus.IDLE == "idle"
        assert TaskStatus.IN_PROGRESS == "in_progress"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.TIMEOUT == "timeout"


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


# ============================================================================
# YAML 格式测试
# ============================================================================


class TestParseTasksYaml:
    """Tests for parse_tasks_yaml function."""

    def test_parse_basic_yaml(self) -> None:
        """Test parsing basic tasks.yaml file."""
        content = """
version: "1.0"
change: test-feature
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
      - src/models/README.md
    checklist:
      - 创建数据模型
      - 添加验证逻辑
"""

        doc = parse_tasks_yaml(content)

        assert doc.change_name == "test-feature"
        assert len(doc.waves) == 2
        assert len(doc.all_tasks) == 2

        # Verify task 01-SETUP
        task1 = doc.all_tasks["01-SETUP"]
        assert task1.task_id == "01-SETUP"
        assert task1.name == "Project Setup"
        assert task1.wave == 0
        assert task1.status == TaskStatus.IDLE
        assert task1.estimated_tokens == 30000
        assert task1.dependencies == []
        assert len(task1.required_docs) == 1
        assert len(task1.code_entry_points) == 1
        assert len(task1.checklist_items) == 2

        # Verify task 02-MODEL
        task2 = doc.all_tasks["02-MODEL"]
        assert task2.wave == 1
        assert task2.dependencies == ["01-SETUP"]
        assert task2.estimated_tokens == 50000

    def test_parse_yaml_with_status(self) -> None:
        """Test parsing tasks.yaml with different task statuses."""
        content = """
version: "1.0"
change: status-test
tasks:
  01-A:
    wave: 0
    name: Task A
    status: completed
  02-B:
    wave: 0
    name: Task B
    status: in_progress
  03-C:
    wave: 0
    name: Task C
    status: failed
"""

        doc = parse_tasks_yaml(content)

        assert doc.all_tasks["01-A"].status == TaskStatus.COMPLETED
        assert doc.all_tasks["02-B"].status == TaskStatus.IN_PROGRESS
        assert doc.all_tasks["03-C"].status == TaskStatus.FAILED

    def test_parse_yaml_with_execution_log(self) -> None:
        """Test parsing tasks.yaml with execution log."""
        content = """
version: "1.0"
change: log-test
tasks:
  01-DONE:
    wave: 0
    name: Completed Task
    status: completed
    log:
      completed_at: "2024-01-15T10:40:00Z"
      subagent_id: agent_123
      notes: "All tests passed"
"""

        doc = parse_tasks_yaml(content)

        task = doc.all_tasks["01-DONE"]
        assert task.execution_log is not None
        assert task.execution_log.completed_at == "2024-01-15T10:40:00Z"
        assert task.execution_log.subagent_id == "agent_123"
        assert task.execution_log.notes == "All tests passed"

    def test_parse_yaml_invalid_format(self) -> None:
        """Test parsing invalid YAML content."""
        with pytest.raises(ValueError, match="tasks.yaml"):
            parse_tasks_yaml("not: valid: yaml: :")

    def test_parse_yaml_missing_change(self) -> None:
        """Test parsing YAML without change field."""
        with pytest.raises(ValueError, match="'change'"):
            parse_tasks_yaml("version: '1.0'\ntasks: {}")

    def test_parse_yaml_with_profile(self) -> None:
        """Test parsing tasks.yaml with profile field."""
        content = """
version: "1.0"
change: profile-test
tasks:
  01-TASK:
    wave: 0
    name: Task with Profile
    profile: heavy-compute
"""

        doc = parse_tasks_yaml(content)
        assert doc.all_tasks["01-TASK"].profile == "heavy-compute"


class TestGenerateTasksYaml:
    """Tests for generate_tasks_yaml function."""

    def test_generate_basic_yaml(self) -> None:
        """Test generating tasks.yaml from TasksDocument."""
        # Create a TasksDocument
        task1 = Task(
            task_id="01-SETUP",
            name="Setup",
            wave=0,
            status=TaskStatus.IDLE,
            estimated_tokens=30000,
            dependencies=[],
            required_docs=["docs/spec.md"],
            code_entry_points=["src/config/"],
            checklist_items=[
                CheckItem(description="Step 1", status=CheckStatus.FAILED, score=0),
                CheckItem(description="Step 2", status=CheckStatus.FAILED, score=0),
            ],
        )
        task2 = Task(
            task_id="02-MODEL",
            name="Model",
            wave=1,
            status=TaskStatus.IDLE,
            estimated_tokens=50000,
            dependencies=["01-SETUP"],
        )

        doc = TasksDocument(
            change_name="test-feature",
            waves=[
                Wave(wave_number=0, tasks=[task1]),
                Wave(wave_number=1, tasks=[task2]),
            ],
            all_tasks={"01-SETUP": task1, "02-MODEL": task2},
        )

        yaml_content = generate_tasks_yaml(doc)

        # Verify YAML contains expected content
        assert "version: '1.0'" in yaml_content or 'version: "1.0"' in yaml_content
        assert "change: test-feature" in yaml_content
        assert "01-SETUP:" in yaml_content
        assert "02-MODEL:" in yaml_content
        assert "30k" in yaml_content
        assert "50k" in yaml_content

    def test_roundtrip_yaml(self) -> None:
        """Test that YAML can be generated and parsed back correctly."""
        # Create original document
        task = Task(
            task_id="01-TEST",
            name="Test Task",
            wave=0,
            status=TaskStatus.COMPLETED,
            estimated_tokens=25000,
            dependencies=[],
            required_docs=["docs/test.md"],
            checklist_items=[
                CheckItem(description="Check 1", status=CheckStatus.PASSED, score=10),
            ],
        )

        original = TasksDocument(
            change_name="roundtrip-test",
            waves=[Wave(wave_number=0, tasks=[task])],
            all_tasks={"01-TEST": task},
        )

        # Generate and parse back
        yaml_content = generate_tasks_yaml(original)
        parsed = parse_tasks_yaml(yaml_content)

        # Verify
        assert parsed.change_name == original.change_name
        assert len(parsed.all_tasks) == len(original.all_tasks)
        assert parsed.all_tasks["01-TEST"].name == task.name
        assert parsed.all_tasks["01-TEST"].estimated_tokens == task.estimated_tokens


class TestUpdateTaskStatusYaml:
    """Tests for update_task_status_yaml function."""

    def test_update_task_status_basic(self) -> None:
        """Test updating task status in YAML."""
        content = """version: "1.0"
change: test
tasks:
  01-SETUP:
    wave: 0
    name: Setup
    status: idle
"""

        updated = update_task_status_yaml(content, "01-SETUP", TaskStatus.IN_PROGRESS)

        assert "status: in_progress" in updated

    def test_update_task_status_with_log(self) -> None:
        """Test updating task status with execution log."""
        content = """version: "1.0"
change: test
tasks:
  01-SETUP:
    wave: 0
    name: Setup
    status: idle
"""

        log = {"completed_at": "2024-01-15T10:40:00Z", "subagent_id": "agent_123"}
        updated = update_task_status_yaml(content, "01-SETUP", TaskStatus.COMPLETED, log=log)

        assert "status: completed" in updated
        assert "completed_at" in updated
        assert "agent_123" in updated

    def test_update_task_status_not_found(self) -> None:
        """Test updating status for non-existent task."""
        content = """version: "1.0"
change: test
tasks:
  01-SETUP:
    wave: 0
    name: Setup
"""

        with pytest.raises(ValueError, match="未找到任务"):
            update_task_status_yaml(content, "99-NONE", TaskStatus.COMPLETED)


class TestUpdateChecklistItemYaml:
    """Tests for update_checklist_item_yaml function."""

    def test_update_checklist_item_check(self) -> None:
        """Test checking a checklist item."""
        content = """version: "1.0"
change: test
tasks:
  01-SETUP:
    wave: 0
    name: Setup
    checklist:
      - First item
      - Second item
      - Third item
"""

        updated = update_checklist_item_yaml(content, "01-SETUP", 1, checked=True)

        assert "done: true" in updated

    def test_update_checklist_item_task_not_found(self) -> None:
        """Test updating checklist for non-existent task."""
        content = """version: "1.0"
change: test
tasks:
  01-SETUP:
    wave: 0
    name: Setup
"""

        with pytest.raises(ValueError, match="未找到任务"):
            update_checklist_item_yaml(content, "99-NONE", 0, checked=True)

    def test_update_checklist_item_index_out_of_range(self) -> None:
        """Test updating checklist with invalid index."""
        content = """version: "1.0"
change: test
tasks:
  01-SETUP:
    wave: 0
    name: Setup
    checklist:
      - First item
"""

        with pytest.raises(ValueError, match="索引.*超出范围"):
            update_checklist_item_yaml(content, "01-SETUP", 5, checked=True)
