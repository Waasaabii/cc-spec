"""Tests for the goto command (v1.2)."""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml
from typer.testing import CliRunner

from cc_spec import app
from cc_spec.commands.goto import _execute_command
from cc_spec.core.config import Config, save_config
from cc_spec.core.state import ChangeState, Stage, StageInfo, TaskStatus
from cc_spec.utils.files import get_cc_spec_dir

runner = CliRunner()


class TestExecuteCommand:
    """Tests for _execute_command helper function (v1.2)."""

    def test_execute_command_skips_non_commands(self, capsys) -> None:
        """Test that non-command strings are skipped."""
        with patch("cc_spec.commands.goto.console") as mock_console:
            _execute_command("proposal.md")
            # Should print note about file, not command
            mock_console.print.assert_called()
            call_args = str(mock_console.print.call_args)
            assert "file" in call_args.lower() or "not a command" in call_args.lower()

    def test_execute_command_runs_cc_spec_command(self) -> None:
        """Test that cc-spec commands are executed."""
        with patch("cc_spec.commands.goto.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("cc_spec.commands.goto.console"):
                _execute_command("cc-spec list")

            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert "cc-spec list" in call_args[0][0]

    def test_execute_command_handles_nonzero_exit(self) -> None:
        """Test handling of non-zero exit code."""
        with patch("cc_spec.commands.goto.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            with patch("cc_spec.commands.goto.console") as mock_console:
                _execute_command("cc-spec apply C-001")

            # Should print warning about exit code
            calls = [str(c) for c in mock_console.print.call_args_list]
            assert any("exit" in c.lower() or "code" in c.lower() for c in calls)

    def test_execute_command_handles_subprocess_error(self) -> None:
        """Test handling of subprocess errors."""
        import subprocess
        with patch("cc_spec.commands.goto.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.SubprocessError("Test error")
            with patch("cc_spec.commands.goto.console") as mock_console:
                _execute_command("cc-spec apply C-001")

            # Should print error message
            calls = [str(c) for c in mock_console.print.call_args_list]
            assert any("error" in c.lower() for c in calls)


class TestGotoCommand:
    """Tests for goto command."""

    def test_goto_fails_without_project(self, tmp_path, monkeypatch) -> None:
        """Test goto fails if not in a project (with isolated filesystem)."""
        # Create a truly isolated directory without any .cc-spec above it
        isolated_dir = tmp_path / "isolated_project"
        isolated_dir.mkdir()
        monkeypatch.chdir(isolated_dir)

        # Mock find_project_root to return None
        with patch("cc_spec.commands.goto.find_project_root", return_value=None):
            result = runner.invoke(app, ["goto", "C-001"])

        assert result.exit_code == 1
        assert "Not in a cc-spec project" in result.stdout or "init" in result.stdout.lower()

    def test_goto_fails_with_invalid_change(self, tmp_path, monkeypatch) -> None:
        """Test goto fails with non-existent change."""
        monkeypatch.chdir(tmp_path)

        # Setup minimal project
        cc_spec_dir = get_cc_spec_dir(tmp_path)
        cc_spec_dir.mkdir(parents=True)

        config = Config(
            version="1.2",
            agent="claude",
            project_name="test",
        )
        save_config(config, cc_spec_dir / "config.yaml")

        # Create empty registry
        registry_path = cc_spec_dir / "registry.yaml"
        registry_path.write_text("changes: {}\nspecs: {}\n", encoding="utf-8")

        result = runner.invoke(app, ["goto", "C-999"])

        assert result.exit_code == 1
        assert "not found" in result.stdout.lower() or "error" in result.stdout.lower()

    def test_goto_spec_shows_info_message(self, tmp_path, monkeypatch) -> None:
        """Test goto with spec ID shows info message."""
        monkeypatch.chdir(tmp_path)

        # Setup project
        cc_spec_dir = get_cc_spec_dir(tmp_path)
        cc_spec_dir.mkdir(parents=True)

        config = Config(
            version="1.2",
            agent="claude",
            project_name="test",
        )
        save_config(config, cc_spec_dir / "config.yaml")

        # Create registry with spec
        registry_data = {
            "changes": {},
            "specs": {
                "S-001": {"name": "test-spec", "path": "specs/test-spec"}
            },
        }
        registry_path = cc_spec_dir / "registry.yaml"
        with open(registry_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(registry_data, f)

        result = runner.invoke(app, ["goto", "S-001"])

        # Should show info about specs not having navigation
        assert "spec" in result.stdout.lower()

    def test_goto_archive_shows_info_message(self, tmp_path, monkeypatch) -> None:
        """Test goto with archive ID shows info message."""
        monkeypatch.chdir(tmp_path)

        # Setup project
        cc_spec_dir = get_cc_spec_dir(tmp_path)
        cc_spec_dir.mkdir(parents=True)

        config = Config(
            version="1.2",
            agent="claude",
            project_name="test",
        )
        save_config(config, cc_spec_dir / "config.yaml")

        # Create registry with archive
        registry_data = {
            "changes": {},
            "specs": {},
            "archives": {
                "A-001": {"name": "archived-change", "path": "archive/archived-change"}
            },
        }
        registry_path = cc_spec_dir / "registry.yaml"
        with open(registry_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(registry_data, f)

        result = runner.invoke(app, ["goto", "A-001"])

        # Should show info about archives being read-only
        assert "archive" in result.stdout.lower()


class TestGotoOptions:
    """Tests for goto command options."""

    def test_goto_has_execute_option(self) -> None:
        """Test that goto command has --execute option."""
        result = runner.invoke(app, ["goto", "--help"])

        assert result.exit_code == 0
        assert "--execute" in result.stdout or "-x" in result.stdout

    def test_goto_has_force_option(self) -> None:
        """Test that goto command has --force option."""
        result = runner.invoke(app, ["goto", "--help"])

        assert result.exit_code == 0
        assert "--force" in result.stdout or "-f" in result.stdout
