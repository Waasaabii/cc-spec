"""Unit tests for archive command."""

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


class TestArchiveCommand:
    """Tests for archive command."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        self.cc_spec_dir = self.project_root / ".cc-spec"
        self.changes_dir = self.cc_spec_dir / "changes"
        self.specs_dir = self.cc_spec_dir / "specs"
        self.change_name = "add-oauth"
        self.change_dir = self.changes_dir / self.change_name

        # Create project structure
        self.cc_spec_dir.mkdir(parents=True, exist_ok=True)
        self.changes_dir.mkdir(parents=True, exist_ok=True)
        self.specs_dir.mkdir(parents=True, exist_ok=True)
        self.change_dir.mkdir(parents=True, exist_ok=True)

        # Save original working directory
        self.original_cwd = os.getcwd()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        # Restore original working directory
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_status(self, checklist_completed: bool = True) -> Path:
        """Helper to create status.yaml.

        Args:
            checklist_completed: Whether checklist stage is completed
        """
        state = ChangeState(
            change_name=self.change_name,
            created_at=datetime.now().isoformat(),
            current_stage=Stage.CHECKLIST,
            stages={
                Stage.SPECIFY: StageInfo(
                    status=TaskStatus.COMPLETED,
                    started_at=datetime.now().isoformat(),
                    completed_at=datetime.now().isoformat(),
                ),
                Stage.CLARIFY: StageInfo(
                    status=TaskStatus.COMPLETED,
                    started_at=datetime.now().isoformat(),
                    completed_at=datetime.now().isoformat(),
                ),
                Stage.PLAN: StageInfo(
                    status=TaskStatus.COMPLETED,
                    started_at=datetime.now().isoformat(),
                    completed_at=datetime.now().isoformat(),
                ),
                Stage.APPLY: StageInfo(
                    status=TaskStatus.COMPLETED,
                    started_at=datetime.now().isoformat(),
                    completed_at=datetime.now().isoformat(),
                ),
                Stage.CHECKLIST: StageInfo(
                    status=TaskStatus.COMPLETED if checklist_completed else TaskStatus.IN_PROGRESS,
                    started_at=datetime.now().isoformat(),
                    completed_at=datetime.now().isoformat() if checklist_completed else None,
                ),
                Stage.ARCHIVE: StageInfo(status=TaskStatus.PENDING),
            },
        )

        status_path = self.change_dir / "status.yaml"
        update_state(status_path, state)
        return status_path

    def _create_delta_spec(
        self, capability: str = "auth", content: str | None = None
    ) -> Path:
        """Helper to create Delta spec.md.

        Args:
            capability: Capability name
            content: Optional custom content
        """
        if content is None:
            content = f"""# Delta: {capability}

## ADDED Requirements

### Requirement: OAuth2 Authentication
The system SHALL support OAuth2 authentication flow.

#### Scenario: Google OAuth Success
- Given: User clicks "Login with Google"
- When: OAuth flow completes successfully
- Then: User session is created

## MODIFIED Requirements

### Requirement: User Session Management
The system SHALL manage user sessions with the following rules:
- Session timeout: 24 hours (modified from 1 hour)
- Refresh token support: enabled
"""

        spec_dir = self.change_dir / "specs" / capability
        spec_dir.mkdir(parents=True, exist_ok=True)

        spec_path = spec_dir / "spec.md"
        spec_path.write_text(content, encoding="utf-8")
        return spec_path

    def _create_base_spec(self, capability: str = "auth") -> Path:
        """Helper to create base spec in main specs/ directory."""
        content = """# Spec: auth

## Requirements

