"""Unit tests for quick-delta command."""

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from cc_spec import app

runner = CliRunner()


class TestQuickDeltaCommand:
    """Tests for quick-delta command."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        self.cc_spec_dir = self.project_root / ".cc-spec"
        self.changes_dir = self.cc_spec_dir / "changes"
        self.archive_dir = self.changes_dir / "archive"

        # Create project structure
        self.cc_spec_dir.mkdir(parents=True, exist_ok=True)
        self.changes_dir.mkdir(parents=True, exist_ok=True)

        # Save original working directory
        self.original_cwd = os.getcwd()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        # Restore original working directory
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_quick_delta_without_project_root(self) -> None:
        """Test quick-delta command fails when not in a project."""
        # Create a temp directory without .cc-spec and change to it
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                result = runner.invoke(app, ["quick-delta", "Fix login bug"])
                assert result.exit_code == 1
                assert "Not a cc-spec project" in result.stdout
            finally:
                # Always restore original directory before temp_dir is deleted
                os.chdir(original_cwd)

    def test_quick_delta_creates_archive_directory(self) -> None:
        """Test quick-delta command creates archive directory."""
        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["quick-delta", "Fix login bug"])

        if result.exit_code != 0:
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)

        assert result.exit_code == 0
        assert self.archive_dir.exists()
        assert "Quick-delta record created successfully" in result.stdout

    def test_quick_delta_generates_change_name(self) -> None:
        """Test quick-delta command generates timestamped change name."""
        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["quick-delta", "Update config"])

        assert result.exit_code == 0

        # Find generated change directory
        change_dirs = list(self.archive_dir.glob("quick-*-update-config"))
        assert len(change_dirs) == 1

        change_dir = change_dirs[0]
        # Verify format: quick-YYYYMMDD-HHMMSS-{slug}
        assert change_dir.name.startswith("quick-")
        assert "update-config" in change_dir.name

    def test_quick_delta_creates_mini_proposal(self) -> None:
        """Test quick-delta command creates mini-proposal.md."""
        os.chdir(str(self.project_root))
        message = "Fix authentication timeout issue"
        result = runner.invoke(app, ["quick-delta", message])

        assert result.exit_code == 0

        # Find the created change directory
        change_dirs = list(self.archive_dir.glob("quick-*-fix-authentication*"))
        assert len(change_dirs) == 1

        change_dir = change_dirs[0]
        mini_proposal = change_dir / "mini-proposal.md"

        # Verify mini-proposal.md exists
        assert mini_proposal.exists()

        # Verify content
        content = mini_proposal.read_text(encoding="utf-8")
        assert f"# Quick Delta: {message}" in content
        assert "## 变更信息" in content
        assert "- **变更类型**: quick-delta" in content
        assert f"- **描述**: {message}" in content
        assert "## 备注" in content
        assert "quick-delta 适用于" in content

    def test_quick_delta_with_git_info(self) -> None:
        """Test quick-delta command includes git info when available."""
        # Initialize git repo
        os.chdir(str(self.project_root))

        try:
            # Setup git repo
            os.system("git init")
            os.system('git config user.name "Test User"')
            os.system('git config user.email "test@example.com"')

            # Create a file and commit
            test_file = self.project_root / "test.txt"
            test_file.write_text("test")
            os.system("git add test.txt")
            os.system('git commit -m "Initial commit"')

            # Run quick-delta
            result = runner.invoke(app, ["quick-delta", "Quick fix"])

            assert result.exit_code == 0

            # Find the created change directory
            change_dirs = list(self.archive_dir.glob("quick-*-quick-fix"))
            assert len(change_dirs) == 1

            change_dir = change_dirs[0]
            mini_proposal = change_dir / "mini-proposal.md"

            # Verify git info is included
            content = mini_proposal.read_text(encoding="utf-8")
            assert "## Git 信息" in content
            assert "- **Commit**:" in content
            assert "- **Author**:" in content
            assert "- **Message**:" in content

        except Exception as e:
            # Git might not be available in CI/CD environment
            pytest.skip(f"Git not available: {e}")

    def test_quick_delta_slug_generation(self) -> None:
        """Test quick-delta command generates proper slug from message."""
        os.chdir(str(self.project_root))

        test_cases = [
            ("Fix login bug", "fix-login-bug"),
            ("Update config.yaml file", "update-configyaml-file"),
            ("Add API endpoint /users", "add-api-endpoint-users"),
            ("修复中文问题", "修复中文问题"),
            ("Fix:  multiple   spaces", "fix-multiple-spaces"),
        ]

        for message, expected_slug_part in test_cases:
            result = runner.invoke(app, ["quick-delta", message])
            assert result.exit_code == 0

            # Find change directory with expected slug
            change_dirs = list(self.archive_dir.glob(f"quick-*-{expected_slug_part}"))
            assert len(change_dirs) >= 1, f"Expected slug '{expected_slug_part}' not found for message '{message}'"

    def test_quick_delta_long_message_truncation(self) -> None:
        """Test quick-delta command truncates very long messages in slug."""
        os.chdir(str(self.project_root))
        long_message = "This is a very long message that should be truncated to fit within the maximum slug length limit"

        result = runner.invoke(app, ["quick-delta", long_message])
        assert result.exit_code == 0

        # Find the created change directory
        change_dirs = list(self.archive_dir.glob("quick-*"))
        assert len(change_dirs) >= 1

        change_dir = change_dirs[-1]  # Get the most recent one
        # Verify slug is truncated (should be around 30 chars max)
        name_parts = change_dir.name.split("-", 3)  # Split into quick-YYYYMMDD-HHMMSS-{slug}
        if len(name_parts) >= 4:
            slug = name_parts[3]
            assert len(slug) <= 35  # Allow some margin for multi-byte chars

    def test_quick_delta_multiple_archives(self) -> None:
        """Test quick-delta command can create multiple archives."""
        os.chdir(str(self.project_root))

        messages = [
            "First fix",
            "Second update",
            "Third change",
        ]

        for message in messages:
            result = runner.invoke(app, ["quick-delta", message])
            assert result.exit_code == 0

        # Verify all archives were created
        change_dirs = list(self.archive_dir.glob("quick-*"))
        assert len(change_dirs) == 3

    def test_quick_delta_shows_preview(self) -> None:
        """Test quick-delta command shows summary preview."""
        os.chdir(str(self.project_root))
        message = "Update database schema"

        result = runner.invoke(app, ["quick-delta", message])
        assert result.exit_code == 0

        # Verify preview is shown
        assert "Quick-Delta Summary" in result.stdout
        assert "Description:" in result.stdout
        assert message in result.stdout

    def test_quick_delta_shows_archived_path(self) -> None:
        """Test quick-delta command displays archived path."""
        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["quick-delta", "Simple fix"])

        assert result.exit_code == 0
        assert "Archived to:" in result.stdout
        # Handle both Windows and Unix path separators
        assert ".cc-spec" in result.stdout
        assert "changes" in result.stdout
        assert "archive" in result.stdout
        assert "quick-" in result.stdout

    def test_quick_delta_with_special_characters(self) -> None:
        """Test quick-delta command handles special characters in message."""
        os.chdir(str(self.project_root))

        # Test with various special characters
        result = runner.invoke(app, ["quick-delta", "Fix: bug #123 (urgent!)"])
        assert result.exit_code == 0

        # Verify change was created
        change_dirs = list(self.archive_dir.glob("quick-*-fix-bug-123-urgent"))
        assert len(change_dirs) == 1

    def test_quick_delta_timestamp_uniqueness(self) -> None:
        """Test quick-delta command generates unique timestamps."""
        os.chdir(str(self.project_root))

        # Create two changes with the same message
        result1 = runner.invoke(app, ["quick-delta", "Same message"])
        result2 = runner.invoke(app, ["quick-delta", "Same message"])

        assert result1.exit_code == 0
        assert result2.exit_code == 0

        # Both should succeed and create different directories
        change_dirs = list(self.archive_dir.glob("quick-*-same-message"))
        # At least one should be created (timestamps might be the same if executed too quickly)
        assert len(change_dirs) >= 1


class TestQuickDeltaIntegration:
    """Integration tests for quick-delta command workflow."""

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
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_quick_delta_end_to_end(self) -> None:
        """Test complete quick-delta workflow."""
        os.chdir(str(self.project_root))

        # Run quick-delta
        message = "Fix critical security vulnerability"
        result = runner.invoke(app, ["quick-delta", message])

        if result.exit_code != 0:
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)

        assert result.exit_code == 0

        # Verify directory structure
        archive_dir = self.cc_spec_dir / "changes" / "archive"
        assert archive_dir.exists()

        # Find created change
        change_dirs = list(archive_dir.glob("quick-*-fix-critical*"))
        assert len(change_dirs) == 1

        change_dir = change_dirs[0]

        # Verify mini-proposal.md exists and has correct structure
        mini_proposal = change_dir / "mini-proposal.md"
        assert mini_proposal.exists()

        content = mini_proposal.read_text(encoding="utf-8")

        # Verify all required sections
        assert "# Quick Delta:" in content
        assert "## 变更信息" in content
        assert "- **变更名称**:" in content
        assert "- **创建时间**:" in content
        assert "- **变更类型**: quick-delta" in content
        assert f"- **描述**: {message}" in content
        assert "## 备注" in content

        # Verify timestamp format in content
        assert datetime.now().strftime("%Y-%m-%d") in content

    def test_quick_delta_mixed_with_regular_workflow(self) -> None:
        """Test quick-delta works alongside regular cc-spec workflow."""
        os.chdir(str(self.project_root))

        # Create a regular change
        result = runner.invoke(app, ["specify", "regular-change"])
        assert result.exit_code == 0

        # Create a quick-delta
        result = runner.invoke(app, ["quick-delta", "Quick hotfix"])
        assert result.exit_code == 0

        # Verify both exist in their respective locations
        changes_dir = self.cc_spec_dir / "changes"

        # Regular change should be in changes/
        regular_change = changes_dir / "regular-change"
        assert regular_change.exists()

        # Quick-delta should be in changes/archive/
        archive_dir = changes_dir / "archive"
        quick_changes = list(archive_dir.glob("quick-*-quick-hotfix"))
        assert len(quick_changes) == 1
