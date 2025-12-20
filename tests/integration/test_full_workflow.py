"""Integration tests for cc-spec full workflow.

Tests the complete workflow from init to archive, ensuring all commands
work together correctly.
"""

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from cc_spec import app
from cc_spec.core.state import (
    ChangeState,
    Stage,
    StageInfo,
    TaskStatus,
    load_state,
    update_state,
)

runner = CliRunner()


class TestFullWorkflow:
    """Integration tests for complete workflow."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        self.original_cwd = os.getcwd()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_command(self) -> None:
        """Test init command creates project structure."""
        os.chdir(str(self.project_root))

        # 使用 --agent 参数跳过交互式选择，避免测试卡住
        result = runner.invoke(app, ["init", "--agent", "claude"])

        assert result.exit_code == 0
        assert (self.project_root / ".cc-spec").exists()
        assert (self.project_root / ".cc-spec" / "config.yaml").exists()
        assert (self.project_root / ".cc-spec" / "templates").exists()

    def test_specify_command(self) -> None:
        """Test specify command creates change directory."""
        os.chdir(str(self.project_root))

        # Initialize first
        runner.invoke(app, ["init", "--agent", "claude"])

        # Create change
        result = runner.invoke(app, ["specify", "add-feature"])

        assert result.exit_code == 0
        change_dir = self.project_root / ".cc-spec" / "changes" / "add-feature"
        assert change_dir.exists()
        assert (change_dir / "proposal.md").exists()
        assert (change_dir / "status.yaml").exists()

    def test_plan_command(self) -> None:
        """Test plan command generates tasks.yaml."""
        os.chdir(str(self.project_root))

        # Initialize and specify
        runner.invoke(app, ["init", "--agent", "claude"])
        runner.invoke(app, ["specify", "add-feature"])

        # Generate plan
        result = runner.invoke(app, ["plan", "add-feature"])

        assert result.exit_code == 0
        change_dir = self.project_root / ".cc-spec" / "changes" / "add-feature"
        assert (change_dir / "tasks.yaml").exists()

    def test_workflow_init_to_plan(self) -> None:
        """Test workflow from init to plan stage."""
        os.chdir(str(self.project_root))

        # Step 1: Init
        result = runner.invoke(app, ["init", "--agent", "claude"])
        assert result.exit_code == 0

        # Step 2: Specify
        result = runner.invoke(app, ["specify", "test-change"])
        assert result.exit_code == 0

        # Step 3: Plan
        result = runner.invoke(app, ["plan", "test-change"])
        assert result.exit_code == 0

        # Verify state progression
        status_path = (
            self.project_root
            / ".cc-spec"
            / "changes"
            / "test-change"
            / "status.yaml"
        )
        state = load_state(status_path)
        assert state.current_stage == Stage.PLAN

    def test_workflow_with_checklist(self) -> None:
        """Test workflow including checklist validation."""
        os.chdir(str(self.project_root))

        # Initialize
        runner.invoke(app, ["init", "--agent", "claude"])
        runner.invoke(app, ["specify", "test-feature"])
        runner.invoke(app, ["plan", "test-feature"])

        # 完全覆盖 tasks.yaml，确保只有一个通过的任务
        change_dir = self.project_root / ".cc-spec" / "changes" / "test-feature"
        tasks_path = change_dir / "tasks.yaml"

        # 写入只包含一个完成的任务的 tasks.yaml
        tasks_content = """version: "1.6"
change: test-feature
tasks:
  01-TEST:
    wave: 0
    name: Test Task
    tokens: 30k
    status: completed
    deps: []
    checklist:
      - item: Test item 1
        status: passed
      - item: Test item 2
        status: passed
