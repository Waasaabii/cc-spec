"""Unit tests for plan command."""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from typer.testing import CliRunner

from cc_spec import app
from cc_spec.core.state import Stage, StageInfo, TaskStatus, load_state, update_state

runner = CliRunner()


class TestPlanCommand:
    """Tests for plan command."""

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

    def _create_proposal(self, content: str = None) -> Path:
        """Helper to create proposal.md."""
        if content is None:
            content = """# Proposal: Add Feature

## Why

We need this feature to improve user experience.

## What Changes

- Add new API endpoint
- Update database schema
- Implement frontend components

## Impact

- Low risk
- No breaking changes
"""
        proposal_path = self.change_dir / "proposal.md"
        proposal_path.write_text(content, encoding="utf-8")
        return proposal_path

    def _create_status(self) -> Path:
        """Helper to create status.yaml."""
        from cc_spec.core.state import ChangeState, Stage, StageInfo, TaskStatus

        state = ChangeState(
            change_name=self.change_name,
            created_at=datetime.now().isoformat(),
            current_stage=Stage.SPECIFY,
            stages={
                Stage.SPECIFY: StageInfo(
                    status=TaskStatus.COMPLETED,
                    started_at=datetime.now().isoformat(),
                    completed_at=datetime.now().isoformat(),
                ),
                Stage.CLARIFY: StageInfo(status=TaskStatus.PENDING),
                Stage.PLAN: StageInfo(status=TaskStatus.PENDING),
                Stage.APPLY: StageInfo(status=TaskStatus.PENDING),
                Stage.CHECKLIST: StageInfo(status=TaskStatus.PENDING),
                Stage.ARCHIVE: StageInfo(status=TaskStatus.PENDING),
            },
        )

        status_path = self.change_dir / "status.yaml"
        update_state(status_path, state)
        return status_path

    def test_plan_without_project_root(self) -> None:
        """Test plan command fails when not in a project."""
        # Mock find_project_root to return None (simulates not being in a project)
        with patch("cc_spec.commands.plan.find_project_root", return_value=None):
            result = runner.invoke(app, ["plan", "test-change"])
            assert result.exit_code == 1
            assert "cc-spec" in result.stdout  # Error message contains project name

    def test_plan_without_change(self) -> None:
        """Test plan command fails when change doesn't exist."""
        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["plan", "nonexistent-change"])
        assert result.exit_code == 1
        assert "未找到" in result.stdout or "not found" in result.stdout

    def test_plan_without_proposal(self) -> None:
        """Test plan command fails when proposal.md doesn't exist."""
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["plan", self.change_name])
        assert result.exit_code == 1
        assert "proposal.md" in result.stdout  # Contains proposal.md in error message

    def test_plan_creates_tasks_md(self) -> None:
        """Test plan command creates tasks.md."""
        self._create_proposal()
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["plan", self.change_name])

        if result.exit_code != 0:
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)

        assert result.exit_code == 0, f"Command failed with: {result.stdout}"

        tasks_path = self.change_dir / "tasks.md"
        assert tasks_path.exists()

        content = tasks_path.read_text(encoding="utf-8")
        # Support Chinese header: "# 任务 - " instead of "# Tasks - "
        assert f"# Tasks - {self.change_name}" in content or f"# 任务 - {self.change_name}" in content
        assert "## 概览" in content
        assert "## 任务详情" in content

    def test_plan_creates_design_md(self) -> None:
        """Test plan command - design.md is no longer created in v1.2+."""
        self._create_proposal()
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["plan", self.change_name])

        assert result.exit_code == 0, f"Command failed with: {result.stdout}"

        # v1.2+: design.md is no longer generated, technical decisions are in proposal.md
        design_path = self.change_dir / "design.md"
        assert not design_path.exists(), "design.md should not be created in v1.2+"

    def test_plan_updates_state_to_plan(self) -> None:
        """Test plan command updates state to plan stage."""
        self._create_proposal()
        status_path = self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["plan", self.change_name])

        assert result.exit_code == 0, f"Command failed with: {result.stdout}"

        # Load and verify state
        state = load_state(status_path)
        assert state.current_stage == Stage.PLAN
        assert state.stages[Stage.PLAN].status == TaskStatus.COMPLETED
        assert state.stages[Stage.PLAN].started_at is not None
        assert state.stages[Stage.PLAN].completed_at is not None

    def test_plan_shows_task_overview(self) -> None:
        """Test plan command displays task overview."""
        self._create_proposal()
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["plan", self.change_name])

        assert result.exit_code == 0
        assert "Task Overview" in result.stdout or "任务" in result.stdout

    def test_plan_shows_next_steps(self) -> None:
        """Test plan command displays next steps."""
        self._create_proposal()
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["plan", self.change_name])

        assert result.exit_code == 0
        # Support Chinese and English output: "计划生成成功" or "Plan generated"
        assert "计划生成" in result.stdout or "Plan generated" in result.stdout
        assert "下一步" in result.stdout or "Next steps" in result.stdout
        assert "cc-spec apply" in result.stdout

    def test_plan_without_explicit_change_name(self) -> None:
        """Test plan command uses current active change when name not provided."""
        self._create_proposal()
        self._create_status()

        # Run without specifying change name
        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["plan"])

        assert result.exit_code == 0, f"Command failed with: {result.stdout}"

        tasks_path = self.change_dir / "tasks.md"
        assert tasks_path.exists()


