"""Unit tests for template processing module."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cc_spec.core.templates import (
    TemplateError,
    copy_template,
    download_templates,
    get_template_path,
    get_template_source,
    list_templates,
    render_template,
    resolve_template_ref,
)


class TestTemplateSource:
    """Tests for template source configuration."""

    def test_default_source(self):
        """Test default template source."""
        repo, branch = get_template_source()
        assert repo == "owner/cc-spec-templates"
        assert branch == "main"

    def test_custom_source_from_env(self):
        """Test custom template source from environment."""
        with patch.dict(
            "os.environ",
            {"CC_SPEC_TEMPLATE_URL": "https://github.com/user/custom-templates"},
        ):
            repo, branch = get_template_source()
            assert repo == "user/custom-templates"
            assert branch == "main"

    def test_custom_source_with_branch(self):
        """Test custom template source with branch."""
        with patch.dict(
            "os.environ",
            {
                "CC_SPEC_TEMPLATE_URL": "https://github.com/user/custom-templates/tree/develop"
            },
        ):
            repo, branch = get_template_source()
            assert repo == "user/custom-templates"
            assert branch == "develop"


class TestRenderTemplate:
    """Tests for template rendering."""

    def test_simple_variable_substitution(self):
        """Test simple variable substitution."""
        template = "Project: {project_name}, Change: {change_name}"
        variables = {"project_name": "test-project", "change_name": "add-feature"}
        result = render_template(template, variables)
        assert result == "Project: test-project, Change: add-feature"

    def test_uppercase_variable_substitution(self):
        """Test uppercase variable format ($ARGUMENTS)."""
        template = "User input: $ARGUMENTS"
        variables = {"arguments": "test input"}
        result = render_template(template, variables)
        assert result == "User input: test input"

    def test_auto_date_injection(self):
        """Test automatic date injection."""
        template = "Created: {date}"
        variables = {}
        result = render_template(template, variables)
        assert "Created:" in result
        assert "{date}" not in result

    def test_auto_timestamp_injection(self):
        """Test automatic timestamp injection."""
        template = "Timestamp: {timestamp}"
        variables = {}
        result = render_template(template, variables)
        assert "Timestamp:" in result
        assert "{timestamp}" not in result

    def test_mixed_variables(self):
        """Test mixed variable formats."""
        template = "{name} says: $MESSAGE on {date}"
        variables = {"name": "Alice", "message": "Hello"}
        result = render_template(template, variables)
        assert "Alice says: Hello on" in result


class TestCopyTemplate:
    """Tests for template copying."""

    def test_copy_template_basic(self, tmp_path):
        """Test basic template copying."""
        # Create a source template
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        template_path = source_dir / "spec-template.md"
        template_path.write_text("# Spec: {project_name}")

        # Copy to destination
        dest_path = tmp_path / "dest" / "spec.md"
        result = copy_template(
            "spec-template.md",
            dest_path,
            variables={"project_name": "my-project"},
            source_dir=source_dir,
        )

        assert result == dest_path
        assert dest_path.exists()
        assert dest_path.read_text() == "# Spec: my-project"

    def test_copy_template_not_found(self, tmp_path):
        """Test copying non-existent template."""
        with pytest.raises(TemplateError, match="未找到模板"):
            copy_template("nonexistent.md", tmp_path / "dest.md", source_dir=tmp_path)

    def test_copy_template_creates_parent_dirs(self, tmp_path):
        """Test that parent directories are created."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        template_path = source_dir / "template.md"
        template_path.write_text("Content")

        # Destination has nested directories
        dest_path = tmp_path / "a" / "b" / "c" / "dest.md"
        copy_template("template.md", dest_path, source_dir=source_dir)

        assert dest_path.exists()
        assert dest_path.read_text() == "Content"