"""
        tasks_path.write_text(tasks_content, encoding="utf-8")

        # Update state to apply completed
        status_path = change_dir / "status.yaml"
        state = load_state(status_path)
        state.current_stage = Stage.APPLY
        state.stages[Stage.APPLY] = StageInfo(
            status=TaskStatus.COMPLETED,
            started_at=datetime.now().isoformat(),
            completed_at=datetime.now().isoformat(),
        )
        update_state(status_path, state)

        # Run checklist
        result = runner.invoke(app, ["checklist", "test-feature"])

        assert result.exit_code == 0
        # 检查中文 "通过" 或英文 "PASSED"
        assert "通过" in result.stdout or "PASSED" in result.stdout

        # Verify state updated
        state = load_state(status_path)
        assert state.stages[Stage.CHECKLIST].status == TaskStatus.COMPLETED

    def test_clarify_command_shows_tasks(self) -> None:
        """Test clarify command shows task list."""
        os.chdir(str(self.project_root))

        # Initialize and create change
        runner.invoke(app, ["init", "--agent", "claude"])
        runner.invoke(app, ["specify", "test-change"])
        runner.invoke(app, ["plan", "test-change"])

        # Run clarify without task ID
        result = runner.invoke(app, ["clarify"])

        # Should show tasks or appropriate message
        assert result.exit_code == 0 or "no tasks" in result.stdout.lower()

    def test_quick_delta_command(self) -> None:
        """Test quick-delta creates and archives change."""
        os.chdir(str(self.project_root))

        # Initialize
        runner.invoke(app, ["init", "--agent", "claude"])

        # Quick delta
        result = runner.invoke(app, ["quick-delta", "Fix typo in README"])

        assert result.exit_code == 0
        # Should create archive
        archive_dir = self.project_root / ".cc-spec" / "changes" / "archive"
        assert archive_dir.exists() or "archived" in result.stdout.lower()

    def test_apply_dry_run(self) -> None:
        """Test apply command in dry-run mode."""
        os.chdir(str(self.project_root))

        # Initialize and plan
        runner.invoke(app, ["init", "--agent", "claude"])
        runner.invoke(app, ["specify", "test-apply"])
        runner.invoke(app, ["plan", "test-apply"])

        # Run apply in dry-run mode
        result = runner.invoke(app, ["apply", "test-apply", "--dry-run"])

        assert result.exit_code == 0
        # 检查中文 "演练模式" 或英文 "Dry run"
        assert "演练模式" in result.stdout or "Dry run" in result.stdout


class TestCommandRegistration:
    """Tests for command registration and help."""

    def test_all_commands_registered(self) -> None:
        """Test all commands are registered."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "init" in result.stdout
        assert "specify" in result.stdout
        assert "clarify" in result.stdout
        assert "plan" in result.stdout
        assert "apply" in result.stdout
        assert "checklist" in result.stdout
        assert "archive" in result.stdout
        assert "quick-delta" in result.stdout

    def test_version_option(self) -> None:
        """Test version option works."""
        result = runner.invoke(app, ["--version"])

        assert result.exit_code == 0
        assert "cc-spec" in result.stdout
        # 版本号可能是 0.1.0 或其他格式
        assert "0.1" in result.stdout or "version" in result.stdout.lower()

    def test_init_help(self) -> None:
        """Test init command help."""
        result = runner.invoke(app, ["init", "--help"])

        assert result.exit_code == 0
        # 检查中文 "初始化" 或英文 "Initialize"
        assert "初始化" in result.stdout or "Initialize" in result.stdout

    def test_specify_help(self) -> None:
        """Test specify command help."""
        result = runner.invoke(app, ["specify", "--help"])

        assert result.exit_code == 0
        # 检查中文 "变更" 或英文 "change"
        assert "变更" in result.stdout or "change" in result.stdout.lower()

    def test_apply_help(self) -> None:
        """Test apply command help."""
        result = runner.invoke(app, ["apply", "--help"])

        assert result.exit_code == 0
        assert "--max-concurrent" in result.stdout
        assert "--resume" in result.stdout
        assert "--dry-run" in result.stdout


