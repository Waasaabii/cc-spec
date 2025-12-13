"""cc-spec 技术检查模块。

该模块提供从配置文件中提取技术要求并执行检查的功能。
"""

from .detector import (
    TechRequirements,
    TechStack,
    detect_tech_stack,
    get_default_commands,
)
from .reader import read_tech_requirements
from .runner import CheckResult, run_tech_checks, should_block

__all__ = [
    "TechRequirements",
    "read_tech_requirements",
    "TechStack",
    "detect_tech_stack",
    "get_default_commands",
    "CheckResult",
    "run_tech_checks",
    "should_block",
]
