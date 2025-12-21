"""Tests for command_templates module."""

from pathlib import Path

import pytest

from cc_spec.core.command_templates import (
    CommandTemplate,
    CommandTemplateContext,
)
from cc_spec.core.command_templates.base import RenderFormat


class TestCommandTemplateContext:
    """Tests for CommandTemplateContext data class."""

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        ctx = CommandTemplateContext(command_name="specify")
        assert ctx.command_name == "specify"
        assert ctx.namespace == "cc-spec"
        assert ctx.config_sources == []
        assert ctx.project_root is None
        assert ctx.extra == {}

    def test_full_command_name_with_namespace(self) -> None:
        """Test full command name with namespace."""
        ctx = CommandTemplateContext(
            command_name="specify",
            namespace="cc-spec",
        )
        assert ctx.get_full_command_name() == "cc-spec.specify"

    def test_full_command_name_without_namespace(self) -> None:
        """Test full command name without namespace."""
        ctx = CommandTemplateContext(
            command_name="specify",
            namespace="",
        )
        assert ctx.get_full_command_name() == "specify"

    def test_config_sources(self) -> None:
        """Test config_sources field."""
        ctx = CommandTemplateContext(
            command_name="specify",
            config_sources=["CLAUDE.md", "config.yaml"],
        )
        assert "CLAUDE.md" in ctx.config_sources
        assert "config.yaml" in ctx.config_sources
        assert len(ctx.config_sources) == 2

    def test_project_root(self) -> None:
        """Test project_root field."""
        root = Path("/tmp/project")
        ctx = CommandTemplateContext(
            command_name="specify",
            project_root=root,
        )
        assert ctx.project_root == root

    def test_extra_data(self) -> None:
        """Test extra data field."""
        ctx = CommandTemplateContext(
            command_name="specify",
            extra={"custom_key": "custom_value"},
        )
        assert ctx.extra["custom_key"] == "custom_value"


class ConcreteTemplate(CommandTemplate):
    """Concrete implementation for testing."""

    def get_outline(self, ctx: CommandTemplateContext) -> str:
        return f"This is the outline for {ctx.get_full_command_name()}."

    def get_execution_steps(self, ctx: CommandTemplateContext) -> list[str]:
        return [
            "Parse user arguments",
            f"Run `cc-spec {ctx.command_name}`",
            "Display results",
        ]

    def get_validation_checklist(self, ctx: CommandTemplateContext) -> list[str]:
        return [
            "Command executed successfully",
            "Output is valid",
        ]


class ConcreteTemplateWithGuidelines(ConcreteTemplate):
    """Concrete implementation with guidelines for testing."""

    def get_guidelines(self, ctx: CommandTemplateContext) -> str:
        return "Follow best practices.\nKeep it simple."


class TestCommandTemplate:
    """Tests for CommandTemplate abstract base class."""

    def test_cannot_instantiate_abstract_class(self) -> None:
        """Test that abstract class cannot be instantiated."""
        with pytest.raises(TypeError):
            CommandTemplate()  # type: ignore[abstract]

    def test_concrete_implementation(self) -> None:
        """Test that concrete implementation works."""
        template = ConcreteTemplate()
        ctx = CommandTemplateContext(command_name="specify")

        outline = template.get_outline(ctx)
        assert "cc-spec.specify" in outline

        steps = template.get_execution_steps(ctx)
        assert len(steps) == 3
        assert "cc-spec specify" in steps[1]

        checklist = template.get_validation_checklist(ctx)
        assert len(checklist) == 2

    def test_default_guidelines_empty(self) -> None:
        """Test that default guidelines return empty string."""
        template = ConcreteTemplate()
        ctx = CommandTemplateContext(command_name="specify")
        assert template.get_guidelines(ctx) == ""

    def test_custom_guidelines(self) -> None:
        """Test custom guidelines implementation."""
        template = ConcreteTemplateWithGuidelines()
        ctx = CommandTemplateContext(command_name="specify")
        guidelines = template.get_guidelines(ctx)
        assert "best practices" in guidelines


class TestRenderMarkdown:
    """Tests for markdown rendering."""

    def test_render_markdown_basic(self) -> None:
        """Test basic markdown rendering."""
        template = ConcreteTemplate()
        ctx = CommandTemplateContext(command_name="specify")

        content = template.render(ctx, fmt=RenderFormat.MARKDOWN)

        # Check sections exist
        assert "## User Input" in content
        assert "## Outline" in content
        assert "## Execution Steps" in content
        assert "## Validation Checklist" in content
        assert "## Command Reference" in content

        # Check content
        assert "$ARGUMENTS" in content
        assert "cc-spec.specify" in content
        assert "1. Parse user arguments" in content
        assert "- [ ] Command executed successfully" in content
        assert "cc-spec specify --help" in content

    def test_render_markdown_with_guidelines(self) -> None:
        """Test markdown rendering with guidelines."""
        template = ConcreteTemplateWithGuidelines()
        ctx = CommandTemplateContext(command_name="clarify")

        content = template.render(ctx, fmt=RenderFormat.MARKDOWN)

        assert "## Guidelines" in content
        assert "best practices" in content

    def test_render_default_format_is_markdown(self) -> None:
        """Test that default render format is markdown."""
        template = ConcreteTemplate()
        ctx = CommandTemplateContext(command_name="specify")

        # Call without format argument
        content = template.render(ctx)

        # Should be markdown format
        assert "## User Input" in content
        assert "[prompt]" not in content


class TestRenderToml:
    """Tests for TOML rendering."""

    def test_render_toml_basic(self) -> None:
        """Test basic TOML rendering."""
        template = ConcreteTemplate()
        ctx = CommandTemplateContext(command_name="specify")

        content = template.render(ctx, fmt=RenderFormat.TOML)

        # Check TOML structure
        assert "[prompt]" in content
        assert 'content = """' in content

        # Check markdown content is embedded
        assert "## User Input" in content
        assert "cc-spec.specify" in content

    def test_render_toml_escapes_triple_quotes(self) -> None:
        """Test that triple quotes are escaped in TOML output."""
        template = ConcreteTemplate()
        ctx = CommandTemplateContext(command_name="specify")

        content = template.render(ctx, fmt=RenderFormat.TOML)

        # The content should be valid TOML with proper escaping
        # Count opening and closing triple quotes
        opening_quotes = content.count('content = """')
        assert opening_quotes == 1


class TestRenderFormat:
    """Tests for RenderFormat enum."""

    def test_markdown_value(self) -> None:
        """Test markdown format value."""
        assert RenderFormat.MARKDOWN.value == "markdown"

    def test_toml_value(self) -> None:
        """Test TOML format value."""
        assert RenderFormat.TOML.value == "toml"