### Requirement: User Session Management
The system SHALL manage user sessions with the following rules:
- Session timeout: 1 hour
"""

        spec_dir = self.specs_dir / capability
        spec_dir.mkdir(parents=True, exist_ok=True)

        spec_path = spec_dir / "spec.md"
        spec_path.write_text(content, encoding="utf-8")
        return spec_path

    def test_archive_without_project_root(self) -> None:
        """Test archive command fails when not in a project."""
        # Mock find_project_root to return None (simulates not being in a project)
        with patch("cc_spec.commands.archive.find_project_root", return_value=None):
            result = runner.invoke(app, ["archive", "test-change"])
            assert result.exit_code == 1
            assert "cc-spec" in result.stdout  # Error message contains project name

    def test_archive_without_change(self) -> None:
        """Test archive command fails when change doesn't exist."""
        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["archive", "nonexistent-change"])
        assert result.exit_code == 1
        assert "未找到" in result.stdout or "not found" in result.stdout

    def test_archive_without_checklist_completed(self) -> None:
        """Test archive command fails when checklist not completed."""
        self._create_status(checklist_completed=False)

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["archive", self.change_name, "--force"])
        assert result.exit_code == 1
        assert "checklist" in result.stdout.lower() or "完成" in result.stdout

    def test_archive_with_no_specs(self) -> None:
        """Test archive command succeeds even without specs directory."""
        self._create_status(checklist_completed=True)

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["archive", self.change_name, "--force"])

        if result.exit_code != 0:
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)

        assert result.exit_code == 0
        # Support Chinese output: "归档完成！"
        assert "归档完成" in result.stdout or "Archive" in result.stdout or "completed" in result.stdout.lower()

        # Verify change was moved to archive
        archive_dir = self.changes_dir / "archive"
        assert archive_dir.exists()

        # Find archived change (with timestamp prefix)
        archived_changes = list(archive_dir.glob(f"*-{self.change_name}"))
        assert len(archived_changes) == 1

    def test_archive_merges_delta_specs(self) -> None:
        """Test archive command merges Delta specs into main specs."""
        self._create_status(checklist_completed=True)
        self._create_base_spec("auth")
        self._create_delta_spec("auth")

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["archive", self.change_name, "--force"])

        if result.exit_code != 0:
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)

        assert result.exit_code == 0
        assert "合并" in result.stdout or "Merged" in result.stdout or "成功" in result.stdout

        # Verify merged spec exists
        merged_spec = self.specs_dir / "auth" / "spec.md"
        assert merged_spec.exists()

        # Verify merged content contains new requirement
        content = merged_spec.read_text(encoding="utf-8")
        assert "OAuth2 Authentication" in content
        assert "24 hours" in content  # Modified value

    def test_archive_creates_new_spec_file(self) -> None:
        """Test archive command creates new spec file for ADDED capability."""
        self._create_status(checklist_completed=True)
        # Create delta spec with only ADDED requirements (no MODIFIED)
        delta_content = """# Delta: oauth

## ADDED Requirements

### Requirement: OAuth2 Authentication
The system SHALL support OAuth2 authentication flow.

#### Scenario: Google OAuth Success
- Given: User clicks "Login with Google"
- When: OAuth flow completes successfully
- Then: User session is created
"""
        self._create_delta_spec("oauth", content=delta_content)

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["archive", self.change_name, "--force"])

        if result.exit_code != 0:
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr if hasattr(result, 'stderr') else "N/A")
        assert result.exit_code == 0

        # Verify new spec was created
        new_spec = self.specs_dir / "oauth" / "spec.md"
        assert new_spec.exists()

        content = new_spec.read_text(encoding="utf-8")
        assert "OAuth2 Authentication" in content

    def test_archive_moves_to_archive_directory(self) -> None:
        """Test archive command moves change to archive with timestamp."""
        self._create_status(checklist_completed=True)
        # Create delta spec with only ADDED requirements (no MODIFIED)
        delta_content = """# Delta: auth

## ADDED Requirements

### Requirement: OAuth2 Authentication
The system SHALL support OAuth2 authentication flow.

#### Scenario: Google OAuth Success
- Given: User clicks "Login with Google"
- When: OAuth flow completes successfully
- Then: User session is created
"""
        self._create_delta_spec("auth", content=delta_content)

        # Create additional files in change directory
        (self.change_dir / "proposal.md").write_text("# Proposal\n", encoding="utf-8")
        (self.change_dir / "tasks.md").write_text("# Tasks\n", encoding="utf-8")

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["archive", self.change_name, "--force"])

        if result.exit_code != 0:
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr if hasattr(result, 'stderr') else "N/A")
        assert result.exit_code == 0

        # Verify change directory no longer exists in changes/
        assert not self.change_dir.exists()

        # Verify archive directory was created
        archive_dir = self.changes_dir / "archive"
        assert archive_dir.exists()

        # Find archived change (with timestamp prefix)
        today = datetime.now().strftime("%Y-%m-%d")
        archived_changes = list(archive_dir.glob(f"{today}-{self.change_name}*"))
        assert len(archived_changes) == 1

        archived_change = archived_changes[0]

        # Verify all files were moved
        assert (archived_change / "proposal.md").exists()
        assert (archived_change / "tasks.md").exists()
        assert (archived_change / "status.yaml").exists()
        assert (archived_change / "specs" / "auth" / "spec.md").exists()

    def test_archive_without_explicit_change_name(self) -> None:
        """Test archive command uses current active change when name not provided."""
        self._create_status(checklist_completed=True)

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["archive", "--force"])

        assert result.exit_code == 0
        assert "归档完成" in result.stdout or "Archive completed successfully" in result.stdout

        # Verify change was archived
        assert not self.change_dir.exists()

    def test_archive_with_invalid_delta_spec(self) -> None:
        """Test archive command fails when Delta spec is invalid."""
        self._create_status(checklist_completed=True)

        # Create invalid Delta spec (missing required fields)
        invalid_content = """# Delta: auth

## ADDED Requirements

### Requirement: OAuth2 Authentication
"""  # Missing content

        self._create_delta_spec("auth", content=invalid_content)

        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["archive", self.change_name, "--force"])

        assert result.exit_code == 1
        # Support Chinese output: "校验失败"
        assert "校验失败" in result.stdout.lower() or "validation failed" in result.stdout.lower()

    def test_archive_shows_merge_preview(self) -> None:
        """Test archive command shows merge preview before confirmation."""
        self._create_status(checklist_completed=True)
        self._create_base_spec("auth")
        self._create_delta_spec("auth")

        os.chdir(str(self.project_root))

        # Run without --force to see preview
        result = runner.invoke(app, ["archive", self.change_name], input="n\n")

        # Support Chinese output: "合并预览：" instead of "Merge Preview"
        assert "合并预览" in result.stdout or "Merge Preview" in result.stdout
        assert "新增需求" in result.stdout or "修改需求" in result.stdout or "ADDED Requirements" in result.stdout or "MODIFIED Requirements" in result.stdout
        assert "取消" in result.stdout or "cancelled" in result.stdout.lower()

    def test_archive_handles_duplicate_archive_name(self) -> None:
        """Test archive command handles collision when archive already exists."""
        self._create_status(checklist_completed=True)

        # Create first archive
        os.chdir(str(self.project_root))
        result = runner.invoke(app, ["archive", self.change_name, "--force"])
        assert result.exit_code == 0

        # Recreate change directory
        self.change_dir.mkdir(parents=True, exist_ok=True)
        self._create_status(checklist_completed=True)

        # Try to archive again (should add time suffix)
        result = runner.invoke(app, ["archive", self.change_name, "--force"])
        assert result.exit_code == 0

        # Verify two archives exist
        archive_dir = self.changes_dir / "archive"
        today = datetime.now().strftime("%Y-%m-%d")
        archived_changes = list(archive_dir.glob(f"{today}-{self.change_name}*"))
        assert len(archived_changes) == 2


