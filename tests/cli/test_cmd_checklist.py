"""Unit tests for checklist command."""

import os
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from helpers import assert_contains_any
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


class TestChecklistCommand:
    """Tests for checklist command."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.project_root = tmp_path
        self.cc_spec_dir = self.project_root / ".cc-spec"
        self.changes_dir = self.cc_spec_dir / "changes"
        self.change_name = "add-feature"
        self.change_dir = self.changes_dir / self.change_name
        self.cc_spec_dir.mkdir(parents=True, exist_ok=True)
        self.change_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.chdir(self.project_root)

    def _create_tasks_yaml(self, content: str = None) -> Path:
        """Helper to create tasks.yaml with checklist items."""
        if content is None:
            content = """version: "1.6"
change: add-feature
tasks:
  01-SETUP:
    wave: 0
    name: Project Setup
    tokens: 30k
    status: completed
    deps: []
    docs:
      - docs/plan/spec.md
    code:
      - src/config/
    checklist:
      - item: 创建配置文件
        status: passed
      - item: 添加环境变量
        status: passed
      - item: 初始化数据库
        status: passed
  02-MODEL:
    wave: 1
    name: Data Model
    tokens: 50k
    status: completed
    deps: [01-SETUP]
    docs:
      - docs/plan/spec.md
    code:
      - src/models/
    checklist:
      - item: 创建数据模型
        status: passed
      - item: 添加验证逻辑
        status: passed
      - item: 编写单元测试
        status: passed
