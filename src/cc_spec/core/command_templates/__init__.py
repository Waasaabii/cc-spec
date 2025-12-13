"""cc-spec 命令模板模块。

该模块提供命令模板的基础架构，用于生成 AI 工具的工作流指令。

v0.1.4: 新增模板系统，支持结构化的命令内容生成。
"""

from .base import (
    CommandTemplate,
    CommandTemplateContext,
)

__all__ = [
    "CommandTemplate",
    "CommandTemplateContext",
]
