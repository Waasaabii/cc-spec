"""v0.2.x: Codex CLI 执行层（通过 cc-spec-tool HTTP API）。

重要：所有 Codex 调用必须通过 ToolClient，不再支持直接调用。
"""

from .models import CodexErrorType, CodexResult
from .tool_client import ToolClient, get_tool_client

__all__ = [
    "CodexErrorType",
    "CodexResult",
    "ToolClient",
    "get_tool_client",
]