class TestPlanValidation:
    """Tests for plan validation functions."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)

    def teardown_method(self) -> None:
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_validate_tasks_with_valid_dependencies(self) -> None:
        """Test dependency validation with valid dependencies."""
        from cc_spec.commands.plan import _validate_tasks_dependencies

        tasks_content = """# Tasks - test

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟦 空闲 | - |
| 1 | 02-MODEL | 50k | 🟦 空闲 | 01-SETUP |
| 1 | 03-API | 45k | 🟦 空闲 | 01-SETUP |
| 2 | 04-FE | 60k | 🟦 空闲 | 02-MODEL, 03-API |
"""
        tasks_path = self.project_root / "tasks.md"
        tasks_path.write_text(tasks_content, encoding="utf-8")

        result = _validate_tasks_dependencies(tasks_path)
        assert result["valid"] is True
        assert len(result["tasks"]) == 4

    def test_validate_tasks_with_invalid_dependencies(self) -> None:
        """Test dependency validation with invalid dependencies."""
        from cc_spec.commands.plan import _validate_tasks_dependencies

        tasks_content = """# Tasks - test

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟦 空闲 | - |
| 1 | 02-MODEL | 50k | 🟦 空闲 | 99-INVALID |
"""
        tasks_path = self.project_root / "tasks.md"
        tasks_path.write_text(tasks_content, encoding="utf-8")

        result = _validate_tasks_dependencies(tasks_path)
        assert result["valid"] is False
        # Support Chinese: "无效依赖" or "依赖无效"
        assert "无效" in result["message"] and "依赖" in result["message"] or "Invalid dependencies" in result["message"]

    def test_parse_tasks_summary(self) -> None:
        """Test parsing tasks.md for display."""
        from cc_spec.commands.plan import _parse_tasks_summary

        tasks_content = """# Tasks - test

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟦 空闲 | - |
| 1 | 02-MODEL | 50k | 🟨 进行中 | 01-SETUP |
| 2 | 03-API | 45k | 🟩 完成 | 02-MODEL |
"""
        tasks_path = self.project_root / "tasks.md"
        tasks_path.write_text(tasks_content, encoding="utf-8")

        tasks = _parse_tasks_summary(tasks_path)
        assert len(tasks) == 3
        assert tasks[0]["id"] == "01-SETUP"
        assert tasks[0]["status"] == "pending"
        assert tasks[1]["status"] == "in_progress"
        assert tasks[2]["status"] == "completed"


class TestPlanIntegration:
    """Integration tests for plan command workflow."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        self.cc_spec_dir = self.project_root / ".cc-spec"

        # Create .cc-spec directory
        self.cc_spec_dir.mkdir(parents=True, exist_ok=True)

    def teardown_method(self) -> None:
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_full_specify_to_plan_workflow(self) -> None:
        """Test complete workflow from specify to plan."""
        # Step 1: Create change with specify
        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["specify", "add-oauth"])
        assert result.exit_code == 0

        # Step 2: Verify proposal exists
        changes_dir = self.cc_spec_dir / "changes"
        change_dir = changes_dir / "add-oauth"
        proposal_path = change_dir / "proposal.md"
        assert proposal_path.exists()

        # Step 3: Run plan
        result = runner.invoke(app, ["plan", "add-oauth"])

        if result.exit_code != 0:
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)

        assert result.exit_code == 0

        # Step 4: Verify plan outputs - v1.2+ only creates tasks.md
        tasks_path = change_dir / "tasks.md"
        design_path = change_dir / "design.md"
        assert tasks_path.exists()
        # v1.2+: design.md is no longer generated
        assert not design_path.exists(), "design.md should not be created in v1.2+"

        # Step 5: Verify state progression
        status_path = change_dir / "status.yaml"
        state = load_state(status_path)
        assert state.current_stage == Stage.PLAN
        # specify stage completed after plan runs
        assert state.stages[Stage.PLAN].status == TaskStatus.COMPLETED
