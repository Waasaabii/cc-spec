"""cc-spec 歧义检测模块。

该模块提供规格文档的歧义检测功能，帮助识别需要澄清的模糊描述。

v0.1.4: 新增歧义检测系统，支持 9 种歧义分类。
"""

from .detector import (
    AMBIGUITY_KEYWORDS,
    AmbiguityMatch,
    AmbiguityType,
    detect,
    filter_false_positives,
    get_context,
    get_keywords_by_type,
    get_type_description,
    is_in_code_block,
)

__all__ = [
    "AmbiguityType",
    "AmbiguityMatch",
    "AMBIGUITY_KEYWORDS",
    "detect",
    "get_context",
    "is_in_code_block",
    "filter_false_positives",
    "get_type_description",
    "get_keywords_by_type",
]
