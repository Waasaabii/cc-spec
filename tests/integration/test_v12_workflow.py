"""Integration tests for cc-spec v1.2 features."""

import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest
import yaml

from cc_spec.core.config import (
    AgentsConfig,
    Config,
    SubAgentConfig,
    SubAgentProfile,
    load_config,
    save_config,
)
from cc_spec.core.command_generator import (
    COMMAND_GENERATORS,
    get_available_agents,
    get_generator,
    TabnineCommandGenerator,
    AiderCommandGenerator,
    DevinCommandGenerator,
    CodyCommandGenerator,
)


class TestAgentsConfigWorkflow:
    """Test multi-tool agents configuration workflow (v1.2)."""

    def test_agents_config_creation(self) -> None:
        """Test creating AgentsConfig with multiple agents."""
        config = AgentsConfig(
            enabled=["claude", "cursor", "gemini"],
            default="cursor",
        )

        assert len(config.enabled) == 3
        assert config.default == "cursor"
        assert "claude" in config.enabled
        assert "gemini" in config.enabled

    def test_agents_config_in_full_config(self) -> None:
        """Test AgentsConfig integrated with Config."""
        config = Config(
            version="1.2",
            agent="claude",  # Legacy field
            agents=AgentsConfig(
                enabled=["claude", "cursor", "amazonq"],
                default="cursor",
            ),
            project_name="multi-agent-project",
        )

        # get_active_agent should return agents.default
        assert config.get_active_agent() == "cursor"

        # Serialization
        data = config.to_dict()
        assert data["version"] == "1.2"
        assert "agents" in data
        assert data["agents"]["default"] == "cursor"
        assert len(data["agents"]["enabled"]) == 3

        # Deserialization
        restored = Config.from_dict(data)
        assert restored.get_active_agent() == "cursor"
        assert len(restored.agents.enabled) == 3

    def test_agents_config_fallback_to_agent(self) -> None:
        """Test fallback to agent field when agents is empty."""
        config = Config(
            agent="gemini",
            agents=AgentsConfig(enabled=[], default=""),
        )

        # Should fall back to agent field
        assert config.get_active_agent() == "gemini"

    def test_config_yaml_round_trip(self) -> None:
        """Test saving and loading config with agents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"

            # Create config with agents
            original = Config(
                version="1.2",
                agent="claude",
                agents=AgentsConfig(
                    enabled=["claude", "gemini", "cody"],
                    default="gemini",
                ),
                project_name="yaml-test",
            )

            save_config(original, config_path)
            restored = load_config(config_path)

            assert restored.version == "1.2"
            assert restored.get_active_agent() == "gemini"
            assert "cody" in restored.agents.enabled


class TestNewCommandGeneratorsWorkflow:
    """Test 8 new command generators added in v1.2."""

    @pytest.fixture
    def temp_project(self) -> Path:
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_generators_available(self) -> None:
        """Test that we now have 18 command generators."""
        agents = get_available_agents()

        assert len(agents) == 18

        # Original agents
        original = ["claude", "cursor", "gemini", "copilot", "amazonq",
                    "windsurf", "qwen", "codeium", "continue", "codex"]
        for agent in original:
            assert agent in agents

        # New 8 in v1.2
        new_v12 = ["tabnine", "aider", "devin", "replit",
                   "cody", "supermaven", "kilo", "auggie"]
        for agent in new_v12:
            assert agent in agents

    def test_new_generator_directory_structure(self, temp_project: Path) -> None:
        """Test new generators create correct directory structure."""
        test_cases = [
            ("tabnine", ".tabnine/commands/cc-spec"),
            ("aider", ".aider/commands"),
            ("devin", ".devin/commands/cc-spec"),
            ("replit", ".replit/commands"),
            ("cody", ".cody/commands/cc-spec"),
            ("supermaven", ".supermaven/commands"),
            ("kilo", ".kilo/commands"),
            ("auggie", ".auggie/commands/cc-spec"),
        ]

        for agent, expected_path in test_cases:
            generator = get_generator(agent)
            assert generator is not None, f"Generator for {agent} not found"

            cmd_dir = generator.get_command_dir(temp_project)
            expected = temp_project / expected_path
            assert cmd_dir == expected, f"Wrong path for {agent}"

    def test_new_generator_creates_commands(self, temp_project: Path) -> None:
        """Test new generators can create command files."""
        for agent in ["tabnine", "aider", "devin", "cody"]:
            generator = get_generator(agent)
            assert generator is not None

            path = generator.generate_command("list", "List changes", temp_project)
            assert path is not None
            assert path.exists()

            content = path.read_text(encoding="utf-8")
            assert "cc-spec list" in content
            assert "<!-- CC-SPEC:START -->" in content

    def test_all_new_generators_generate_all(self, temp_project: Path) -> None:
        """Test all new generators can generate full command set."""
        new_agents = ["tabnine", "aider", "devin", "replit",
                      "cody", "supermaven", "kilo", "auggie"]

        for agent in new_agents:
            generator = get_generator(agent)
            assert generator is not None

            paths = generator.generate_all(temp_project)
            assert len(paths) == 10, f"Expected 10 commands for {agent}"


class TestV12Features:
    """Test v1.2 specific features integration."""

    def test_version_default_is_12(self) -> None:
        """Test default version is now 1.3 (updated from 1.2)."""
        config = Config()
        assert config.version == "1.3"  # Updated: current version is 1.3

    def test_config_migration_from_v11(self) -> None:
        """Test config migration from v1.1 to v1.2 format."""
        # v1.1 format (agent field only)
        v11_data = {
            "version": "1.1",
            "agent": "cursor",
            "project_name": "old-project",
        }

        config = Config.from_dict(v11_data)

        # Should still work with agent field
        assert config.agent == "cursor"
        # get_active_agent should use agents.default or fall back
        active = config.get_active_agent()
        assert active in ["cursor", "claude"]  # Either from agents.default or agent

    def test_eleven_commands_still_available(self) -> None:
        """Test that all 11 commands are still available."""
        from cc_spec import app

        commands = [cmd.name for cmd in app.registered_commands]

        # All 11 commands
        expected = [
            "init", "specify", "clarify", "plan", "apply",
            "checklist", "archive", "quick-delta", "list", "goto", "update"
        ]

        for cmd in expected:
            assert cmd in commands, f"Command {cmd} not found"

        assert len(commands) == 11


class TestGotoExecuteWorkflow:
    """Test goto --execute workflow (v1.2)."""

    def test_execute_command_helper(self) -> None:
        """Test _execute_command helper function."""
        from cc_spec.commands.goto import _execute_command

        # Test that non-commands are skipped
        with patch("cc_spec.commands.goto.console") as mock_console:
            _execute_command("tasks.md")
            # Should print note about file
            assert mock_console.print.called

        # Test that cc-spec commands are executed
        with patch("cc_spec.commands.goto.subprocess.run") as mock_run:
            mock_run.return_value = type('obj', (object,), {'returncode': 0})()
            with patch("cc_spec.commands.goto.console"):
                _execute_command("cc-spec list")
            mock_run.assert_called_once()


class TestUpdateTemplatesWorkflow:
    """Test update --templates workflow (v1.2)."""

    def test_template_files_defined(self) -> None:
        """Test template files are defined."""
        from cc_spec.commands.update import TEMPLATE_FILES

        assert len(TEMPLATE_FILES) >= 4
        assert "spec-template.md" in TEMPLATE_FILES
        assert "plan-template.md" in TEMPLATE_FILES

    def test_templates_directory_creation(self) -> None:
        """Test templates directory is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from cc_spec.commands.update import _update_templates

            cc_spec_root = Path(tmpdir) / ".cc-spec"
            cc_spec_root.mkdir(parents=True)

            # Mock download to fail (use local fallback)
            with patch("cc_spec.commands.update.download_file", new_callable=AsyncMock) as mock_dl:
                mock_dl.return_value = False
                _update_templates(cc_spec_root, force=True)

            templates_dir = cc_spec_root / "templates"
            assert templates_dir.exists()