"""
        tasks_path = self.change_dir / "tasks.yaml"
        tasks_path.write_text(content, encoding="utf-8")
        return tasks_path

    def _create_status(self, current_stage: Stage = Stage.APPLY) -> Path:
        """Helper to create status.yaml."""
        state = ChangeState(
            change_name=self.change_name,
            created_at=datetime.now().isoformat(),
            current_stage=current_stage,
            stages={
                Stage.SPECIFY: StageInfo(
                    status=TaskStatus.COMPLETED,
                    started_at=datetime.now().isoformat(),
                    completed_at=datetime.now().isoformat(),
                ),
                Stage.CLARIFY: StageInfo(status=TaskStatus.COMPLETED),
                Stage.PLAN: StageInfo(status=TaskStatus.COMPLETED),
                Stage.APPLY: StageInfo(
                    status=TaskStatus.COMPLETED,
                    started_at=datetime.now().isoformat(),
                    completed_at=datetime.now().isoformat(),
                ),
                Stage.CHECKLIST: StageInfo(status=TaskStatus.PENDING),
                Stage.ARCHIVE: StageInfo(status=TaskStatus.PENDING),
            },
        )

        status_path = self.change_dir / "status.yaml"
        update_state(status_path, state)
        return status_path

    def test_checklist_without_project_root(self) -> None:
        """Test checklist command fails when not in a project."""
        # Mock find_project_root to return None (simulates not being in a project)
        with patch("cc_spec.commands.checklist.find_project_root", return_value=None):
            result = runner.invoke(app, ["checklist", "test-change"])
            assert result.exit_code == 1
            assert "cc-spec" in result.stdout  # Error message contains project name

    def test_checklist_without_change(self) -> None:
        """Test checklist command fails when change doesn't exist."""
        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["checklist", "nonexistent-change"])
        assert result.exit_code == 1
        assert_contains_any(result.stdout, ["未找到", "not found"])

    def test_checklist_without_tasks_yaml(self) -> None:
        """Test checklist command fails when tasks.yaml doesn't exist."""
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["checklist", self.change_name, "--write-report"])
        assert result.exit_code == 1
        assert_contains_any(result.stdout, ["tasks.yaml", "tasks"])

    def test_checklist_with_all_passed(self) -> None:
        """Test checklist command with all items passed."""
        self._create_tasks_yaml()
        status_path = self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["checklist", self.change_name, "--write-report"])

        if result.exit_code != 0:
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)

        assert result.exit_code == 0, f"Command failed with: {result.stdout}"

        # Check output - support Chinese and English
        assert_contains_any(result.stdout, ["通过", "PASSED"])

        # Check state updated to checklist completed
        state = load_state(status_path)
        assert state.current_stage == Stage.CHECKLIST
        assert state.stages[Stage.CHECKLIST].status == TaskStatus.COMPLETED

    def test_checklist_with_failed_items(self) -> None:
        """Test checklist command with failed items."""
        # Create tasks.yaml with some unchecked items
        tasks_content = """version: "1.6"
change: add-feature
tasks:
  01-SETUP:
    wave: 0
    name: Project Setup
    tokens: 30k
    status: in_progress
    deps: []
    checklist:
      - item: 创建配置文件
        status: passed
      - item: 添加环境变量
        status: failed
      - item: 初始化数据库
        status: failed
"""
        self._create_tasks_yaml(tasks_content)
        status_path = self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["checklist", self.change_name, "--write-report"])

        assert result.exit_code == 0, f"Command failed with: {result.stdout}"

        # Check output - support Chinese and English
        assert_contains_any(result.stdout, ["未通过", "FAILED"])

        # Check failure report generated
        report_path = self.change_dir / "checklist-result.md"
        assert report_path.exists()

        report_content = report_path.read_text(encoding="utf-8")
        assert "验证失败" in report_content or "Validation Failed" in report_content
        assert "添加环境变量" in report_content
        assert "初始化数据库" in report_content

        # Check state reverted to apply
        state = load_state(status_path)
        assert state.current_stage == Stage.APPLY
        assert state.stages[Stage.CHECKLIST].status == TaskStatus.FAILED

    def test_checklist_with_custom_threshold(self) -> None:
        """Test checklist command with custom threshold."""
        # Create tasks with 50% completion
        tasks_content = """version: "1.6"
change: add-feature
tasks:
  01-SETUP:
    wave: 0
    name: Project Setup
    tokens: 30k
    status: completed
    deps: []
    checklist:
      - item: Item 1
        status: passed
      - item: Item 2
        status: failed
"""
        self._create_tasks_yaml(tasks_content)
        self._create_status()

        os.chdir(str(self.project_root))

        # Test with threshold 40% (should pass)
        result = runner.invoke(app, ["checklist", self.change_name, "--threshold", "40"])
        assert result.exit_code == 0
        assert_contains_any(result.stdout, ["通过", "PASSED"])

        # Test with threshold 60% (should fail)
        result = runner.invoke(app, ["checklist", self.change_name, "--threshold", "60"])
        assert result.exit_code == 0
        assert_contains_any(result.stdout, ["未通过", "FAILED"])

    def test_checklist_with_no_checklist_items(self) -> None:
        """Test checklist command when no checklist items found."""
        # Create tasks.yaml without checklist items
        tasks_content = """version: "1.6"
change: add-feature
tasks:
  01-SETUP:
    wave: 0
    name: Project Setup
    tokens: 30k
    status: completed
    deps: []
"""
        self._create_tasks_yaml(tasks_content)
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["checklist", self.change_name])

        assert result.exit_code == 1
        # Support various Chinese messages about no checklist items
        assert_contains_any(result.stdout, ["未找到", "No checklist items found"])

    def test_checklist_with_skipped_items(self) -> None:
        """Test checklist command with skipped items."""
        tasks_content = """version: "1.6"
change: add-feature
tasks:
  01-SETUP:
    wave: 0
    name: Project Setup
    tokens: 30k
    status: completed
    deps: []
    checklist:
      - item: 创建配置文件
        status: passed
      - item: 可选功能 (跳过)
        status: skipped
      - item: 初始化数据库
        status: passed
"""
        self._create_tasks_yaml(tasks_content)
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["checklist", self.change_name])

        assert result.exit_code == 0
        # Skipped items should not affect score
        assert_contains_any(result.stdout, ["100.0%", "PASSED"])

    def test_checklist_without_explicit_change_name(self) -> None:
        """Test checklist command uses current active change when name not provided."""
        self._create_tasks_yaml()
        self._create_status()

        # Run without specifying change name
        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["checklist"])

        assert result.exit_code == 0, f"Command failed with: {result.stdout}"
        assert_contains_any(result.stdout, ["通过", "PASSED"])

    def test_checklist_displays_task_results(self) -> None:
        """Test checklist command displays results for each task."""
        self._create_tasks_yaml()
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["checklist", self.change_name])

        assert result.exit_code == 0
        # Should show task IDs
        assert "01-SETUP" in result.stdout
        assert "02-MODEL" in result.stdout
        # Should show task scores
        assert_contains_any(result.stdout, ["Score:", "得分"])

    def test_checklist_shows_next_steps(self) -> None:
        """Test checklist command displays next steps."""
        self._create_tasks_yaml()
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["checklist", self.change_name])

        assert result.exit_code == 0
        assert_contains_any(result.stdout, ["Next steps:", "下一步"])