class TestArchiveIntegration:
    """Integration tests for archive command workflow."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        self.cc_spec_dir = self.project_root / ".cc-spec"

        # Create .cc-spec directory
        self.cc_spec_dir.mkdir(parents=True, exist_ok=True)

    def teardown_method(self) -> None:
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_full_workflow_to_archive(self) -> None:
        """Test complete workflow from specify to archive."""
        os.chdir(str(self.project_root))

        # Step 1: Create change with specify
        result = runner.invoke(app, ["specify", "add-oauth"])
        assert result.exit_code == 0

        changes_dir = self.cc_spec_dir / "changes"
        change_dir = changes_dir / "add-oauth"

        # Step 2: Manually mark checklist as completed
        status_path = change_dir / "status.yaml"
        state = load_state(status_path)

        state.current_stage = Stage.CHECKLIST
        state.stages[Stage.CHECKLIST] = StageInfo(
            status=TaskStatus.COMPLETED,
            started_at=datetime.now().isoformat(),
            completed_at=datetime.now().isoformat(),
        )
        update_state(status_path, state)

        # Step 3: Create a Delta spec
        spec_dir = change_dir / "specs" / "auth"
        spec_dir.mkdir(parents=True, exist_ok=True)

        delta_content = """# Delta: auth

## ADDED Requirements

### Requirement: OAuth Support
The system SHALL support OAuth authentication.
"""
        (spec_dir / "spec.md").write_text(delta_content, encoding="utf-8")

        # Step 4: Run archive
        result = runner.invoke(app, ["archive", "add-oauth", "--force"])

        if result.exit_code != 0:
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)

        assert result.exit_code == 0
        assert "归档完成" in result.stdout or "Archive completed successfully" in result.stdout

        # Step 5: Verify change was archived
        assert not change_dir.exists()

        archive_dir = changes_dir / "archive"
        archived_changes = list(archive_dir.glob("*-add-oauth*"))
        assert len(archived_changes) == 1

        # Step 6: Verify spec was merged
        specs_dir = self.cc_spec_dir / "specs"
        merged_spec = specs_dir / "auth" / "spec.md"
        assert merged_spec.exists()

        content = merged_spec.read_text(encoding="utf-8")
        assert "OAuth Support" in content