class TestListTemplates:
    """Tests for listing templates."""

    def test_list_templates_empty(self, tmp_path):
        """Test listing templates in empty directory."""
        templates = list_templates(tmp_path)
        assert templates == []

    def test_list_templates_with_files(self, tmp_path):
        """Test listing available templates."""
        # Create some template files
        (tmp_path / "spec-template.md").write_text("content")
        (tmp_path / "plan-template.md").write_text("content")

        templates = list_templates(tmp_path)
        assert "spec-template.md" in templates
        assert "plan-template.md" in templates
        assert len(templates) == 2

    def test_list_templates_partial(self, tmp_path):
        """Test listing with only some templates present."""
        (tmp_path / "spec-template.md").write_text("content")

        templates = list_templates(tmp_path)
        assert "spec-template.md" in templates
        assert "plan-template.md" not in templates


class TestGetTemplatePath:
    """Tests for getting template paths."""

    def test_get_template_path_exists(self, tmp_path):
        """Test getting path to existing template."""
        template_file = tmp_path / "spec-template.md"
        template_file.write_text("content")

        path = get_template_path("spec-template.md", tmp_path)
        assert path == template_file

    def test_get_template_path_not_found(self, tmp_path):
        """Test getting path to non-existent template."""
        with pytest.raises(TemplateError, match="未找到模板"):
            get_template_path("nonexistent.md", tmp_path)


class TestDownloadTemplates:
    """Tests for downloading templates."""

    @pytest.mark.asyncio
    async def test_download_templates_success(self, tmp_path):
        """Test successful template download."""
        with patch("cc_spec.core.templates.download_file") as mock_download:
            # Mock successful downloads
            mock_download.return_value = True

            result = await download_templates(tmp_path)
            assert result is True

    @pytest.mark.asyncio
    async def test_download_templates_fallback_to_cache(self, tmp_path):
        """Test fallback to cached templates."""
        # Create cached templates
        for template in ["spec-template.md", "plan-template.md", "tasks-template.md", "checklist-template.md"]:
            (tmp_path / template).write_text("cached content")

        with patch("cc_spec.core.templates.download_file") as mock_download:
            # Mock failed downloads
            mock_download.return_value = False

            result = await download_templates(tmp_path, use_cache=True)
            assert result is True

    @pytest.mark.asyncio
    async def test_download_templates_fallback_to_bundled(self, tmp_path):
        """Test fallback to bundled templates."""
        with patch("cc_spec.core.templates.download_file") as mock_download:
            mock_download.return_value = False

            with patch("cc_spec.core.templates._has_cached_templates") as mock_cache:
                mock_cache.return_value = False

                bundled_dir = tmp_path / "bundled"
                bundled_dir.mkdir()
                for template in ["spec-template.md", "plan-template.md", "tasks-template.md", "checklist-template.md"]:
                    (bundled_dir / template).write_text("bundled content")

                with patch("pathlib.Path.exists") as mock_exists:
                    mock_exists.return_value = True
                    with patch(
                        "cc_spec.core.templates._copy_bundled_templates"
                    ) as mock_copy:
                        result = await download_templates(tmp_path, use_cache=True)
                        assert result is True
                        mock_copy.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_templates_all_fail(self, tmp_path):
        """Test when all download methods fail."""
        with patch("cc_spec.core.templates.download_file") as mock_download:
            mock_download.return_value = False

            with patch("cc_spec.core.templates._has_cached_templates") as mock_cache:
                mock_cache.return_value = False

                with patch("pathlib.Path.exists") as mock_exists:
                    mock_exists.return_value = False

                    with pytest.raises(TemplateError, match="模板下载失败"):
                        await download_templates(tmp_path, use_cache=True)


