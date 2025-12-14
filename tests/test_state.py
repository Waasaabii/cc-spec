"""Tests for state management module."""

from datetime import datetime
from pathlib import Path

import pytest
import yaml

from cc_spec.core.state import (
    ChangeState,
    Stage,
    StageInfo,
    TaskInfo,
    TaskStatus,
    get_current_change,
    load_state,
    update_state,
    validate_stage_transition,
)


@pytest.fixture
def temp_state_file(tmp_path: Path) -> Path:
    """Create a temporary state file."""
    state_file = tmp_path / "status.yaml"
    state_data = {
        "change_name": "add-oauth",
        "created_at": "2024-01-15T10:00:00Z",
        "current_stage": "apply",
        "stages": {
            "specify": {
                "status": "completed",
                "completed_at": "2024-01-15T10:05:00Z",
            },
            "clarify": {
                "status": "completed",
                "completed_at": "2024-01-15T10:15:00Z",
            },
            "plan": {
                "status": "completed",
                "completed_at": "2024-01-15T10:30:00Z",
            },
            "apply": {
                "status": "in_progress",
                "started_at": "2024-01-15T10:35:00Z",
                "waves_completed": 1,
                "waves_total": 3,
            },
            "checklist": {
                "status": "pending",
            },
            "archive": {
                "status": "pending",
            },
        },
        "tasks": [
            {"id": "01-SETUP", "status": "completed", "wave": 0},
            {"id": "02-MODEL", "status": "in_progress", "wave": 1},
            {"id": "03-API", "status": "pending", "wave": 1},
        ],
    }

    with open(state_file, "w", encoding="utf-8") as f:
        yaml.dump(state_data, f)

    return state_file


@pytest.fixture
def temp_cc_spec_root(tmp_path: Path) -> Path:
    """Create a temporary .cc-spec directory structure."""
    cc_spec_root = tmp_path / ".cc-spec"
    changes_dir = cc_spec_root / "changes"
    changes_dir.mkdir(parents=True)

    # Create multiple changes with different timestamps
    change1_dir = changes_dir / "add-oauth"
    change1_dir.mkdir()
    state1 = {
        "change_name": "add-oauth",
        "created_at": "2024-01-15T10:00:00Z",
        "current_stage": "apply",
        "stages": {},
        "tasks": [],
    }
    with open(change1_dir / "status.yaml", "w", encoding="utf-8") as f:
        yaml.dump(state1, f)

    change2_dir = changes_dir / "add-logging"
    change2_dir.mkdir()
    state2 = {
        "change_name": "add-logging",
        "created_at": "2024-01-16T10:00:00Z",
        "current_stage": "plan",
        "stages": {},
        "tasks": [],
    }
    with open(change2_dir / "status.yaml", "w", encoding="utf-8") as f:
        yaml.dump(state2, f)

    # Create archived change
    archive_dir = changes_dir / "archive"
    archive_dir.mkdir()
    archived_change = archive_dir / "2024-01-14-old-change"
    archived_change.mkdir()
    state3 = {
        "change_name": "old-change",
        "created_at": "2024-01-14T10:00:00Z",
        "current_stage": "archive",
        "stages": {},
        "tasks": [],
    }
    with open(archived_change / "status.yaml", "w", encoding="utf-8") as f:
        yaml.dump(state3, f)

    return cc_spec_root


class TestStageEnum:
    """Tests for Stage enum."""

    def test_stage_values(self) -> None:
        """Test that all stages have correct values."""
        assert Stage.SPECIFY.value == "specify"
        assert Stage.CLARIFY.value == "clarify"
        assert Stage.PLAN.value == "plan"
        assert Stage.APPLY.value == "apply"
        assert Stage.CHECKLIST.value == "checklist"
        assert Stage.ARCHIVE.value == "archive"


