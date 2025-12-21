"""命令模板的基础类。

该模块定义了命令模板系统的核心抽象：
- CommandTemplateContext: 模板渲染所需的上下文数据
- CommandTemplate: 模板的抽象基类，定义统一接口
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class RenderFormat(Enum):
    """模板渲染输出格式。"""

    MARKDOWN = "markdown"
    TOML = "toml"


@dataclass
class CommandTemplateContext:
    """命令模板的渲染上下文。

    属性：
        command_name: 命令名称（如 specify, clarify, plan）
        namespace: 命令命名空间（如 cc-spec）
        config_sources: 配置文件路径列表（如 CLAUDE.md, config.yaml）
        project_root: 项目根目录
        extra: 扩展数据，用于特定模板的自定义需求
    """

    command_name: str
    namespace: str = "cc-spec"
    config_sources: list[str] = field(default_factory=list)
    project_root: Path | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def get_full_command_name(self) -> str:
        """获取完整命令名（包含命名空间）。"""
        if self.namespace:
            return f"{self.namespace}.{self.command_name}"
        return self.command_name


class CommandTemplate(ABC):
    """命令模板的抽象基类。

    每个具体命令（如 specify, clarify）都需要实现该抽象类，
    提供其特有的大纲、执行步骤和验证检查清单。
    """

    @abstractmethod
    def get_outline(self, ctx: CommandTemplateContext) -> str:
        """获取命令的大纲描述。

        大纲是命令功能的概要说明，帮助 AI 理解命令目的。

        参数：
            ctx: 模板渲染上下文

        返回：
            大纲文本（Markdown 格式）
        """
        ...

    @abstractmethod
    def get_execution_steps(self, ctx: CommandTemplateContext) -> list[str]:
        """获取命令的执行步骤列表。

        每个步骤是一个可执行的指令，AI 将按顺序执行。

        参数：
            ctx: 模板渲染上下文

        返回：
            执行步骤列表
        """
        ...

    @abstractmethod
    def get_validation_checklist(self, ctx: CommandTemplateContext) -> list[str]:
        """获取命令完成后的验证检查清单。

        检查清单用于验证命令是否正确执行完毕。

        参数：
            ctx: 模板渲染上下文

        返回：
            验证项列表
        """
        ...

    def get_guidelines(self, ctx: CommandTemplateContext) -> str:
        """获取通用指南。

        子类可重写此方法提供特定指南。

        参数：
            ctx: 模板渲染上下文

        返回：
            指南文本（Markdown 格式）
        """
        return ""

    def render(
        self,
        ctx: CommandTemplateContext,
        fmt: RenderFormat = RenderFormat.MARKDOWN,
    ) -> str:
        """渲染完整的命令模板内容。

        参数：
            ctx: 模板渲染上下文
            fmt: 输出格式（markdown 或 toml）

        返回：
            渲染后的完整模板内容
        """
        if fmt == RenderFormat.TOML:
            return self._render_toml(ctx)
        return self._render_markdown(ctx)

    def _render_markdown(self, ctx: CommandTemplateContext) -> str:
        """渲染 Markdown 格式的模板。"""
        outline = self.get_outline(ctx)
        steps = self.get_execution_steps(ctx)
        checklist = self.get_validation_checklist(ctx)
        guidelines = self.get_guidelines(ctx)

        lines = [
            "## User Input",
            "",
            "```text",
            "$ARGUMENTS",
            "```",
            "",
            "You **MUST** consider the user input before proceeding (if not empty).",
            "",
            "## Workflow Controls",
            "",
            "- 默认不跳过任何步骤；仅在用户**明确表达**时允许跳过/强制快速（支持中文自然语句）。",
            "- 检测到跳过/强制时，必须写入 KB record（包含原始用户语句与跳过步骤）。",
            "- 模式判定需基于 KB 调研评估影响面；无法确认时默认标准流程。",
            "- 快速/标准判定：影响文件数 > 5 必须走标准流程（禁止 quick）。",
            "- 统计影响文件数可用：`git status --porcelain` 或 `git diff --name-only`。",
            "",
            "## Outline",
            "",
            outline,
            "",
            "## Execution Steps",
            "",
        ]

        for i, step in enumerate(steps, 1):
            lines.append(f"{i}. {step}")
        lines.append("")

        lines.extend([
            "## Validation Checklist",
            "",
        ])
        for item in checklist:
            lines.append(f"- [ ] {item}")
        lines.append("")

        if guidelines:
            lines.extend([
                "## Guidelines",
                "",
                guidelines,
                "",
            ])

        lines.extend([
            "## Command Reference",
            "",
            "```bash",
            f"cc-spec {ctx.command_name} --help",
            "```",
        ])

        return "\n".join(lines)

    def _render_toml(self, ctx: CommandTemplateContext) -> str:
        """渲染 TOML 格式的模板。"""
        md_content = self._render_markdown(ctx)
        # TOML 格式需要将内容包装在多行字符串中
        escaped_content = md_content.replace('"""', '\\"\\"\\"')
        return f'''[prompt]
content = """
{escaped_content}
"""
'''