class TestFullV12Workflow:
    """End-to-end workflow tests for v1.2."""

    def test_multi_agent_project_setup(self) -> None:
        """Test setting up a project with multiple agents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cc_spec_root = project_root / ".cc-spec"
            cc_spec_root.mkdir(parents=True)

            # Create v1.2 config with multiple agents
            config = Config(
                version="1.2",
                agent="claude",
                agents=AgentsConfig(
                    enabled=["claude", "cursor", "gemini"],
                    default="claude",
                ),
                project_name="multi-agent-project",
                subagent=SubAgentConfig(
                    max_concurrent=10,
                    common=SubAgentProfile(
                        model="sonnet",
                        timeout=300000,
                    ),
                    profiles={
                        "quick": SubAgentProfile(model="haiku", timeout=60000),
                        "heavy": SubAgentProfile(model="opus", timeout=600000),
                    },
                ),
            )

            # Save config
            config_path = cc_spec_root / "config.yaml"
            save_config(config, config_path)

            # Generate commands for each enabled agent
            for agent in config.agents.enabled:
                generator = get_generator(agent)
                if generator:
                    paths = generator.generate_all(project_root)
                    assert len(paths) == 10, f"Expected 10 commands for {agent}"

            # Verify config can be loaded
            loaded = load_config(config_path)
            assert loaded.version == "1.2"
            assert loaded.get_active_agent() == "claude"
            assert len(loaded.agents.enabled) == 3

            # Verify profile access
            quick = loaded.subagent.get_profile("quick")
            assert quick.model == "haiku"
