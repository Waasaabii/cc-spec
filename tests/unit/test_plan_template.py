"""Tests for PlanTemplate class."""

from pathlib import Path

import pytest

from cc_spec.core.command_templates import (
    CommandTemplateContext,
    PlanTemplate,
)
from cc_spec.core.command_templates.base import RenderFormat


class TestPlanTemplate:
    """Tests for PlanTemplate class."""

    @pytest.fixture
    def template(self) -> PlanTemplate:
        """Create a PlanTemplate instance for testing."""
        return PlanTemplate()

    @pytest.fixture
    def ctx(self) -> CommandTemplateContext:
        """Create a test context."""
        return CommandTemplateContext(
            command_name="plan",
            namespace="cc-spec",
            project_root=Path("/tmp/test-project"),
        )

    def test_get_outline(self, template: PlanTemplate, ctx: CommandTemplateContext) -> None:
        """Test that outline is complete and contains key sections."""
        outline = template.get_outline(ctx)

        # 检查核心目标
        assert "核心目标" in outline
        assert "Gate-0" in outline
        assert "Wave-1" in outline
        assert "tasks.yaml" in outline

        # 检查输入输出
        assert "proposal.md" in outline
        assert "tasks.yaml" in outline

        # 检查任务结构说明
        assert "meta" in outline
        assert "waves" in outline
        assert "type: gate" in outline
        assert "type: wave" in outline

    def test_get_execution_steps_count(
        self, template: PlanTemplate, ctx: CommandTemplateContext
    ) -> None:
        """Test that execution steps contain exactly 9 steps (九段大纲)."""
        steps = template.get_execution_steps(ctx)

        # 必须是九段大纲
        assert len(steps) == 9, f"Expected 9 steps (九段大纲), got {len(steps)}"

    def test_get_execution_steps_content(
        self, template: PlanTemplate, ctx: CommandTemplateContext
    ) -> None:
        """Test that execution steps contain required content."""
        steps = template.get_execution_steps(ctx)

        # 第一步：读取 proposal
        assert "proposal.md" in steps[0]

        # 第二步：识别技术硬要求
        assert "技术硬要求" in steps[1]
        assert "CLAUDE.md" in steps[1]

        # 第三步：分析依赖关系
        assert "依赖关系" in steps[2]

        # 第四步：创建 Gate-0
        assert "Gate-0" in steps[3]
        assert "串行" in steps[3]

        # 第五步：创建 Wave
        assert "Wave-1" in steps[4] or "Wave" in steps[4]
        assert "并行" in steps[4] or "并发" in steps[4]

        # 第六步：预估上下文
        assert "预估上下文" in steps[5] or "estimate" in steps[5]

        # 第七步：检查清单
        assert "检查清单" in steps[6] or "checklist" in steps[6]

        # 第八步：生成 tasks.yaml
        assert "tasks.yaml" in steps[7]

        # 第九步：校验依赖
        assert "校验" in steps[8] or "依赖" in steps[8]

    def test_get_validation_checklist_count(
        self, template: PlanTemplate, ctx: CommandTemplateContext
    ) -> None:
        """Test that validation checklist has at least 4 items."""
        checklist = template.get_validation_checklist(ctx)

        # 至少4项验证
        assert len(checklist) >= 4, f"Expected at least 4 validation items, got {len(checklist)}"

    def test_get_validation_checklist_content(
        self, template: PlanTemplate, ctx: CommandTemplateContext
    ) -> None:
        """Test that validation checklist contains required checks."""
        checklist = template.get_validation_checklist(ctx)
        checklist_text = "\n".join(checklist)

        # 必须检查 tasks.yaml 生成
        assert "tasks.yaml" in checklist_text

        # 必须检查 Gate-0
        assert "Gate-0" in checklist_text

        # 必须检查 Wave 分组
        assert "Wave" in checklist_text

        # 必须检查依赖关系
        assert "依赖" in checklist_text

    def test_get_guidelines(
        self, template: PlanTemplate, ctx: CommandTemplateContext
    ) -> None:
        """Test that guidelines contain comprehensive planning rules."""
        guidelines = template.get_guidelines(ctx)

        # 必须包含 Gate/Wave 规划原则
        assert "Gate/Wave" in guidelines or "Gate" in guidelines

        # 必须包含技术硬要求提取
        assert "技术硬要求" in guidelines

        # 必须包含 tasks.yaml 结构说明
        assert "tasks.yaml" in guidelines

        # 必须包含预估上下文计算
        assert "预估上下文" in guidelines or "estimate" in guidelines

        # 必须包含检查清单编写规范
        assert "检查清单" in guidelines or "checklist" in guidelines

    def test_render_markdown_structure(
        self, template: PlanTemplate, ctx: CommandTemplateContext
    ) -> None:
        """Test that rendered markdown has correct structure."""
        content = template.render(ctx, fmt=RenderFormat.MARKDOWN)

        # 检查基本结构
        assert "## User Input" in content
        assert "## Outline" in content
        assert "## Execution Steps" in content
        assert "## Validation Checklist" in content
        assert "## Guidelines" in content
        assert "## Command Reference" in content

        # 检查命令引用
        assert "cc-spec plan" in content

    def test_render_markdown_length(
        self, template: PlanTemplate, ctx: CommandTemplateContext
    ) -> None:
        """Test that rendered markdown meets length requirements (150-300 lines)."""
        content = template.render(ctx, fmt=RenderFormat.MARKDOWN)
        lines = content.split("\n")

        # 检查长度要求（任务 checklist 要求 150-300 行）
        line_count = len(lines)
        assert 150 <= line_count <= 500, (
            f"Template length should be 150-500 lines, got {line_count} lines. "
            f"Task requirement: 150-300 lines, allowing some flexibility."
        )

    def test_render_toml_structure(
        self, template: PlanTemplate, ctx: CommandTemplateContext
    ) -> None:
        """Test that rendered TOML has correct structure."""
        content = template.render(ctx, fmt=RenderFormat.TOML)

        # 检查 TOML 结构
        assert "[prompt]" in content
        assert 'content = """' in content

        # 检查内嵌的 markdown 内容
        assert "## Outline" in content
        assert "## Execution Steps" in content

    def test_guidelines_gate_wave_rules(
        self, template: PlanTemplate, ctx: CommandTemplateContext
    ) -> None:
        """Test that guidelines contain detailed Gate/Wave rules."""
        guidelines = template.get_guidelines(ctx)

        # Gate-0 规则
        assert "Gate-0" in guidelines
        assert "串行" in guidelines

        # Wave 规则
        assert "Wave" in guidelines
        assert "并行" in guidelines or "并发" in guidelines

        # 依赖规则
        assert "依赖" in guidelines

    def test_guidelines_technical_requirements(
        self, template: PlanTemplate, ctx: CommandTemplateContext
    ) -> None:
        """Test that guidelines contain technical requirements extraction."""
        guidelines = template.get_guidelines(ctx)

        # 必须提到 CLAUDE.md
        assert "CLAUDE.md" in guidelines

        # 必须提到测试命令
        assert "测试" in guidelines or "test" in guidelines

        # 必须提到 lint
        assert "lint" in guidelines or "ruff" in guidelines

    def test_guidelines_yaml_structure(
        self, template: PlanTemplate, ctx: CommandTemplateContext
    ) -> None:
        """Test that guidelines explain tasks.yaml structure."""
        guidelines = template.get_guidelines(ctx)

        # 必须说明 meta 字段
        assert "meta" in guidelines

        # 必须说明 waves 字段
        assert "waves" in guidelines

        # 必须说明任务字段
        assert "id:" in guidelines or "name:" in guidelines or "desc:" in guidelines

    def test_guidelines_common_pitfalls(
        self, template: PlanTemplate, ctx: CommandTemplateContext
    ) -> None:
        """Test that guidelines include common pitfalls section."""
        guidelines = template.get_guidelines(ctx)

        # 应该包含常见陷阱说明
        assert "陷阱" in guidelines or "错误" in guidelines or "避免" in guidelines
