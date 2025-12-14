"""Unit tests for checklist command."""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
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


class TestChecklistCommand:
    """Tests for checklist command."""

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

    def _create_tasks_md(self, content: str = None) -> Path:
        """Helper to create tasks.md with checklist items."""
        if content is None:
            content = """# Tasks - add-feature

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟩 完成 | - |
| 1 | 02-MODEL | 50k | 🟩 完成 | 01-SETUP |

## 任务详情

### 01-SETUP - Project Setup
**预估上下文**: ~30k tokens
**状态**: 🟩 完成
**依赖**: 无

**必读文档**:
- docs/plan/spec.md

**核心代码入口**:
- src/config/

**Checklist**:
- [x] 创建配置文件
- [x] 添加环境变量
- [x] 初始化数据库

---

### 02-MODEL - Data Model
**预估上下文**: ~50k tokens
**状态**: 🟩 完成
**依赖**: 01-SETUP

**必读文档**:
- docs/plan/spec.md

**核心代码入口**:
- src/models/

**Checklist**:
- [x] 创建数据模型
- [x] 添加验证逻辑
- [x] 编写单元测试
"""
        tasks_path = self.change_dir / "tasks.md"
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
        assert "未找到" in result.stdout or "not found" in result.stdout

    def test_checklist_without_tasks_md(self) -> None:
        """Test checklist command fails when tasks.md doesn't exist."""
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["checklist", self.change_name])
        assert result.exit_code == 1
        assert "tasks.md" in result.stdout  # Contains tasks.md in error message

    def test_checklist_with_all_passed(self) -> None:
        """Test checklist command with all items passed."""
        self._create_tasks_md()
        status_path = self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["checklist", self.change_name])

        if result.exit_code != 0:
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)

        assert result.exit_code == 0, f"Command failed with: {result.stdout}"

        # Check output - support Chinese and English
        assert "通过" in result.stdout or "PASSED" in result.stdout

        # Check state updated to checklist completed
        state = load_state(status_path)
        assert state.current_stage == Stage.CHECKLIST
        assert state.stages[Stage.CHECKLIST].status == TaskStatus.COMPLETED

    def test_checklist_with_failed_items(self) -> None:
        """Test checklist command with failed items."""
        # Create tasks.md with some unchecked items
        tasks_content = """# Tasks - add-feature

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟨 进行中 | - |

## 任务详情

### 01-SETUP - Project Setup
**预估上下文**: ~30k tokens
**状态**: 🟨 进行中
**依赖**: 无

**Checklist**:
- [x] 创建配置文件
- [ ] 添加环境变量
- [ ] 初始化数据库
"""
        self._create_tasks_md(tasks_content)
        status_path = self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["checklist", self.change_name])

        assert result.exit_code == 0, f"Command failed with: {result.stdout}"

        # Check output - support Chinese and English
        assert "未通过" in result.stdout or "FAILED" in result.stdout

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
        tasks_content = """# Tasks - add-feature

## 任务详情

### 01-SETUP - Project Setup

**Checklist**:
- [x] Item 1
- [ ] Item 2
"""
        self._create_tasks_md(tasks_content)
        self._create_status()

        os.chdir(str(self.project_root))

        # Test with threshold 40% (should pass)
        result = runner.invoke(app, ["checklist", self.change_name, "--threshold", "40"])
        assert result.exit_code == 0
        assert "通过" in result.stdout or "PASSED" in result.stdout

        # Test with threshold 60% (should fail)
        result = runner.invoke(app, ["checklist", self.change_name, "--threshold", "60"])
        assert result.exit_code == 0
        assert "未通过" in result.stdout or "FAILED" in result.stdout

    def test_checklist_with_no_checklist_items(self) -> None:
        """Test checklist command when no checklist items found."""
        # Create tasks.md without checklist items
        tasks_content = """# Tasks - add-feature

## 任务详情

### 01-SETUP - Project Setup

No checklist here.
"""
        self._create_tasks_md(tasks_content)
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["checklist", self.change_name])

        assert result.exit_code == 1
        # Support various Chinese messages about no checklist items
        assert "未找到" in result.stdout and "检查" in result.stdout or "No checklist items found" in result.stdout

    def test_checklist_with_skipped_items(self) -> None:
        """Test checklist command with skipped items."""
        tasks_content = """# Tasks - add-feature

## 任务详情

### 01-SETUP - Project Setup

**Checklist**:
- [x] 创建配置文件
- [-] 可选功能 (跳过)
- [x] 初始化数据库
"""
        self._create_tasks_md(tasks_content)
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["checklist", self.change_name])

        assert result.exit_code == 0
        # Skipped items should not affect score
        assert "100.0%" in result.stdout or "PASSED" in result.stdout

    def test_checklist_without_explicit_change_name(self) -> None:
        """Test checklist command uses current active change when name not provided."""
        self._create_tasks_md()
        self._create_status()

        # Run without specifying change name
        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["checklist"])

        assert result.exit_code == 0, f"Command failed with: {result.stdout}"
        assert "通过" in result.stdout or "PASSED" in result.stdout

    def test_checklist_displays_task_results(self) -> None:
        """Test checklist command displays results for each task."""
        self._create_tasks_md()
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["checklist", self.change_name])

        assert result.exit_code == 0
        # Should show task IDs
        assert "01-SETUP" in result.stdout
        assert "02-MODEL" in result.stdout
        # Should show task scores
        assert "Score:" in result.stdout or "得分" in result.stdout

    def test_checklist_shows_next_steps(self) -> None:
        """Test checklist command displays next steps."""
        self._create_tasks_md()
        self._create_status()

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["checklist", self.change_name])

        assert result.exit_code == 0
        assert "Next steps:" in result.stdout or "下一步" in result.stdout


class TestChecklistIntegration:
    """Integration tests for checklist command workflow."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        self.cc_spec_dir = self.project_root / ".cc-spec"

        # Create .cc-spec directory
        self.cc_spec_dir.mkdir(parents=True, exist_ok=True)

        # Save original working directory
        self.original_cwd = os.getcwd()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        import shutil

        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

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

        # Step 3: Manually add completed checklist to tasks.md
        changes_dir = self.cc_spec_dir / "changes"
        change_dir = changes_dir / "add-oauth"
        tasks_path = change_dir / "tasks.md"

        # Read existing tasks.md and add completed checklist
        tasks_content = tasks_path.read_text(encoding="utf-8")
        tasks_content += """

### 99-TEST - Integration Test Task

**Checklist**:
- [x] Test item 1
- [x] Test item 2
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
        assert "通过" in result.stdout or "PASSED" in result.stdout

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

        # Step 3: Add incomplete checklist to tasks.md
        changes_dir = self.cc_spec_dir / "changes"
        change_dir = changes_dir / "add-feature"
        tasks_path = change_dir / "tasks.md"

        tasks_content = tasks_path.read_text(encoding="utf-8")
        tasks_content += """

### 99-TEST - Integration Test Task

**Checklist**:
- [x] Test item 1
- [ ] Test item 2
- [ ] Test item 3
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
        result = runner.invoke(app, ["checklist", "add-feature"])
        assert result.exit_code == 0
        assert "未通过" in result.stdout or "FAILED" in result.stdout

        # Step 5: Verify failure report generated
        report_path = change_dir / "checklist-result.md"
        assert report_path.exists()

        # Step 6: Verify state reverted to apply
        state = load_state(status_path)
        assert state.current_stage == Stage.APPLY
        assert state.stages[Stage.CHECKLIST].status == TaskStatus.FAILED
