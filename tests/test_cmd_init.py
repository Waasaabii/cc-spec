"""Tests for the init command (v1.2)."""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from cc_spec import app
from cc_spec.core.config import Config, load_config, save_config
from cc_spec.utils.files import get_cc_spec_dir, get_config_path

runner = CliRunner()


def test_init_creates_directory_structure(tmp_path, monkeypatch):
    """Test that init creates the correct directory structure."""
    monkeypatch.chdir(tmp_path)

    # Mock select_option to avoid interactive prompts
    with patch("cc_spec.commands.init.select_option", return_value="claude"):
        result = runner.invoke(app, ["init", "test-project", "--agent", "claude"])

    assert result.exit_code == 0
    assert (tmp_path / ".cc-spec").exists()
    assert (tmp_path / ".cc-spec" / "templates").exists()
    assert (tmp_path / ".cc-spec" / "changes").exists()
    assert (tmp_path / ".cc-spec" / "specs").exists()


def test_init_creates_config_file(tmp_path, monkeypatch):
    """Test that init creates a valid config.yaml file."""
    monkeypatch.chdir(tmp_path)

    with patch("cc_spec.commands.init.select_option", return_value="claude"):
        result = runner.invoke(app, ["init", "test-project", "--agent", "claude"])

    assert result.exit_code == 0

    config_path = get_config_path(tmp_path)
    assert config_path.exists()

    # Load and verify config
    config = load_config(config_path)
    assert config.project_name == "test-project"
    assert config.version == "1.2"  # v1.2 default
    assert config.agents.default == "claude"


def test_init_with_specified_agent(tmp_path, monkeypatch):
    """Test init with --agent option."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "test-project", "--agent", "cursor"])

    assert result.exit_code == 0

    config_path = get_config_path(tmp_path)
    config = load_config(config_path)
    assert config.agents.default == "cursor"
    assert "cursor" in config.agents.enabled


def test_init_detects_existing_agent(tmp_path, monkeypatch):
    """Test that init detects existing AI agent directories."""
    monkeypatch.chdir(tmp_path)

    # Create .claude directory to simulate Claude Code presence
    (tmp_path / ".claude").mkdir()

    # Mock select_option to simulate user accepting detected agent
    with patch("cc_spec.commands.init.select_option", return_value="use_detected"):
        result = runner.invoke(app, ["init", "test-project"])

    assert result.exit_code == 0

    config_path = get_config_path(tmp_path)
    config = load_config(config_path)
    assert config.agents.default == "claude"


def test_init_fails_if_already_initialized(tmp_path, monkeypatch):
    """Test that init fails if .cc-spec already exists (without --force)."""
    monkeypatch.chdir(tmp_path)

    # Create .cc-spec directory
    cc_spec_dir = get_cc_spec_dir(tmp_path)
    cc_spec_dir.mkdir(parents=True)

    result = runner.invoke(app, ["init", "test-project"])

    assert result.exit_code == 1
    # Chinese or English message
    assert "已存在" in result.stdout or "already exists" in result.stdout


def test_init_with_force_overwrites_existing(tmp_path, monkeypatch):
    """Test that init with --force overwrites existing configuration."""
    monkeypatch.chdir(tmp_path)

    # Create existing .cc-spec with old config
    cc_spec_dir = get_cc_spec_dir(tmp_path)
    cc_spec_dir.mkdir(parents=True)
    config_path = get_config_path(tmp_path)

    old_config = Config(
        version="1.0",
        project_name="old-project",
        agent="cursor",
    )
    save_config(old_config, config_path)

    result = runner.invoke(
        app, ["init", "new-project", "--agent", "gemini", "--force"]
    )

    assert result.exit_code == 0

    # Verify config was overwritten
    config = load_config(config_path)
    assert config.project_name == "new-project"
    assert config.agents.default == "gemini"


def test_init_uses_directory_name_as_default_project_name(tmp_path, monkeypatch):
    """Test that init uses current directory name as default project name."""
    project_dir = tmp_path / "my-awesome-project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)

    # Mock select_option to avoid interactive prompts
    with patch("cc_spec.commands.init.select_option", return_value="claude"):
        result = runner.invoke(app, ["init", "--agent", "claude"])

    assert result.exit_code == 0

    config_path = get_config_path(project_dir)
    config = load_config(config_path)
    assert config.project_name == "my-awesome-project"


def test_init_handles_template_copy_failure_gracefully(tmp_path, monkeypatch):
    """Test that init handles template copy failures gracefully."""
    monkeypatch.chdir(tmp_path)

    # Mock shutil.copy2 to raise an exception
    def mock_copy_fail(*args, **kwargs):
        raise Exception("Copy error")

    with patch("shutil.copy2", side_effect=mock_copy_fail):
        result = runner.invoke(app, ["init", "test-project", "--agent", "claude"])

    # Should still succeed (with warning) even if template copy fails
    assert result.exit_code == 0

    # Config should still be created
    config_path = get_config_path(tmp_path)
    assert config_path.exists()


def test_init_displays_success_message(tmp_path, monkeypatch):
    """Test that init displays a success message with next steps."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "test-project", "--agent", "claude"])

    assert result.exit_code == 0
    # Check for Chinese success message
    assert "初始化完成" in result.stdout or "成功初始化" in result.stdout
    assert "test-project" in result.stdout
    assert "cc-spec specify" in result.stdout


def test_init_creates_agents_md(tmp_path, monkeypatch):
    """Test that init creates AGENTS.md file."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "test-project", "--agent", "claude"])

    assert result.exit_code == 0
    agents_md = tmp_path / "AGENTS.md"
    assert agents_md.exists()
    content = agents_md.read_text(encoding="utf-8")
    assert "cc-spec" in content


def test_init_creates_agent_folder(tmp_path, monkeypatch):
    """Test that init creates the AI tool folder."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "test-project", "--agent", "claude"])

    assert result.exit_code == 0
    # Claude uses .claude folder
    assert (tmp_path / ".claude").exists()


def test_init_creates_codex_prompts_when_selected(tmp_path, monkeypatch):
    """Test that init generates Codex CLI prompts when codex is selected."""
    monkeypatch.chdir(tmp_path)
    codex_prompts_dir = tmp_path / ".codex-user" / "prompts"
    monkeypatch.setenv("CC_SPEC_CODEX_PROMPTS_DIR", str(codex_prompts_dir))

    result = runner.invoke(app, ["init", "test-project", "--agent", "codex"])

    assert result.exit_code == 0
    assert codex_prompts_dir.exists()
    assert (codex_prompts_dir / "cc-spec-specify.md").exists()
