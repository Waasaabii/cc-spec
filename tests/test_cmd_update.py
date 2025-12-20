"""Tests for the update command (v0.1.6)."""

from unittest.mock import AsyncMock, patch

import yaml
from typer.testing import CliRunner

from cc_spec import app
from cc_spec.core.config import Config, save_config
from cc_spec.utils.files import get_cc_spec_dir

runner = CliRunner()


class TestTemplateFiles:
    def test_template_files_defined(self) -> None:
        from cc_spec.commands.update import TEMPLATE_FILES

        assert len(TEMPLATE_FILES) >= 4
        assert "spec-template.md" in TEMPLATE_FILES
        assert "plan-template.md" in TEMPLATE_FILES


class TestUpdateCommand:
    def test_update_fails_without_project(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["update"])

        assert result.exit_code == 1
        assert "cc-spec" in result.stdout.lower() or "not" in result.stdout.lower()

    def test_update_commands_generates_claude_commands(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)

        cc_spec_dir = get_cc_spec_dir(tmp_path)
        cc_spec_dir.mkdir(parents=True)
        save_config(Config(project_name="test"), cc_spec_dir / "config.yaml")

        result = runner.invoke(app, ["update", "commands"])

        assert result.exit_code == 0
        cmd_dir = tmp_path / ".claude" / "commands" / "cc-spec"
        assert cmd_dir.exists()
        assert (cmd_dir / "specify.md").exists()

    def test_update_templates_creates_templates_dir(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)

        cc_spec_dir = get_cc_spec_dir(tmp_path)
        cc_spec_dir.mkdir(parents=True)
        save_config(Config(project_name="test"), cc_spec_dir / "config.yaml")

        with patch("cc_spec.commands.update.download_file", new_callable=AsyncMock) as mock_download:
            mock_download.return_value = False
            result = runner.invoke(app, ["update", "--templates"])

        assert result.exit_code == 0
        assert (cc_spec_dir / "templates").exists()


class TestUpdateSubagentConfig:
    def test_update_subagent_adds_profiles(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)

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

        with open(config_path, encoding="utf-8") as f:
            updated = yaml.safe_load(f) or {}

        assert "subagent" in updated
        assert "common" in updated["subagent"]
        assert "profiles" in updated["subagent"]
