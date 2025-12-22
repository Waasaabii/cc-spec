"""Codex 流式输出进度指示器。

替代原始 JSONL 流式输出，以简洁的 Spinner + 状态方式显示进度。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.status import Status
from rich.text import Text


class OutputMode(str, Enum):
    """Codex 输出模式。"""

    STREAM = "stream"  # 原始流式输出（打印所有 JSONL）
    PROGRESS = "progress"  # 进度指示模式（Spinner + 状态）
    QUIET = "quiet"  # 静默模式（只显示最终结果）


@dataclass
class CodexEventInfo:
    """解析后的 Codex 事件信息。"""

    event_type: str
    session_id: str | None = None
    tool_name: str | None = None
    agent_message: str | None = None
    is_completed: bool = False


def parse_codex_event(line: str) -> CodexEventInfo | None:
    """解析单行 Codex JSONL 事件。

    Args:
        line: JSONL 行

    Returns:
        解析后的事件信息，解析失败返回 None
    """
    if not line.strip():
        return None

    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None

    if not isinstance(obj, dict):
        return None

    event_type = obj.get("type", "")
    info = CodexEventInfo(event_type=event_type)

    # 会话启动
    if event_type == "thread.started":
        info.session_id = obj.get("thread_id")
        return info

    # 轮次完成
    if event_type == "turn.completed":
        info.is_completed = True
        return info

    # 项目开始 - 检测工具调用
    if event_type == "item.started":
        item = obj.get("item", {})
        item_type = item.get("type", "")
        if item_type in ("function_call_request", "tool_use", "function_call"):
            # 尝试提取工具名
            info.tool_name = (
                item.get("name")
                or item.get("function", {}).get("name")
                or item.get("tool_name")
                or "工具"
            )
        return info

    # 项目完成 - 检测 agent 消息
    if event_type == "item.completed":
        item = obj.get("item", {})
        if item.get("type") == "agent_message":
            text = item.get("text", "")
            if isinstance(text, str):
                info.agent_message = text
            elif isinstance(text, list):
                info.agent_message = "".join(
                    x if isinstance(x, str) else json.dumps(x) for x in text
                )
        return info

    return info


class CodexProgressIndicator:
    """Codex 执行进度指示器。

    使用 Rich Status (Spinner) 显示简洁的执行状态。
    """

    def __init__(self, console: Console | None = None):
        """初始化进度指示器。

        Args:
            console: Rich Console 实例
        """
        self.console = console or Console()
        self._status: Status | None = None
        self._start_time: float = 0.0
        self._session_id: str | None = None
        self._events_count: int = 0
        self._current_status: str = "初始化..."
        self._agent_messages: list[str] = []
        self._tool_calls: list[str] = []
        self._is_started: bool = False

    def start(self) -> None:
        """开始进度指示。"""
        self._start_time = time.time()
        self._status = self.console.status(
            "[cyan]🔄 Codex 启动中...[/cyan]",
            spinner="dots",
        )
        self._status.start()
        self._is_started = True

    def process_line(self, line: str) -> str | None:
        """处理一行 JSONL 输出，更新状态。

        Args:
            line: JSONL 行

        Returns:
            提取的 session_id（如果有）
        """
        self._events_count += 1
        event = parse_codex_event(line)
        if event is None:
            return None

        session_id = None

        # 会话启动
        if event.session_id:
            self._session_id = event.session_id
            session_id = event.session_id
            self._update_status("🟢 会话已启动")

        # 工具调用
        elif event.tool_name:
            self._tool_calls.append(event.tool_name)
            self._update_status(f"⚙️ 执行: {event.tool_name}")

        # Agent 消息
        elif event.agent_message:
            self._agent_messages.append(event.agent_message)
            # 显示消息摘要（前30字符）
            preview = event.agent_message[:30].replace("\n", " ")
            if len(event.agent_message) > 30:
                preview += "..."
            self._update_status(f"💬 响应: {preview}")

        # 完成
        elif event.is_completed:
            self._update_status("✅ 执行完成")

        return session_id

    def _update_status(self, message: str) -> None:
        """更新状态显示。"""
        self._current_status = message
        elapsed = time.time() - self._start_time
        elapsed_str = f"{elapsed:.1f}s"

        if self._status:
            self._status.update(f"[cyan]{message}[/cyan] [dim]({elapsed_str})[/dim]")

    def stop(self, success: bool, duration: float, message: str = "") -> None:
        """停止进度指示，显示摘要。

        Args:
            success: 是否成功
            duration: 执行耗时（秒）
            message: agent 最终消息
        """
        if self._status:
            self._status.stop()
            self._status = None

        self._is_started = False

        # 构建摘要
        self._print_summary(success, duration, message)

    def _print_summary(self, success: bool, duration: float, message: str) -> None:
        """打印执行摘要。"""
        # 状态图标和颜色
        if success:
            status_icon = "✅"
            status_text = "[green]成功[/green]"
        else:
            status_icon = "❌"
            status_text = "[red]失败[/red]"

        # 构建摘要文本
        lines = [
            f"{status_icon} Codex 执行{status_text}",
            f"   ⏱️  耗时: [cyan]{duration:.1f}s[/cyan]",
        ]

        if self._session_id:
            # 显示简短的 session_id
            short_id = self._session_id[:8] if len(self._session_id) > 8 else self._session_id
            lines.append(f"   🔑 会话: [dim]{short_id}...[/dim]")

        if self._tool_calls:
            tools_str = ", ".join(self._tool_calls[:3])
            if len(self._tool_calls) > 3:
                tools_str += f" +{len(self._tool_calls) - 3}"
            lines.append(f"   🔧 工具: [yellow]{tools_str}[/yellow]")

        lines.append(f"   📊 事件: [dim]{self._events_count}[/dim]")

        # 显示 agent 回复摘要
        if message:
            preview = message[:100].replace("\n", " ").strip()
            if len(message) > 100:
                preview += "..."
            lines.append(f"   💬 回复: {preview}")

        self.console.print("\n".join(lines))

    def is_active(self) -> bool:
        """检查进度指示器是否正在运行。"""
        return self._is_started

    def __enter__(self) -> "CodexProgressIndicator":
        """上下文管理器入口。"""
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        """上下文管理器出口。"""
        if self._is_started and self._status:
            self._status.stop()
            self._is_started = False
