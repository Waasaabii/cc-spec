"""Tests for clarify command."""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from helpers import assert_contains_any, read_yaml, write_yaml
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
            "detail": {
                "status": "completed",
                "completed_at": "2024-01-15T10:10:00Z",
            },
            "review": {
                "status": "completed",
                "completed_at": "2024-01-15T10:15:00Z",
            },
            "plan": {
                "status": "completed",
                "completed_at": "2024-01-15T10:20:00Z",
            },
            "apply": {
                "status": "in_progress",
                "started_at": "2024-01-15T10:25:00Z",
            },
            "accept": {
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
    write_yaml(status_file, status_data)

    # Create tasks.yaml (optional, for history display)
    tasks_yaml = change_dir / "tasks.yaml"
    tasks_yaml.write_text(
        """version: "1.6"
change: test-change
tasks:
  01-SETUP:
    wave: 0
    name: Setup
    tokens: 30k
    status: completed
    deps: []
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
    assert_contains_any(result.stdout.lower(), ["详情", "task details", "task"])


@patch("cc_spec.ui.prompts.readchar.readkey")
def test_clarify_rework_updates_status(mock_readkey, mock_cc_spec_project: Path) -> None:
    """Test that clarify with confirmation updates task status to pending."""
    # Simulate user confirming the operation (press 'y')
    mock_readkey.return_value = "y"
    result = runner.invoke(app, ["clarify", "02-MODEL"])

    assert result.exit_code == 0
    # Support Chinese and English output
    assert_contains_any(result.stdout.lower(), ["返工", "rework", "重做"])

    # Verify status.yaml was updated
    status_file = mock_cc_spec_project / ".cc-spec" / "changes" / "test-change" / "status.yaml"
    with open(status_file, encoding="utf-8") as f:
        status_data = read_yaml(status_file)

    # Find the task and check its status
    task = next((t for t in status_data["tasks"] if t["id"] == "02-MODEL"), None)
    assert task is not None
    assert task["status"] == TaskStatus.PENDING.value


def test_clarify_with_invalid_task_id(mock_cc_spec_project: Path) -> None:
    """Test that clarify with invalid task ID shows error."""
    result = runner.invoke(app, ["clarify", "99-INVALID"])

    assert result.exit_code == 1
    # Support Chinese error: "错误： 未找到任务"
    assert_contains_any(result.stdout.lower(), ["未找到", "not found", "error"])


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
    assert_contains_any(result.stdout.lower(), ["未找到", "no active change", "not found"])


def test_clarify_not_in_cc_spec_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that clarify shows error when not in cc-spec project."""
    # Mock find_project_root to return None (simulates not being in a project)
    with patch("cc_spec.commands.clarify.find_project_root", return_value=None):
        result = runner.invoke(app, ["clarify"])

        assert result.exit_code == 1
        assert_contains_any(result.stdout.lower(), ["cc-spec", "init"])


@patch("cc_spec.ui.prompts.readchar.readkey")
def test_clarify_pending_task_shows_note(mock_readkey, mock_cc_spec_project: Path) -> None:
    """Test that clarifying a pending task shows a note."""
    # Simulate user cancelling the operation (press 'n')
    mock_readkey.return_value = "n"
    result = runner.invoke(app, ["clarify", "03-API"])

    assert result.exit_code == 0
    assert "pending" in result.stdout.lower()


def test_clarify_detect_with_proposal(mock_cc_spec_project: Path) -> None:
    """Test that --detect option detects ambiguities in proposal.md."""
    # Create proposal.md with ambiguous content
    proposal_path = (
        mock_cc_spec_project / ".cc-spec" / "changes" / "test-change" / "proposal.md"
    )
    proposal_path.write_text(
        """# Test Change Proposal

## 背景与目标

这个功能可能需要支持多种格式。

## 技术决策

接口参数需要灵活定义。

## 用户故事

用户可以某些方式使用这个功能。
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["clarify", "--detect"])

    assert result.exit_code == 0
    # Should show ambiguity detection results
    assert_contains_any(result.stdout.lower(), ["歧义", "ambiguity"])


def test_clarify_detect_no_ambiguity(mock_cc_spec_project: Path) -> None:
    """Test that --detect shows success message when no ambiguities found."""
    # Create proposal.md with clear content (no ambiguous keywords)
    proposal_path = (
        mock_cc_spec_project / ".cc-spec" / "changes" / "test-change" / "proposal.md"
    )
    proposal_path.write_text(
        """# Test Change Proposal

## 背景与目标

实现用户登录功能。

## 技术决策

使用 JWT 进行身份验证。
已定义的 API 端点为 /auth/login。

## 成功标准

用户能够成功登录并获取令牌。
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["clarify", "--detect"])

    assert result.exit_code == 0
    # Should show success message (no ambiguities)
    assert_contains_any(result.stdout.lower(), ["检测", "未检测到", "proposal"])


def test_clarify_detect_missing_proposal(mock_cc_spec_project: Path) -> None:
    """Test that --detect shows error when proposal.md is missing."""
    # Don't create proposal.md
    result = runner.invoke(app, ["clarify", "--detect"])

    assert result.exit_code == 1
    assert_contains_any(result.stdout.lower(), ["proposal.md", "缺少"])


def test_clarify_detect_short_option(mock_cc_spec_project: Path) -> None:
    """Test that -d short option works for detect."""
    # Create proposal.md
    proposal_path = (
        mock_cc_spec_project / ".cc-spec" / "changes" / "test-change" / "proposal.md"
    )
    proposal_path.write_text(
        """# Test Change Proposal

## 背景

这个功能的实现方式比较灵活。
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["clarify", "-d"])

    assert result.exit_code == 0
    # Should run ambiguity detection
    assert_contains_any(result.stdout.lower(), ["检测", "歧义", "proposal"])