class TestErrorHandling:
    """Tests for error handling across commands."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        self.original_cwd = os.getcwd()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_specify_without_init(self) -> None:
        """Test specify command behavior without local init.

        Note: This test may pass if user has ~/.cc-spec configured,
        as specify will use that. The key is it shouldn't crash.
        """
        # Mock find_project_root to return None (simulates not being in a project)
        with patch("cc_spec.commands.specify.find_project_root", return_value=None):
            result = runner.invoke(app, ["specify", "new-unique-change-xyz789"])

            # Should fail with "Not a cc-spec project" or 中文 "不是 cc-spec 项目"
            assert result.exit_code == 1
            assert (
                "Not in a cc-spec project" in result.stdout
                or "不是 cc-spec 项目" in result.stdout
                or "cc-spec" in result.stdout
            )

    def test_plan_without_specify(self) -> None:
        """Test plan command fails without specify."""
        os.chdir(str(self.project_root))

        runner.invoke(app, ["init", "--agent", "claude"])
        result = runner.invoke(app, ["plan", "nonexistent"])

        assert result.exit_code == 1
        # 检查中文 "未找到" 或英文 "not found"
        assert "not found" in result.stdout.lower() or "未找到" in result.stdout

    def test_checklist_without_tasks(self) -> None:
        """Test checklist fails without tasks.yaml."""
        os.chdir(str(self.project_root))

        runner.invoke(app, ["init", "--agent", "claude"])
        runner.invoke(app, ["specify", "test-change"])

        result = runner.invoke(app, ["checklist", "test-change"])

        assert result.exit_code == 1
        assert "tasks.yaml" in result.stdout.lower() or "tasks" in result.stdout.lower()

    def test_archive_without_checklist(self) -> None:
        """Test archive fails without checklist completion."""
        os.chdir(str(self.project_root))

        runner.invoke(app, ["init", "--agent", "claude"])
        runner.invoke(app, ["specify", "test-change"])
        runner.invoke(app, ["plan", "test-change"])

        result = runner.invoke(app, ["archive", "test-change"])

        assert result.exit_code == 1
        assert "checklist" in result.stdout.lower()

    def test_duplicate_specify(self) -> None:
        """Test specify fails for duplicate change name."""
        os.chdir(str(self.project_root))

        runner.invoke(app, ["init", "--agent", "claude"])
        runner.invoke(app, ["specify", "test-change"])

        result = runner.invoke(app, ["specify", "test-change"])

        assert result.exit_code == 1
        assert "exists" in result.stdout.lower()


class TestStateTransitions:
    """Tests for state transition validation."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        self.original_cwd = os.getcwd()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_state_progresses_through_stages(self) -> None:
        """Test state progresses correctly through stages."""
        os.chdir(str(self.project_root))

        # Init
        runner.invoke(app, ["init", "--agent", "claude"])

        # Specify
        runner.invoke(app, ["specify", "test-change"])
        status_path = (
            self.project_root
            / ".cc-spec"
            / "changes"
            / "test-change"
            / "status.yaml"
        )
        state = load_state(status_path)
        assert state.current_stage == Stage.SPECIFY

        # Plan
        runner.invoke(app, ["plan", "test-change"])
        state = load_state(status_path)
        assert state.current_stage == Stage.PLAN

    def test_checklist_updates_state(self) -> None:
        """Test checklist command updates state correctly."""
        os.chdir(str(self.project_root))

        runner.invoke(app, ["init", "--agent", "claude"])
        runner.invoke(app, ["specify", "test-change"])
        runner.invoke(app, ["plan", "test-change"])

        # Prepare completed tasks with proper task format
        change_dir = self.project_root / ".cc-spec" / "changes" / "test-change"
        tasks_path = change_dir / "tasks.yaml"

        # Write a complete tasks.yaml with checklist
        content = """version: "1.6"
change: test-change
tasks:
  01-TEST:
    wave: 0
    name: Test Task
    tokens: 30k
    status: completed
    deps: []
    checklist:
      - item: Task completed
        status: passed
      - item: All items done
        status: passed
"""
        tasks_path.write_text(content, encoding="utf-8")

        # Update to apply completed
        status_path = change_dir / "status.yaml"
        state = load_state(status_path)
        state.current_stage = Stage.APPLY
        state.stages[Stage.APPLY] = StageInfo(
            status=TaskStatus.COMPLETED,
            started_at=datetime.now().isoformat(),
            completed_at=datetime.now().isoformat(),
        )
        update_state(status_path, state)

        # Run checklist
        result = runner.invoke(app, ["checklist", "test-change"])

        # Verify checklist ran (either passed or failed based on items)
        assert result.exit_code == 0

        # Verify state was updated
        state = load_state(status_path)
        assert state.stages[Stage.CHECKLIST].status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
        )
