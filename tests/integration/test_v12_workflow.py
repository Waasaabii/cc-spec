"""Integration tests for v0.1.6 command surfaces."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from cc_spec.core.command_generator import ClaudeCommandGenerator, get_available_agents, get_generator


class TestCommandGeneratorSurface:
    def test_only_claude_generator_available(self) -> None:
        assert get_available_agents() == ["claude"]
        assert isinstance(get_generator("claude"), ClaudeCommandGenerator)
        assert get_generator("cursor") is None


class TestUpdateTemplatesWorkflow:
    def test_template_files_defined(self) -> None:
        from cc_spec.commands.update import TEMPLATE_FILES

        assert len(TEMPLATE_FILES) >= 4
        assert "spec-template.md" in TEMPLATE_FILES
        assert "plan-template.md" in TEMPLATE_FILES

    def test_templates_directory_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            from cc_spec.commands.update import _update_templates

            cc_spec_root = Path(tmpdir) / ".cc-spec"
            cc_spec_root.mkdir(parents=True)

            with patch("cc_spec.commands.update.download_file", new_callable=AsyncMock) as mock_dl:
                mock_dl.return_value = False
                _update_templates(cc_spec_root, force=True)

            assert (cc_spec_root / "templates").exists()


class TestGotoExecuteWorkflow:
    def test_execute_command_helper(self) -> None:
        from cc_spec.commands.goto import _execute_command

        with patch("cc_spec.commands.goto.console") as mock_console:
            _execute_command("tasks.md")
            assert mock_console.print.called

        with patch("cc_spec.commands.goto.subprocess.run") as mock_run:
            mock_run.return_value = type("obj", (object,), {"returncode": 0})()
            with patch("cc_spec.commands.goto.console"):
                _execute_command("cc-spec list")
            mock_run.assert_called_once()


class TestRegisteredCommands:
    def test_cli_commands_registered(self) -> None:
        from cc_spec import app

        commands = [cmd.name for cmd in app.registered_commands]
        groups = [g.name for g in app.registered_groups]
        assert "kb" in groups
        assert "init" in commands
        assert "apply" in commands
        assert len(commands) == 11
