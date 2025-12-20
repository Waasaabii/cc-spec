"""Codex 执行结果与数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CodexErrorType(str, Enum):
    """Codex 执行错误类型。"""

    NONE = "none"  # 执行成功，无错误
    NOT_FOUND = "not_found"  # Codex CLI 未找到
    TIMEOUT = "timeout"  # 执行超时
    EXEC_FAILED = "exec_failed"  # 执行失败（非零退出码）
    PARSE_FAILED = "parse_failed"  # JSONL 解析失败


@dataclass(frozen=True)
class CodexResult:
    success: bool
    exit_code: int
    message: str
    session_id: str | None
    stderr: str
    duration_seconds: float
    events_parsed: int = 0
    error_type: CodexErrorType = CodexErrorType.NONE

