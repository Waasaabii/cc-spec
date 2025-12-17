"""Codex 执行结果与数据模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CodexResult:
    success: bool
    exit_code: int
    message: str
    session_id: str | None
    stderr: str
    duration_seconds: float
    events_parsed: int = 0

