"""Codex JSONL 输出解析。

Codex `codex exec --json` 会输出 JSONL 事件流，关键事件：
- thread.started: 提供 thread_id（作为 session_id）
- item.completed + item.type == agent_message: 最终回复文本
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class ParsedCodexStream:
    message: str
    session_id: str | None
    events_parsed: int


def parse_codex_jsonl(lines: Iterable[str]) -> ParsedCodexStream:
    session_id: str | None = None
    message: str = ""
    events = 0

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        events += 1

        event_type = obj.get("type")
        if event_type == "thread.started":
            thread_id = obj.get("thread_id")
            if isinstance(thread_id, str) and thread_id:
                session_id = thread_id
            continue

        if event_type == "item.completed":
            item = obj.get("item")
            if not isinstance(item, dict):
                continue
            if item.get("type") != "agent_message":
                continue
            text = item.get("text")
            normalized = _normalize_text(text)
            if normalized:
                message = normalized
            continue

    return ParsedCodexStream(message=message, session_id=session_id, events_parsed=events)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for x in value:
            if isinstance(x, str):
                parts.append(x)
            else:
                parts.append(json.dumps(x, ensure_ascii=False))
        return "".join(parts).strip()
    if isinstance(value, dict):
        # 常见兼容：{"text": "..."} 或 {"content": "..."}
        for k in ("text", "content", "message"):
            v = value.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return json.dumps(value, ensure_ascii=False).strip()
    return str(value).strip()

