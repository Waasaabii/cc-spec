"""Tests for command_generator module (v1.2).

Tests cover all 17+ command generators including the 8 new ones added in v1.2.
"""

import tempfile
from pathlib import Path

import pytest

from cc_spec.core.command_generator import (
    CC_SPEC_COMMANDS,
    COMMAND_GENERATORS,
    MANAGED_END,
    MANAGED_START,
    AiderCommandGenerator,
    AmazonQCommandGenerator,
    AuggieCommandGenerator,
    ClaudeCommandGenerator,
    CodexCommandGenerator,
    CodeiumCommandGenerator,
    CodyCommandGenerator,
    CommandGenerator,
    ContinueCommandGenerator,
    CopilotCommandGenerator,
    CursorCommandGenerator,
    DevinCommandGenerator,
    GeminiCommandGenerator,
    KiloCodeCommandGenerator,
    QwenCommandGenerator,
    ReplitCommandGenerator,
    SupermavenCommandGenerator,
    TabnineCommandGenerator,
    WindsurfCommandGenerator,
    get_available_agents,
    get_generator,
)


class TestConstants:
    """Tests for module constants."""

    def test_cc_spec_commands_count(self) -> None:
        """Test that CC_SPEC_COMMANDS has 10 commands."""
        assert len(CC_SPEC_COMMANDS) == 10
        command_names = [name for name, _ in CC_SPEC_COMMANDS]
        assert "specify" in command_names
        assert "clarify" in command_names
        assert "plan" in command_names
        assert "apply" in command_names
        assert "checklist" in command_names
        assert "archive" in command_names
        assert "quick-delta" in command_names
        assert "list" in command_names
        assert "goto" in command_names
        assert "update" in command_names

    def test_command_generators_count(self) -> None:
        """Test that we have 18 command generators (10 original + 8 new)."""
        assert len(COMMAND_GENERATORS) == 18

    def test_managed_block_markers(self) -> None:
        """Test managed block markers are correct."""
        assert MANAGED_START == "<!-- CC-SPEC:START -->"
        assert MANAGED_END == "<!-- CC-SPEC:END -->"


class TestGetGenerator:
    """Tests for get_generator function."""

    def test_get_generator_claude(self) -> None:
        """Test getting Claude generator."""
        generator = get_generator("claude")
        assert generator is not None
        assert isinstance(generator, ClaudeCommandGenerator)

    def test_get_generator_case_insensitive(self) -> None:
        """Test that generator lookup is case-insensitive."""
        generator = get_generator("CLAUDE")
        assert generator is not None
        assert isinstance(generator, ClaudeCommandGenerator)

    def test_get_generator_unknown(self) -> None:
        """Test getting unknown generator returns None."""
        generator = get_generator("unknown-agent")
        assert generator is None


class TestGetAvailableAgents:
    """Tests for get_available_agents function."""

    def test_get_available_agents_count(self) -> None:
        """Test that 18 agents are available."""
        agents = get_available_agents()
        assert len(agents) == 18

    def test_get_available_agents_original(self) -> None:
        """Test original agents are in list."""
        agents = get_available_agents()
        original = ["claude", "cursor", "gemini", "copilot", "amazonq",
                    "windsurf", "qwen", "codeium", "continue", "codex"]
        for agent in original:
            assert agent in agents

    def test_get_available_agents_new_v12(self) -> None:
        """Test 8 new v1.2 agents are in list."""
        agents = get_available_agents()
        new_agents = ["tabnine", "aider", "devin", "replit",
                      "cody", "supermaven", "kilo", "auggie"]
        for agent in new_agents:
            assert agent in agents


class TestClaudeCommandGenerator:
    """Tests for Claude command generator."""

    def test_command_dir_path(self) -> None:
        """Test Claude command directory path."""
        generator = ClaudeCommandGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cmd_dir = generator.get_command_dir(project_root)
            assert cmd_dir == project_root / ".claude" / "commands" / "cc-spec"

    def test_file_format(self) -> None:
        """Test Claude uses markdown format."""
        generator = ClaudeCommandGenerator()
        assert generator.file_format == "markdown"

    def test_generate_command(self) -> None:
        """Test generating a command file."""
        generator = ClaudeCommandGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            path = generator.generate_command("specify", "Test desc", project_root)

            assert path is not None
            assert path.exists()
            assert path.name == "specify.md"

            content = path.read_text(encoding="utf-8")
            assert "description: Test desc" in content
            assert MANAGED_START in content
            assert MANAGED_END in content
            assert "cc-spec specify" in content


class TestGeminiCommandGenerator:
    """Tests for Gemini command generator (uses TOML)."""

    def test_command_dir_path(self) -> None:
        """Test Gemini command directory path."""
        generator = GeminiCommandGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cmd_dir = generator.get_command_dir(project_root)
            assert cmd_dir == project_root / ".gemini" / "commands" / "cc-spec"

    def test_file_format(self) -> None:
        """Test Gemini uses TOML format."""
        generator = GeminiCommandGenerator()
        assert generator.file_format == "toml"

    def test_generate_command_toml(self) -> None:
        """Test generating a TOML command file."""
        generator = GeminiCommandGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            path = generator.generate_command("clarify", "Review tasks", project_root)

            assert path is not None
            assert path.exists()
            assert path.name == "clarify.toml"

            content = path.read_text(encoding="utf-8")
            assert 'description = "Review tasks"' in content
            assert MANAGED_START in content
            assert MANAGED_END in content