class TestChecklistIntegration:
    """Integration tests for checklist command workflow."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.project_root = tmp_path
        self.cc_spec_dir = self.project_root / ".cc-spec"
        self.cc_spec_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.chdir(self.project_root)

    def test_full_workflow_with_checklist_pass(self) -> None:
        """Test complete workflow from specify to checklist (passing)."""
        os.chdir(str(self.project_root))

        # Step 1: Create change with specify
        result = runner.invoke(app, ["specify", "add-oauth"])
        assert result.exit_code == 0

        # Step 2: Generate plan
        result = runner.invoke(app, ["plan", "add-oauth"])
        if result.exit_code != 0:
            print("PLAN STDOUT:", result.stdout)
            print("PLAN STDERR:", result.stderr)
        assert result.exit_code == 0

        # Step 3: Manually add completed checklist to tasks.yaml
        changes_dir = self.cc_spec_dir / "changes"
        change_dir = changes_dir / "add-oauth"
        tasks_path = change_dir / "tasks.yaml"

        # Create new tasks.yaml with completed checklist
        tasks_content = """version: "1.6"
change: add-oauth
tasks:
  99-TEST:
    wave: 0
    name: Integration Test Task
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

        # Step 4: Run checklist with threshold 0 to ensure pass
        result = runner.invoke(app, ["checklist", "add-oauth", "--threshold", "0"])

        if result.exit_code != 0:
            print("CHECKLIST STDOUT:", result.stdout)
            print("CHECKLIST STDERR:", result.stderr)

        assert result.exit_code == 0
        assert_contains_any(result.stdout, ["通过", "PASSED"])

        # Step 5: Verify state progression
        state = load_state(status_path)
        assert state.current_stage == Stage.CHECKLIST
        assert state.stages[Stage.CHECKLIST].status == TaskStatus.COMPLETED

    def test_full_workflow_with_checklist_fail(self) -> None:
        """Test complete workflow from specify to checklist (failing)."""
        os.chdir(str(self.project_root))

        # Step 1: Create change with specify
        result = runner.invoke(app, ["specify", "add-feature"])
        assert result.exit_code == 0

        # Step 2: Generate plan
        result = runner.invoke(app, ["plan", "add-feature"])
        assert result.exit_code == 0

        # Step 3: Add incomplete checklist to tasks.yaml
        changes_dir = self.cc_spec_dir / "changes"
        change_dir = changes_dir / "add-feature"
        tasks_path = change_dir / "tasks.yaml"

        # Create new tasks.yaml with incomplete checklist
        tasks_content = """version: "1.6"
change: add-feature
tasks:
  99-TEST:
    wave: 0
    name: Integration Test Task
    tokens: 30k
    status: completed
    deps: []
    checklist:
      - item: Test item 1
        status: passed
      - item: Test item 2
        status: failed
      - item: Test item 3
        status: failed
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

        # Step 4: Run checklist
        result = runner.invoke(app, ["checklist", "add-feature", "--write-report"])
        assert result.exit_code == 0
        assert_contains_any(result.stdout, ["未通过", "FAILED"])

        # Step 5: Verify failure report generated
        report_path = change_dir / "checklist-result.md"
        assert report_path.exists()

        # Step 6: Verify state reverted to apply
        state = load_state(status_path)
        assert state.current_stage == Stage.APPLY
        assert state.stages[Stage.CHECKLIST].status == TaskStatus.FAILED
