"""cc-spec 歧义检测模块。

该模块提供规格文档的歧义检测功能，帮助识别需要澄清的模糊描述。

v0.1.4: 新增歧义检测系统，支持 9 种歧义分类。
"""

from .detector import (
    AMBIGUITY_KEYWORDS,
    AmbiguityMatch,
    AmbiguityType,
)

__all__ = [
    "AmbiguityType",
    "AmbiguityMatch",
    "AMBIGUITY_KEYWORDS",
]