class TestCodexCommandGenerator:
    """Tests for Codex command generator."""

    def test_command_dir_path(self, monkeypatch) -> None:
        """Test Codex command directory path (global, via CODEX_HOME)."""
        generator = CodexCommandGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            codex_home = project_root / ".codex-home"
            monkeypatch.setenv("CODEX_HOME", str(codex_home))
            cmd_dir = generator.get_command_dir(project_root)
            assert cmd_dir == codex_home / "prompts"


class TestCursorCommandGenerator:
    """Tests for Cursor command generator."""

    def test_command_dir_path(self) -> None:
        """Test Cursor command directory path (no namespace)."""
        generator = CursorCommandGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cmd_dir = generator.get_command_dir(project_root)
            # Cursor has no namespace
            assert cmd_dir == project_root / ".cursor" / "commands"


class TestNewV12Generators:
    """Tests for 8 new v1.2 command generators."""

    def test_tabnine_generator(self) -> None:
        """Test Tabnine command generator."""
        generator = TabnineCommandGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cmd_dir = generator.get_command_dir(project_root)
            assert cmd_dir == project_root / ".tabnine" / "commands" / "cc-spec"
            assert generator.file_format == "markdown"

    def test_aider_generator(self) -> None:
        """Test Aider command generator."""
        generator = AiderCommandGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cmd_dir = generator.get_command_dir(project_root)
            assert cmd_dir == project_root / ".aider" / "commands"
            assert generator.file_format == "markdown"

    def test_devin_generator(self) -> None:
        """Test Devin command generator."""
        generator = DevinCommandGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cmd_dir = generator.get_command_dir(project_root)
            assert cmd_dir == project_root / ".devin" / "commands" / "cc-spec"

    def test_replit_generator(self) -> None:
        """Test Replit command generator."""
        generator = ReplitCommandGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cmd_dir = generator.get_command_dir(project_root)
            assert cmd_dir == project_root / ".replit" / "commands"

    def test_cody_generator(self) -> None:
        """Test Sourcegraph Cody command generator."""
        generator = CodyCommandGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cmd_dir = generator.get_command_dir(project_root)
            assert cmd_dir == project_root / ".cody" / "commands" / "cc-spec"

    def test_supermaven_generator(self) -> None:
        """Test Supermaven command generator."""
        generator = SupermavenCommandGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cmd_dir = generator.get_command_dir(project_root)
            assert cmd_dir == project_root / ".supermaven" / "commands"

    def test_kilo_generator(self) -> None:
        """Test Kilo Code command generator."""
        generator = KiloCodeCommandGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cmd_dir = generator.get_command_dir(project_root)
            assert cmd_dir == project_root / ".kilo" / "commands"

    def test_auggie_generator(self) -> None:
        """Test Auggie command generator."""
        generator = AuggieCommandGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cmd_dir = generator.get_command_dir(project_root)
            assert cmd_dir == project_root / ".auggie" / "commands" / "cc-spec"


class TestGenerateAll:
    """Tests for generate_all method."""

    def test_generate_all_creates_all_commands(self) -> None:
        """Test generate_all creates all 10 command files."""
        generator = ClaudeCommandGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            paths = generator.generate_all(project_root)

            assert len(paths) == 10
            cmd_dir = generator.get_command_dir(project_root)
            assert (cmd_dir / "specify.md").exists()
            assert (cmd_dir / "clarify.md").exists()
            assert (cmd_dir / "plan.md").exists()
            assert (cmd_dir / "apply.md").exists()
            assert (cmd_dir / "checklist.md").exists()
            assert (cmd_dir / "archive.md").exists()
            assert (cmd_dir / "quick-delta.md").exists()
            assert (cmd_dir / "list.md").exists()
            assert (cmd_dir / "goto.md").exists()
            assert (cmd_dir / "update.md").exists()


class TestUpdateCommand:
    """Tests for update_command method."""

    def test_update_command_creates_if_not_exists(self) -> None:
        """Test update_command creates file if it doesn't exist."""
        generator = ClaudeCommandGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            path = generator.update_command("specify", "Create spec", project_root)

            assert path is not None
            assert path.exists()

    def test_update_command_preserves_user_content(self) -> None:
        """Test update_command preserves content outside managed block."""
        generator = ClaudeCommandGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # First create the command
            path = generator.generate_command("specify", "Old desc", project_root)

            # Add user content before managed block
            content = path.read_text(encoding="utf-8")
            new_content = content.replace(
                "---\n",
                "---\n\n## User Custom Section\nMy custom content\n\n",
                1
            )
            path.write_text(new_content, encoding="utf-8")

            # Update the command
            generator.update_command("specify", "New desc", project_root)

            # Check user content is preserved
            updated = path.read_text(encoding="utf-8")
            assert "## User Custom Section" in updated
            assert "My custom content" in updated

    def test_update_command_skips_without_managed_block(self) -> None:
        """Test update_command skips files without managed block."""
        generator = ClaudeCommandGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create command dir and write a file without managed block
            cmd_dir = generator.get_command_dir(project_root)
            cmd_dir.mkdir(parents=True)
            file_path = cmd_dir / "specify.md"
            file_path.write_text("User file without managed block", encoding="utf-8")

            # Update should return None (no update)
            result = generator.update_command("specify", "New desc", project_root)

            assert result is None

            # File should be unchanged
            content = file_path.read_text(encoding="utf-8")
            assert content == "User file without managed block"
