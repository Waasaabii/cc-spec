"""Unit tests for specify command."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from typer.testing import CliRunner

from cc_spec import app
from cc_spec.commands.specify import validate_change_name
from cc_spec.core.state import Stage, TaskStatus, load_state
from cc_spec.utils.files import get_changes_dir

runner = CliRunner()


class TestValidateChangeName:
    """Tests for change name validation."""

    def test_valid_names(self) -> None:
        """Test valid change names."""
        valid_names = [
            "add-feature",
            "fix-bug",
            "update-dependency",
            "a",
            "abc-123",
            "feature-x-y-z",
            "add123",
        ]
        for name in valid_names:
            is_valid, error = validate_change_name(name)
            assert is_valid, f"{name} should be valid, got error: {error}"
            assert error == ""

    def test_invalid_names(self) -> None:
        """Test invalid change names."""
        invalid_cases = [
            ("", "不能为空"),  # Change name cannot be empty
            ("Add-Feature", "小写字母开头"),  # must start with a lowercase letter
            ("123-feature", "小写字母开头"),
            ("-feature", "小写字母开头"),
            ("add_feature", "小写字母、数字和连字符"),  # contain only lowercase letters, numbers, and hyphens
            ("add feature", "小写字母、数字和连字符"),
            ("add.feature", "小写字母、数字和连字符"),
            ("ADD-FEATURE", "小写字母开头"),
            ("a" * 65, "64"),  # must be 64 characters or less
        ]
        for name, expected_msg_fragment in invalid_cases:
            is_valid, error = validate_change_name(name)
            assert not is_valid, f"{name} should be invalid"
            assert expected_msg_fragment in error, f"Expected '{expected_msg_fragment}' in error: {error}"


class TestSpecifyCommand:
    """Tests for specify command."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        self.cc_spec_dir = self.project_root / ".cc-spec"
        self.changes_dir = self.cc_spec_dir / "changes"

        # Create .cc-spec directory to mark as project root
        self.cc_spec_dir.mkdir(parents=True, exist_ok=True)

        # Save original working directory
        self.original_cwd = os.getcwd()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        import shutil
        # Restore original working directory
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_specify_without_project_root(self) -> None:
        """Test specify command fails when not in a project."""
        # Mock find_project_root to return None (simulates not being in a project)
        with patch("cc_spec.commands.specify.find_project_root", return_value=None):
            result = runner.invoke(app, ["specify", "test-change"])
            assert result.exit_code == 1
            assert "cc-spec" in result.stdout  # Error message contains project name

    def test_specify_creates_change_directory(self) -> None:
        """Test specify command creates change directory."""
        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["specify", "add-feature"])

        if result.exit_code != 0:
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)

        assert result.exit_code == 0, f"Command failed with: {result.stdout}"

        change_dir = self.changes_dir / "add-feature"
        assert change_dir.exists()
        assert change_dir.is_dir()

    def test_specify_creates_proposal_file(self) -> None:
        """Test specify command creates proposal.md."""
        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["specify", "add-feature"])

        assert result.exit_code == 0, f"Command failed with: {result.stdout}"

        proposal_path = self.changes_dir / "add-feature" / "proposal.md"
        assert proposal_path.exists()

        content = proposal_path.read_text(encoding="utf-8")
        # Check for Chinese section headers (new template format)
        assert "背景与目标" in content or "## Why" in content
        assert "用户故事" in content or "## What Changes" in content
        assert "技术决策" in content or "## Impact" in content

    def test_specify_creates_status_yaml(self) -> None:
        """Test specify command creates status.yaml with correct initial state."""
        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["specify", "add-feature"])

        assert result.exit_code == 0, f"Command failed with: {result.stdout}"

        status_path = self.changes_dir / "add-feature" / "status.yaml"
        assert status_path.exists()

        # Load and validate state
        state = load_state(status_path)
        assert state.change_name == "add-feature"
        assert state.current_stage == Stage.SPECIFY
        assert state.stages[Stage.SPECIFY].status == TaskStatus.IN_PROGRESS
        assert state.stages[Stage.SPECIFY].started_at is not None

    def test_specify_rejects_duplicate_change(self) -> None:
        """Test specify command rejects duplicate change name."""
        os.chdir(str(self.project_root))

        # Create first change
        result1 = runner.invoke(app, ["specify", "add-feature"])
        assert result1.exit_code == 0

        # Try to create duplicate
        result2 = runner.invoke(app, ["specify", "add-feature"])
        assert result2.exit_code == 1
        assert "already exists" in result2.stdout

    def test_specify_rejects_invalid_name(self) -> None:
        """Test specify command rejects invalid change name."""
        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["specify", "Invalid-Name"])

        assert result.exit_code == 1
        assert "不合法" in result.stdout or "Invalid" in result.stdout

    def test_specify_shows_next_steps(self) -> None:
        """Test specify command displays next steps."""
        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["specify", "add-feature"])

        assert result.exit_code == 0
        # Check for Chinese or English output
        assert "add-feature" in result.stdout
        assert "clarify" in result.stdout
        assert "plan" in result.stdout

    def test_specify_with_template_option(self) -> None:
        """Test specify command with custom template."""
        os.chdir(str(self.project_root))
        result = runner.invoke(
            app,
            ["specify", "add-feature", "--template", "custom"]
        )

        # Should succeed even if custom template doesn't exist (falls back to default)
        assert result.exit_code == 0

        proposal_path = self.changes_dir / "add-feature" / "proposal.md"
        assert proposal_path.exists()


class TestSpecifyIntegration:
    """Integration tests for specify command workflow."""

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
        # Restore original working directory
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_multiple_changes_coexist(self) -> None:
        """Test creating multiple changes in the same project."""
        os.chdir(str(self.project_root))
        changes = ["add-feature-a", "fix-bug-b", "update-deps-c"]

        for change_name in changes:
            result = runner.invoke(app, ["specify", change_name])
            assert result.exit_code == 0, f"Failed to create {change_name}: {result.stdout}"

        # Verify all changes exist
        changes_dir = get_changes_dir(self.project_root)
        for change_name in changes:
            change_dir = changes_dir / change_name
            assert change_dir.exists()
            assert (change_dir / "proposal.md").exists()
            assert (change_dir / "status.yaml").exists()

    def test_specify_preserves_project_root_detection(self) -> None:
        """Test specify works from subdirectories."""
        # Create a subdirectory
        subdir = self.project_root / "src" / "components"
        subdir.mkdir(parents=True, exist_ok=True)

        # Run specify from subdirectory
        os.chdir(str(subdir))
        result = runner.invoke(app, ["specify", "add-component"])

        assert result.exit_code == 0, f"Command failed with: {result.stdout}"

        # Verify change created at project root
        change_dir = get_changes_dir(self.project_root) / "add-component"
        assert change_dir.exists()