class TestTaskStatusEnum:
    """Tests for TaskStatus enum."""

    def test_task_status_values(self) -> None:
        """Test that all task statuses have correct values."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.IN_PROGRESS.value == "in_progress"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.TIMEOUT.value == "timeout"


class TestChangeState:
    """Tests for ChangeState dataclass."""

    def test_change_state_initialization(self) -> None:
        """Test ChangeState initialization."""
        state = ChangeState(
            change_name="test-change",
            created_at="2024-01-15T10:00:00Z",
            current_stage=Stage.SPECIFY,
        )

        assert state.change_name == "test-change"
        assert state.created_at == "2024-01-15T10:00:00Z"
        assert state.current_stage == Stage.SPECIFY
        assert len(state.stages) == 6
        assert len(state.tasks) == 0

    def test_change_state_with_stages(self) -> None:
        """Test ChangeState with custom stages."""
        stages = {
            Stage.SPECIFY: StageInfo(
                status=TaskStatus.COMPLETED, completed_at="2024-01-15T10:00:00Z"
            )
        }

        state = ChangeState(
            change_name="test-change",
            created_at="2024-01-15T10:00:00Z",
            current_stage=Stage.SPECIFY,
            stages=stages,
        )

        assert len(state.stages) == 1
        assert state.stages[Stage.SPECIFY].status == TaskStatus.COMPLETED


class TestLoadState:
    """Tests for load_state function."""

    def test_load_state_success(self, temp_state_file: Path) -> None:
        """Test loading state from valid file."""
        state = load_state(temp_state_file)

        assert state.change_name == "add-oauth"
        assert state.created_at == "2024-01-15T10:00:00Z"
        assert state.current_stage == Stage.APPLY

        # Check stages
        assert state.stages[Stage.SPECIFY].status == TaskStatus.COMPLETED
        assert state.stages[Stage.APPLY].status == TaskStatus.IN_PROGRESS
        assert state.stages[Stage.APPLY].waves_completed == 1
        assert state.stages[Stage.APPLY].waves_total == 3

        # Check tasks
        assert len(state.tasks) == 3
        assert state.tasks[0].id == "01-SETUP"
        assert state.tasks[0].status == TaskStatus.COMPLETED
        assert state.tasks[1].id == "02-MODEL"
        assert state.tasks[1].status == TaskStatus.IN_PROGRESS

    def test_load_state_file_not_found(self, tmp_path: Path) -> None:
        """Test loading state from non-existent file."""
        with pytest.raises(FileNotFoundError):
            load_state(tmp_path / "nonexistent.yaml")

    def test_load_state_empty_file(self, tmp_path: Path) -> None:
        """Test loading state from empty file."""
        empty_file = tmp_path / "empty.yaml"
        empty_file.touch()

        with pytest.raises(ValueError, match="(State file is empty|状态文件为空|空文件)"):
            load_state(empty_file)

    def test_load_state_minimal(self, tmp_path: Path) -> None:
        """Test loading state with minimal data."""
        minimal_file = tmp_path / "minimal.yaml"
        with open(minimal_file, "w", encoding="utf-8") as f:
            yaml.dump({"change_name": "test"}, f)

        state = load_state(minimal_file)
        assert state.change_name == "test"
        assert state.current_stage == Stage.SPECIFY


class TestUpdateState:
    """Tests for update_state function."""

    def test_update_state_success(self, tmp_path: Path) -> None:
        """Test updating state to file."""
        state = ChangeState(
            change_name="test-change",
            created_at="2024-01-15T10:00:00Z",
            current_stage=Stage.APPLY,
            stages={
                Stage.SPECIFY: StageInfo(
                    status=TaskStatus.COMPLETED, completed_at="2024-01-15T10:05:00Z"
                ),
                Stage.APPLY: StageInfo(
                    status=TaskStatus.IN_PROGRESS,
                    started_at="2024-01-15T10:10:00Z",
                    waves_completed=1,
                    waves_total=3,
                ),
            },
            tasks=[
                TaskInfo(id="01-SETUP", status=TaskStatus.COMPLETED, wave=0),
                TaskInfo(id="02-MODEL", status=TaskStatus.IN_PROGRESS, wave=1),
            ],
        )

        state_file = tmp_path / "status.yaml"
        update_state(state_file, state)

        assert state_file.exists()

        # Verify content
        loaded_state = load_state(state_file)
        assert loaded_state.change_name == "test-change"
        assert loaded_state.current_stage == Stage.APPLY
        assert loaded_state.stages[Stage.SPECIFY].status == TaskStatus.COMPLETED
        assert loaded_state.stages[Stage.APPLY].waves_completed == 1
        assert len(loaded_state.tasks) == 2

    def test_update_state_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Test that update_state creates parent directories."""
        state_file = tmp_path / "nested" / "dir" / "status.yaml"
        state = ChangeState(
            change_name="test",
            created_at="2024-01-15T10:00:00Z",
            current_stage=Stage.SPECIFY,
        )

        update_state(state_file, state)
        assert state_file.exists()


class TestGetCurrentChange:
    """Tests for get_current_change function."""

    def test_get_current_change_success(self, temp_cc_spec_root: Path) -> None:
        """Test getting current change."""
        state = get_current_change(temp_cc_spec_root)

        assert state is not None
        assert state.change_name == "add-logging"  # Most recent
        assert state.created_at == "2024-01-16T10:00:00Z"

    def test_get_current_change_no_changes_dir(self, tmp_path: Path) -> None:
        """Test getting current change when changes dir doesn't exist."""
        state = get_current_change(tmp_path)
        assert state is None

    def test_get_current_change_empty_changes_dir(self, tmp_path: Path) -> None:
        """Test getting current change from empty changes dir."""
        changes_dir = tmp_path / "changes"
        changes_dir.mkdir(parents=True)

        state = get_current_change(tmp_path)
        assert state is None

    def test_get_current_change_ignores_archive(self, temp_cc_spec_root: Path) -> None:
        """Test that archived changes are ignored."""
        state = get_current_change(temp_cc_spec_root)

        assert state is not None
        assert state.change_name != "old-change"  # Archived change


class TestValidateStageTransition:
    """Tests for validate_stage_transition function."""

    def test_validate_transition_next_stage(self) -> None:
        """Test transition to next stage."""
        assert validate_stage_transition(Stage.SPECIFY, Stage.CLARIFY) is True
        assert validate_stage_transition(Stage.CLARIFY, Stage.PLAN) is True
        assert validate_stage_transition(Stage.PLAN, Stage.APPLY) is True
        assert validate_stage_transition(Stage.APPLY, Stage.CHECKLIST) is True
        assert validate_stage_transition(Stage.CHECKLIST, Stage.ARCHIVE) is True

    def test_validate_transition_same_stage(self) -> None:
        """Test staying in the same stage."""
        assert validate_stage_transition(Stage.SPECIFY, Stage.SPECIFY) is True
        assert validate_stage_transition(Stage.APPLY, Stage.APPLY) is True

    def test_validate_transition_backward(self) -> None:
        """Test backward transitions (rework)."""
        assert validate_stage_transition(Stage.APPLY, Stage.PLAN) is True
        assert validate_stage_transition(Stage.CHECKLIST, Stage.APPLY) is True
        assert validate_stage_transition(Stage.ARCHIVE, Stage.SPECIFY) is True

    def test_validate_transition_skip_forward(self) -> None:
        """Test that skipping stages forward is not allowed."""
        assert validate_stage_transition(Stage.SPECIFY, Stage.PLAN) is False
        assert validate_stage_transition(Stage.SPECIFY, Stage.APPLY) is False
        assert validate_stage_transition(Stage.CLARIFY, Stage.CHECKLIST) is False
