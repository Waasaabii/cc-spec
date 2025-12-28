"""Integration tests for legacy features (kept minimal)."""

import tempfile
from pathlib import Path

import pytest
import yaml

from cc_spec.core.config import Config, SubAgentConfig, SubAgentProfile, load_config, save_config
from cc_spec.core.id_manager import IDManager, IDType
from cc_spec.core.command_generator import (
    ClaudeCommandGenerator,
    get_generator,
    get_available_agents,
)


class TestIDWorkflow:
    """Test ID creation and resolution workflow."""

    @pytest.fixture
    def temp_cc_spec(self) -> Path:
        """Create a temporary .cc-spec directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cc_spec_root = Path(tmpdir) / ".cc-spec"
            cc_spec_root.mkdir(parents=True)
            yield cc_spec_root

    def test_id_workflow_create_list_resolve(self, temp_cc_spec: Path) -> None:
        """Test full ID workflow: create → list → resolve."""
        manager = IDManager(temp_cc_spec)

        # Create changes
        change1_path = temp_cc_spec / "changes" / "feature-a"
        change1_path.mkdir(parents=True)
        change1_id = manager.register_change("feature-a", change1_path)

        change2_path = temp_cc_spec / "changes" / "feature-b"
        change2_path.mkdir(parents=True)
        change2_id = manager.register_change("feature-b", change2_path)

        # List changes
        changes = manager.list_changes()
        assert len(changes) == 2
        assert change1_id in changes
        assert change2_id in changes

        # Resolve by ID
        resolved1 = manager.resolve_path(change1_id)
        assert resolved1 is not None
        assert resolved1.name == "feature-a"

        # Resolve by name
        parsed = manager.parse_id("feature-a")
        assert parsed.type == IDType.CHANGE
        assert parsed.change_id == change1_id

    def test_task_id_parsing(self, temp_cc_spec: Path) -> None:
        """Test task ID format parsing."""
        manager = IDManager(temp_cc_spec)

        # Register a change first
        change_path = temp_cc_spec / "changes" / "my-change"
        change_path.mkdir(parents=True)
        change_id = manager.register_change("my-change", change_path)

        # Parse task ID
        task_full_id = f"{change_id}:02-MODEL"
        parsed = manager.parse_id(task_full_id)

        assert parsed.type == IDType.TASK
        assert parsed.change_id == change_id
        assert parsed.task_id == "02-MODEL"
        assert parsed.full_id == task_full_id


class TestProfileWorkflow:
    """Test SubAgent profile configuration workflow."""

    def test_profile_inheritance(self) -> None:
        """Test profile inherits from common config."""
        config = SubAgentConfig(
            max_concurrent=5,
            common=SubAgentProfile(
                model="sonnet[1m]",
                timeout=300000,
                tools="Read,Write,Edit",
            ),
            profiles={
                "quick": SubAgentProfile(
                    model="haiku",
                    timeout=60000,
                ),
                "heavy": SubAgentProfile(
                    model="opus",
                    timeout=600000,
                ),
            },
        )

        # Default profile returns common
        default_profile = config.get_profile(None)
        assert default_profile.model == "sonnet[1m]"
        assert default_profile.tools == "Read,Write,Edit"

        # Quick profile
        quick_profile = config.get_profile("quick")
        assert quick_profile.model == "haiku"
        assert quick_profile.timeout == 60000
        assert quick_profile.tools == "Read,Write,Edit"  # Inherited

        # Heavy profile
        heavy_profile = config.get_profile("heavy")
        assert heavy_profile.model == "opus"
        assert heavy_profile.timeout == 600000

        # Unknown profile returns common
        unknown_profile = config.get_profile("unknown")
        assert unknown_profile.model == "sonnet[1m]"

    def test_config_serialization_with_profiles(self) -> None:
        """Test config with profiles serializes correctly."""
        config = Config(
            version="1.1",
            agent="claude",
            project_name="test-project",
            subagent=SubAgentConfig(
                max_concurrent=10,
                common=SubAgentProfile(
                    model="sonnet",
                    timeout=300000,
                ),
                profiles={
                    "quick": SubAgentProfile(model="haiku", timeout=60000),
                },
            ),
        )

        # Serialize
        data = config.to_dict()

        assert data["version"] == "1.1"
        assert "subagent" in data
        assert "common" in data["subagent"]
        assert "profiles" in data["subagent"]
        assert "quick" in data["subagent"]["profiles"]

        # Deserialize
        restored = Config.from_dict(data)

        assert restored.version == "1.1"
        assert restored.subagent.max_concurrent == 10
        assert "quick" in restored.subagent.profiles


class TestCommandGeneratorWorkflow:
    """Test slash command generation workflow."""

    @pytest.fixture
    def temp_project(self) -> Path:
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_claude_generator(self, temp_project: Path) -> None:
        """Test Claude command generator."""
        generator = ClaudeCommandGenerator()

        # Generate a command
        path = generator.generate_command("list", "List changes", temp_project)

        assert path is not None
        assert path.exists()
        assert path.suffix == ".md"
        assert "cc-spec" in str(path)

        # Check content
        content = path.read_text(encoding="utf-8")
        assert "cc-spec list" in content
        assert "<!-- CC-SPEC:START -->" in content
        assert "<!-- CC-SPEC:END -->" in content

    def test_generate_all_commands(self, temp_project: Path) -> None:
        """Test generating all commands for an agent."""
        generator = ClaudeCommandGenerator()

        paths = generator.generate_all(temp_project)

        # Should generate all cc-spec commands
        assert len(paths) == 14

        # Check some specific commands exist
        cmd_names = [p.stem for p in paths]
        assert "init" in cmd_names
        assert "specify" in cmd_names
        assert "list" in cmd_names
        assert "goto" in cmd_names
        assert "update" in cmd_names

    def test_get_generator(self) -> None:
        """Test getting generator by agent name."""
        claude_gen = get_generator("claude")
        assert claude_gen is not None
        assert isinstance(claude_gen, ClaudeCommandGenerator)

        assert get_generator("gemini") is None

        unknown_gen = get_generator("unknown-agent")
        assert unknown_gen is None

    def test_available_agents(self) -> None:
        """Test getting list of available agents."""
        agents = get_available_agents()

        assert agents == ["claude"]

    def test_update_preserves_user_content(self, temp_project: Path) -> None:
        """Test that update preserves user-added content."""
        generator = ClaudeCommandGenerator()

        # Generate initial command
        path = generator.generate_command("list", "List changes", temp_project)

        # Add user content
        content = path.read_text(encoding="utf-8")
        user_content = "\n## My Custom Section\n\nThis is my custom content.\n"
        modified = content.replace(
            "---\n",
            "---\nmy_custom_field: true\n",
            1,
        ) + user_content
        path.write_text(modified, encoding="utf-8")

        # Update command
        updated_path = generator.update_command("list", "List changes v2", temp_project)

        assert updated_path is not None

        # Check user content preserved
        final_content = updated_path.read_text(encoding="utf-8")
        assert "my_custom_field: true" in final_content
        assert "My Custom Section" in final_content
        assert "This is my custom content" in final_content


class TestV11Features:
    """Test legacy features."""

    def test_version_in_config(self) -> None:
        """Test config version is set correctly."""
        config = Config(
            version="1.1",
            agent="claude",
        )

        data = config.to_dict()
        assert data["version"] == "1.1"

    def test_eleven_commands_available(self) -> None:
        """Test CLI commands are registered."""
        from cc_spec import app

        commands = [cmd.name for cmd in app.registered_commands]
        groups = [g.name for g in app.registered_groups]

        # Core workflow commands
        assert "init" in commands
        assert "init-index" in commands
        assert "update-index" in commands
        assert "check-index" in commands
        assert "specify" in commands
        assert "clarify" in commands
        assert "plan" in commands
        assert "apply" in commands
        assert "accept" in commands
        assert "archive" in commands
        assert "quick-delta" in commands
        assert "list" in commands
        assert "goto" in commands
        assert "update" in commands
        assert "chat" in commands
        assert "context" in commands
        assert groups == []

        assert len(commands) >= 16
