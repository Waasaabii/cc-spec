"""Tests for clarify command."""

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from typer.testing import CliRunner

from cc_spec import app
from cc_spec.core.state import TaskStatus

runner = CliRunner()


@pytest.fixture
def mock_cc_spec_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a mock cc-spec project structure."""
    # Create .cc-spec directory
    cc_spec_dir = tmp_path / ".cc-spec"
    cc_spec_dir.mkdir()

    # Create changes directory
    changes_dir = cc_spec_dir / "changes"
    changes_dir.mkdir()

    # Create a test change
    change_dir = changes_dir / "test-change"
    change_dir.mkdir()

    # Create status.yaml with tasks
    status_data = {
        "change_name": "test-change",
        "created_at": "2024-01-15T10:00:00Z",
        "current_stage": "apply",
        "stages": {
            "specify": {
                "status": "completed",
                "completed_at": "2024-01-15T10:05:00Z",
            },
            "clarify": {
                "status": "completed",
                "completed_at": "2024-01-15T10:10:00Z",
            },
            "plan": {
                "status": "completed",
                "completed_at": "2024-01-15T10:20:00Z",
            },
            "apply": {
                "status": "in_progress",
                "started_at": "2024-01-15T10:25:00Z",
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

    status_file = change_dir / "status.yaml"
    with open(status_file, "w", encoding="utf-8") as f:
        yaml.dump(status_data, f)

    # Create tasks.md (optional, for history display)
    tasks_md = change_dir / "tasks.md"
    tasks_md.write_text(
        """# Tasks - test-change

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟩 完成 | - |
| 1 | 02-MODEL | 50k | 🟨 进行中 | 01-SETUP |
| 1 | 03-API | 45k | 🟦 空闲 | 01-SETUP |

## 任务详情

### Task: 01-SETUP
**预估上下文**: ~30k tokens
**状态**: 🟩 完成
**依赖**: 无

**执行日志**:
- 完成时间: 2024-01-15T10:40:00Z
""",
        encoding="utf-8",
    )

    # Change to the temp directory
    monkeypatch.chdir(tmp_path)

    return tmp_path


def test_clarify_no_args_shows_task_list(mock_cc_spec_project: Path) -> None:
    """Test that clarify without arguments shows task list."""
    result = runner.invoke(app, ["clarify"])

    assert result.exit_code == 0
    assert "test-change" in result.stdout
    assert "01-SETUP" in result.stdout
    assert "02-MODEL" in result.stdout
    assert "03-API" in result.stdout


@patch("cc_spec.ui.prompts.readchar.readkey")
def test_clarify_with_task_id_prompts_rework(mock_readkey, mock_cc_spec_project: Path) -> None:
    """Test that clarify with task ID prompts for rework confirmation."""
    # Simulate user cancelling the operation (press 'n')
    mock_readkey.return_value = "n"
    result = runner.invoke(app, ["clarify", "02-MODEL"])

    assert result.exit_code == 0
    assert "02-MODEL" in result.stdout
    assert "详情" in result.stdout or "Task Details" in result.stdout or "task" in result.stdout.lower()


@patch("cc_spec.ui.prompts.readchar.readkey")
def test_clarify_rework_updates_status(mock_readkey, mock_cc_spec_project: Path) -> None:
    """Test that clarify with confirmation updates task status to pending."""
    # Simulate user confirming the operation (press 'y')
    mock_readkey.return_value = "y"
    result = runner.invoke(app, ["clarify", "02-MODEL"])

    assert result.exit_code == 0
    # Support Chinese and English output
    assert "返工" in result.stdout or "rework" in result.stdout.lower() or "重做" in result.stdout

    # Verify status.yaml was updated
    status_file = mock_cc_spec_project / ".cc-spec" / "changes" / "test-change" / "status.yaml"
    with open(status_file, encoding="utf-8") as f:
        status_data = yaml.safe_load(f)

    # Find the task and check its status
    task = next((t for t in status_data["tasks"] if t["id"] == "02-MODEL"), None)
    assert task is not None
    assert task["status"] == TaskStatus.PENDING.value


def test_clarify_with_invalid_task_id(mock_cc_spec_project: Path) -> None:
    """Test that clarify with invalid task ID shows error."""
    result = runner.invoke(app, ["clarify", "99-INVALID"])

    assert result.exit_code == 1
    # Support Chinese error: "错误： 未找到任务"
    assert "未找到" in result.stdout or "not found" in result.stdout.lower() or "error" in result.stdout.lower()


def test_clarify_with_explicit_change(mock_cc_spec_project: Path) -> None:
    """Test that clarify works with explicit change name."""
    result = runner.invoke(app, ["clarify", "--change", "test-change"])

    assert result.exit_code == 0
    assert "test-change" in result.stdout
    assert "01-SETUP" in result.stdout


def test_clarify_no_active_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that clarify shows error when no active change exists."""
    # Create empty .cc-spec directory
    cc_spec_dir = tmp_path / ".cc-spec"
    cc_spec_dir.mkdir()
    (cc_spec_dir / "changes").mkdir()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["clarify"])

    assert result.exit_code == 1
    # Support Chinese message: "未找到激活的变更"
    assert "未找到" in result.stdout or "no active change" in result.stdout.lower() or "not found" in result.stdout.lower()


def test_clarify_not_in_cc_spec_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that clarify shows error when not in cc-spec project."""
    # Mock find_project_root to return None (simulates not being in a project)
    with patch("cc_spec.commands.clarify.find_project_root", return_value=None):
        result = runner.invoke(app, ["clarify"])

        assert result.exit_code == 1
        assert "cc-spec" in result.stdout.lower() or "init" in result.stdout.lower()


@patch("cc_spec.ui.prompts.readchar.readkey")
def test_clarify_pending_task_shows_note(mock_readkey, mock_cc_spec_project: Path) -> None:
    """Test that clarifying a pending task shows a note."""
    # Simulate user cancelling the operation (press 'n')
    mock_readkey.return_value = "n"
    result = runner.invoke(app, ["clarify", "03-API"])

    assert result.exit_code == 0
    assert "pending" in result.stdout.lower()
