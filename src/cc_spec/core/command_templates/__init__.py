"""cc-spec 命令模板模块。

该模块提供命令模板的基础架构，用于生成 AI 工具的工作流指令。

v0.1.4: 新增模板系统，支持结构化的命令内容生成。
"""

from .apply_template import ApplyTemplate
from .base import (
    CommandTemplate,
    CommandTemplateContext,
)
from .checklist_template import ChecklistTemplate
from .clarify_template import ClarifyTemplate
from .init_template import InitTemplate
from .plan_template import PlanTemplate
from .specify_template import SpecifyTemplate

__all__ = [
    "ApplyTemplate",
    "ChecklistTemplate",
    "ClarifyTemplate",
    "CommandTemplate",
    "CommandTemplateContext",
    "InitTemplate",
    "PlanTemplate",
    "SpecifyTemplate",
]