class TestResolveTemplateRef:
    """Tests for resolve_template_ref function."""

    def test_resolve_template_ref_with_valid_reference(self, tmp_path):
        """Test resolving a valid template reference."""
        # 创建 .cc-spec/templates/checklists 目录结构
        cc_spec_dir = tmp_path / ".cc-spec"
        templates_dir = cc_spec_dir / "templates" / "checklists"
        templates_dir.mkdir(parents=True)

        # 创建测试模板文件
        template_content = "# Setup Checklist\n\n- [ ] Item 1\n- [ ] Item 2"
        template_path = templates_dir / "setup-checklist.md"
        template_path.write_text(template_content, encoding="utf-8")

        # 测试引用解析
        result = resolve_template_ref("$templates/checklists/setup-checklist", cc_spec_dir)
        assert result == template_content

    def test_resolve_template_ref_with_md_extension(self, tmp_path):
        """Test resolving reference that already has .md extension."""
        cc_spec_dir = tmp_path / ".cc-spec"
        templates_dir = cc_spec_dir / "templates"
        templates_dir.mkdir(parents=True)

        template_content = "# Feature Checklist"
        template_path = templates_dir / "feature-checklist.md"
        template_path.write_text(template_content, encoding="utf-8")

        # 引用中已包含 .md 扩展名
        result = resolve_template_ref("$templates/feature-checklist.md", cc_spec_dir)
        assert result == template_content

    def test_resolve_template_ref_without_md_extension(self, tmp_path):
        """Test resolving reference without .md extension (auto-append)."""
        cc_spec_dir = tmp_path / ".cc-spec"
        templates_dir = cc_spec_dir / "templates"
        templates_dir.mkdir(parents=True)

        template_content = "# Test Checklist"
        template_path = templates_dir / "test-checklist.md"
        template_path.write_text(template_content, encoding="utf-8")

        # 引用中不包含 .md 扩展名，应自动添加
        result = resolve_template_ref("$templates/test-checklist", cc_spec_dir)
        assert result == template_content

    def test_resolve_template_ref_not_found(self, tmp_path):
        """Test resolving a non-existent template reference."""
        cc_spec_dir = tmp_path / ".cc-spec"
        templates_dir = cc_spec_dir / "templates"
        templates_dir.mkdir(parents=True)

        # 引用不存在的模板
        with pytest.raises(TemplateError, match="未找到公共模板"):
            resolve_template_ref("$templates/nonexistent-checklist", cc_spec_dir)

    def test_resolve_template_ref_non_template_string(self, tmp_path):
        """Test that non-template strings are returned as-is."""
        cc_spec_dir = tmp_path / ".cc-spec"

        # 普通字符串应原样返回
        plain_text = "This is just a plain string"
        result = resolve_template_ref(plain_text, cc_spec_dir)
        assert result == plain_text

    def test_resolve_template_ref_inline_content(self, tmp_path):
        """Test that inline content (not starting with $templates/) is returned unchanged."""
        cc_spec_dir = tmp_path / ".cc-spec"

        inline_content = "# Inline Checklist\n\n- [ ] Task 1\n- [ ] Task 2"
        result = resolve_template_ref(inline_content, cc_spec_dir)
        assert result == inline_content

    def test_resolve_template_ref_read_error(self, tmp_path):
        """Test handling of file read errors."""
        cc_spec_dir = tmp_path / ".cc-spec"
        templates_dir = cc_spec_dir / "templates"
        templates_dir.mkdir(parents=True)

        # 创建一个文件但模拟读取错误
        template_path = templates_dir / "error-checklist.md"
        template_path.write_text("content", encoding="utf-8")

        with patch("pathlib.Path.read_text") as mock_read:
            mock_read.side_effect = IOError("Read error")

            with pytest.raises(TemplateError, match="读取公共模板失败"):
                resolve_template_ref("$templates/error-checklist", cc_spec_dir)

    def test_resolve_template_ref_nested_path(self, tmp_path):
        """Test resolving templates in nested directories."""
        cc_spec_dir = tmp_path / ".cc-spec"
        templates_dir = cc_spec_dir / "templates" / "nested" / "folder"
        templates_dir.mkdir(parents=True)

        template_content = "# Nested Template"
        template_path = templates_dir / "nested-checklist.md"
        template_path.write_text(template_content, encoding="utf-8")

        result = resolve_template_ref("$templates/nested/folder/nested-checklist", cc_spec_dir)
        assert result == template_content

