"""Tests for the init command (v0.1.6)."""

from typer.testing import CliRunner

from cc_spec import app
from cc_spec.core.config import Config, load_config, save_config
from cc_spec.utils.files import get_cc_spec_dir, get_config_path

runner = CliRunner()


def test_init_creates_directory_structure(tmp_path, monkeypatch):
    """Test that init creates the correct directory structure."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "test-project"])

    assert result.exit_code == 0
    assert (tmp_path / ".cc-spec").exists()
    assert (tmp_path / ".cc-spec" / "templates").exists()
    assert (tmp_path / ".cc-spec" / "changes").exists()
    assert (tmp_path / ".cc-spec" / "specs").exists()
    assert (tmp_path / ".cc-spec" / "archive").exists()


def test_init_creates_config_file(tmp_path, monkeypatch):
    """Test that init creates a valid config.yaml file."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "test-project"])

    assert result.exit_code == 0

    config_path = get_config_path(tmp_path)
    assert config_path.exists()

    # Load and verify config
    config = load_config(config_path)
    assert config.project_name == "test-project"
    assert config.version == "1.3"  # Current default schema
    assert config.agents.default == "claude"


def test_init_rejects_non_claude_agent(tmp_path, monkeypatch):
    """Test init rejects non-claude --agent (deprecated flag)."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "test-project", "--agent", "cursor"])

    assert result.exit_code == 1


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
        app, ["init", "new-project", "--force"]
    )

    assert result.exit_code == 0

    # Verify config was overwritten
    config = load_config(config_path)
    assert config.project_name == "new-project"
    assert config.agents.default == "claude"


def test_init_uses_directory_name_as_default_project_name(tmp_path, monkeypatch):
    """Test that init uses current directory name as default project name."""
    project_dir = tmp_path / "my-awesome-project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)

    result = runner.invoke(app, ["init"])

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

    from unittest.mock import patch

    with patch("shutil.copy2", side_effect=mock_copy_fail):
        result = runner.invoke(app, ["init", "test-project"])

    # Should still succeed (with warning) even if template copy fails
    assert result.exit_code == 0

    # Config should still be created
    config_path = get_config_path(tmp_path)
    assert config_path.exists()


def test_init_displays_success_message(tmp_path, monkeypatch):
    """Test that init displays a success message with next steps."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "test-project"])

    assert result.exit_code == 0
    # Check for Chinese success message
    assert "初始化完成" in result.stdout or "成功初始化" in result.stdout
    assert "test-project" in result.stdout
    assert "/cc-spec:specify" in result.stdout


def test_init_creates_agents_md(tmp_path, monkeypatch):
    """Test that init creates AGENTS.md file."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "test-project"])

    assert result.exit_code == 0
    agents_md = tmp_path / "AGENTS.md"
    assert agents_md.exists()
    content = agents_md.read_text(encoding="utf-8")
    assert "cc-spec" in content


def test_init_creates_agent_folder(tmp_path, monkeypatch):
    """Test that init creates the AI tool folder."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "test-project"])

    assert result.exit_code == 0
    # Claude uses .claude folder
    assert (tmp_path / ".claude").exists()


def test_init_creates_cc_specignore(tmp_path, monkeypatch):
    """Test that init creates .cc-specignore for KB scanning rules."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "test-project"])

    assert result.exit_code == 0
    ignore_file = tmp_path / ".cc-specignore"
    assert ignore_file.exists()
    content = ignore_file.read_text(encoding="utf-8")
    assert "KB scanning ignore rules" in content


def test_init_creates_claude_commands(tmp_path, monkeypatch):
    """Test that init generates Claude Code slash command files."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "test-project"])

    assert result.exit_code == 0
    cmd_dir = tmp_path / ".claude" / "commands" / "cc-spec"
    assert cmd_dir.exists()
    assert (cmd_dir / "specify.md").exists()
