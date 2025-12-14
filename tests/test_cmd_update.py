"""Tests for the update command (v1.2)."""

import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest
import yaml
from typer.testing import CliRunner

from cc_spec import app
from cc_spec.commands.update import (
    AVAILABLE_AGENTS,
    MANAGED_END,
    MANAGED_START,
    TEMPLATE_FILES,
    _add_agent,
    _get_agent_command_dir,
    _update_managed_block,
)
from cc_spec.core.config import Config, save_config
from cc_spec.utils.files import get_cc_spec_dir

runner = CliRunner()


class TestAvailableAgents:
    """Tests for AVAILABLE_AGENTS constant."""

    def test_available_agents_count(self) -> None:
        """Test that we have 18 available agents (10 original + 8 new)."""
        assert len(AVAILABLE_AGENTS) == 18

    def test_available_agents_original(self) -> None:
        """Test original agents are in list."""
        original = ["claude", "cursor", "gemini", "copilot", "amazonq",
                    "windsurf", "qwen", "codeium", "continue", "codex"]
        for agent in original:
            assert agent in AVAILABLE_AGENTS

    def test_available_agents_new_v12(self) -> None:
        """Test 8 new v1.2 agents are in list."""
        new_agents = ["tabnine", "aider", "devin", "replit",
                      "cody", "supermaven", "kilo", "auggie"]
        for agent in new_agents:
            assert agent in AVAILABLE_AGENTS


class TestTemplateFiles:
    """Tests for TEMPLATE_FILES constant."""

    def test_template_files_count(self) -> None:
        """Test template files list."""
        assert len(TEMPLATE_FILES) >= 4  # At least core templates
        assert "spec-template.md" in TEMPLATE_FILES
        assert "plan-template.md" in TEMPLATE_FILES


class TestGetAgentCommandDir:
    """Tests for _get_agent_command_dir function."""

    def test_get_agent_command_dir_claude(self) -> None:
        """Test Claude command directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cmd_dir = _get_agent_command_dir(project_root, "claude")
            assert cmd_dir == project_root / ".claude" / "commands" / "cc-spec"

    def test_get_agent_command_dir_cursor(self) -> None:
        """Test Cursor command directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cmd_dir = _get_agent_command_dir(project_root, "cursor")
            assert cmd_dir == project_root / ".cursor" / "commands"

    def test_get_agent_command_dir_unknown(self) -> None:
        """Test unknown agent returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cmd_dir = _get_agent_command_dir(project_root, "unknown")
            assert cmd_dir is None


class TestUpdateManagedBlock:
    """Tests for _update_managed_block function."""

    def test_update_managed_block(self) -> None:
        """Test updating managed block preserves user content."""
        existing = f"""---
description: Test
---

User content before

{MANAGED_START}
Old managed content
{MANAGED_END}

User content after
"""
        new_content = f"""{MANAGED_START}
New managed content
{MANAGED_END}"""

        result = _update_managed_block(existing, new_content)

        assert "User content before" in result
        assert "User content after" in result
        assert "New managed content" in result
        assert "Old managed content" not in result


class TestUpdateCommand:
    """Tests for update command."""

    def test_update_fails_without_project(self, tmp_path, monkeypatch) -> None:
        """Test update fails if not in a project."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["update"])

        assert result.exit_code == 1
        assert "cc-spec" in result.stdout.lower() or "not found" in result.stdout.lower()

    def test_update_shows_agents(self, tmp_path, monkeypatch) -> None:
        """Test update agents shows available agents."""
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

        result = runner.invoke(app, ["update", "agents"])

        assert result.exit_code == 0
        assert "claude" in result.stdout
        assert "cursor" in result.stdout

    def test_update_templates_creates_templates_dir(self, tmp_path, monkeypatch) -> None:
        """Test update --templates creates templates directory."""
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

        # Mock download to fail so it uses local fallback
        with patch("cc_spec.commands.update.download_file", new_callable=AsyncMock) as mock_download:
            mock_download.return_value = False

            result = runner.invoke(app, ["update", "--templates"])

        assert result.exit_code == 0
        templates_dir = cc_spec_dir / "templates"
        assert templates_dir.exists()

    def test_update_add_agent_recognized(self, tmp_path, monkeypatch) -> None:
        """Test update --add-agent with recognized agent."""
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

        result = runner.invoke(app, ["update", "--add-agent", "gemini"])

        assert result.exit_code == 0
        assert "gemini" in result.stdout.lower() or "Adding agent" in result.stdout

    def test_update_add_agent_unrecognized(self, tmp_path, monkeypatch) -> None:
        """Test update --add-agent with unrecognized agent shows warning."""
        monkeypatch.chdir(tmp_path)

        # Setup project
        cc_spec_dir = get_cc_spec_dir(tmp_path)
        cc_spec_dir.mkdir(parents=True)

        config = Config(
            version="1.3",  # Updated to current version
            agent="claude",
            project_name="test",
        )
        save_config(config, cc_spec_dir / "config.yaml")

        result = runner.invoke(app, ["update", "--add-agent", "unknown-agent"])

        assert result.exit_code == 0
        # Support Chinese and English output
        assert ("未识别" in result.stdout.lower() or "not a recognized agent" in result.stdout.lower()
                or "warning" in result.stdout.lower() or "警告" in result.stdout)


class TestUpdateSubagentConfig:
    """Tests for subagent configuration update."""

    def test_update_subagent_adds_profiles(self, tmp_path, monkeypatch) -> None:
        """Test update subagent adds profiles if missing."""
        monkeypatch.chdir(tmp_path)

        # Setup project with minimal config
        cc_spec_dir = get_cc_spec_dir(tmp_path)
        cc_spec_dir.mkdir(parents=True)

        config_path = cc_spec_dir / "config.yaml"
        config_data = {
            "version": "1.0",
            "agent": "claude",
            "project_name": "test",
        }
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f)

        result = runner.invoke(app, ["update", "subagent"])

        assert result.exit_code == 0

        # Check config was updated
        with open(config_path, encoding="utf-8") as f:
            updated = yaml.safe_load(f)

        assert "subagent" in updated
        assert "common" in updated["subagent"]
        assert "profiles" in updated["subagent"]
