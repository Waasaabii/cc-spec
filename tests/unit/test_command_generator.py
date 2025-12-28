"""Tests for command_generator module (v0.1.6)."""

import tempfile
from pathlib import Path

from cc_spec.core.command_generator import (
    CC_SPEC_COMMANDS,
    COMMAND_GENERATORS,
    MANAGED_END,
    MANAGED_START,
    ClaudeCommandGenerator,
    get_available_agents,
    get_generator,
)


class TestConstants:
    def test_cc_spec_commands_count(self) -> None:
        assert len(CC_SPEC_COMMANDS) == 14
        command_names = [name for name, _ in CC_SPEC_COMMANDS]
        assert "init" in command_names
        assert "init-index" in command_names
        assert "update-index" in command_names
        assert "check-index" in command_names
        assert "specify" in command_names
        assert "clarify" in command_names
        assert "plan" in command_names
        assert "apply" in command_names
        assert "accept" in command_names
        assert "archive" in command_names
        assert "quick-delta" in command_names
        assert "list" in command_names
        assert "goto" in command_names
        assert "update" in command_names

    def test_command_generators_count(self) -> None:
        assert len(COMMAND_GENERATORS) == 1
        assert "claude" in COMMAND_GENERATORS

    def test_managed_block_markers(self) -> None:
        assert MANAGED_START == "<!-- CC-SPEC:START -->"
        assert MANAGED_END == "<!-- CC-SPEC:END -->"


class TestGetGenerator:
    def test_get_generator_claude(self) -> None:
        generator = get_generator("claude")
        assert isinstance(generator, ClaudeCommandGenerator)

    def test_get_generator_case_insensitive(self) -> None:
        generator = get_generator("CLAUDE")
        assert isinstance(generator, ClaudeCommandGenerator)

    def test_get_generator_unknown(self) -> None:
        assert get_generator("unknown-agent") is None


class TestGetAvailableAgents:
    def test_get_available_agents(self) -> None:
        assert get_available_agents() == ["claude"]


class TestClaudeCommandGenerator:
    def test_command_dir_path(self) -> None:
        generator = ClaudeCommandGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cmd_dir = generator.get_command_dir(project_root)
            assert cmd_dir == project_root / ".claude" / "commands" / "cc-spec"

    def test_generate_command(self) -> None:
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

    def test_generate_all_creates_all_commands(self) -> None:
        generator = ClaudeCommandGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            paths = generator.generate_all(project_root)
            assert len(paths) == 14

            cmd_dir = generator.get_command_dir(project_root)
            for cmd_name, _ in CC_SPEC_COMMANDS:
                assert (cmd_dir / f"{cmd_name}.md").exists()

    def test_update_command_preserves_user_content(self) -> None:
        generator = ClaudeCommandGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            path = generator.generate_command("specify", "Old desc", project_root)
            assert path is not None

            content = path.read_text(encoding="utf-8")
            new_content = content.replace(
                "---\n",
                "---\n\n## User Custom Section\nMy custom content\n\n",
                1,
            )
            path.write_text(new_content, encoding="utf-8")

            generator.update_command("specify", "New desc", project_root)

            updated = path.read_text(encoding="utf-8")
            assert "## User Custom Section" in updated
            assert "My custom content" in updated
