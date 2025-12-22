"""Unit tests for Codex progress indicator."""

import os
import re
from io import StringIO
from unittest.mock import patch

import pytest
from rich.console import Console


def strip_ansi(text: str) -> str:
    """移除 ANSI 转义码。"""
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)

from cc_spec.codex.progress import (
    CodexEventInfo,
    CodexProgressIndicator,
    OutputMode,
    parse_codex_event,
)


class TestOutputModeEnvPriority:
    """测试环境变量优先级。"""

    def test_new_env_takes_priority(self) -> None:
        """CC_SPEC_CODEX_OUTPUT 优先于 CC_SPEC_CODEX_STREAM。"""
        from cc_spec.codex.client import _get_output_mode

        with patch.dict(
            os.environ,
            {"CC_SPEC_CODEX_OUTPUT": "stream", "CC_SPEC_CODEX_STREAM": "false"},
        ):
            mode = _get_output_mode()
            assert mode == OutputMode.STREAM

    def test_new_env_progress_mode(self) -> None:
        """CC_SPEC_CODEX_OUTPUT=progress 返回进度模式。"""
        from cc_spec.codex.client import _get_output_mode

        with patch.dict(os.environ, {"CC_SPEC_CODEX_OUTPUT": "progress"}, clear=True):
            mode = _get_output_mode()
            assert mode == OutputMode.PROGRESS

    def test_new_env_quiet_mode(self) -> None:
        """CC_SPEC_CODEX_OUTPUT=quiet 返回静默模式。"""
        from cc_spec.codex.client import _get_output_mode

        with patch.dict(os.environ, {"CC_SPEC_CODEX_OUTPUT": "quiet"}, clear=True):
            mode = _get_output_mode()
            assert mode == OutputMode.QUIET

    def test_legacy_env_stream_true(self) -> None:
        """CC_SPEC_CODEX_STREAM=true 兼容返回流模式。"""
        from cc_spec.codex.client import _get_output_mode

        with patch.dict(os.environ, {"CC_SPEC_CODEX_STREAM": "true"}, clear=True):
            mode = _get_output_mode()
            assert mode == OutputMode.STREAM

    def test_legacy_env_stream_false(self) -> None:
        """CC_SPEC_CODEX_STREAM=false 兼容返回静默模式。"""
        from cc_spec.codex.client import _get_output_mode

        with patch.dict(os.environ, {"CC_SPEC_CODEX_STREAM": "false"}, clear=True):
            mode = _get_output_mode()
            assert mode == OutputMode.QUIET

    def test_default_tty_returns_progress(self) -> None:
        """无环境变量时，TTY 环境默认返回 progress 模式。"""
        from cc_spec.codex.client import _get_output_mode

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("sys.stdout.isatty", return_value=True),
        ):
            mode = _get_output_mode()
            assert mode == OutputMode.PROGRESS

    def test_default_non_tty_returns_quiet(self) -> None:
        """无环境变量时，非 TTY 环境默认返回 quiet 模式。"""
        from cc_spec.codex.client import _get_output_mode

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("sys.stdout.isatty", return_value=False),
        ):
            mode = _get_output_mode()
            assert mode == OutputMode.QUIET


class TestEventParsing:
    """测试 JSONL 事件解析。"""

    def test_parse_thread_started(self) -> None:
        """解析 thread.started 事件。"""
        line = '{"type":"thread.started","thread_id":"sess-123"}'
        event = parse_codex_event(line)

        assert event is not None
        assert event.event_type == "thread.started"
        assert event.session_id == "sess-123"
        assert event.is_completed is False

    def test_parse_tool_call(self) -> None:
        """解析工具调用事件。"""
        line = '{"type":"item.started","item":{"type":"function_call","name":"read_file"}}'
        event = parse_codex_event(line)

        assert event is not None
        assert event.event_type == "item.started"
        assert event.tool_name == "read_file"

    def test_parse_agent_message(self) -> None:
        """解析 agent 消息事件。"""
        line = '{"type":"item.completed","item":{"type":"agent_message","text":"Hello world"}}'
        event = parse_codex_event(line)

        assert event is not None
        assert event.event_type == "item.completed"
        assert event.agent_message == "Hello world"

    def test_parse_turn_completed(self) -> None:
        """解析 turn.completed 事件。"""
        line = '{"type":"turn.completed"}'
        event = parse_codex_event(line)

        assert event is not None
        assert event.event_type == "turn.completed"
        assert event.is_completed is True

    def test_parse_invalid_json(self) -> None:
        """无效 JSON 返回 None。"""
        event = parse_codex_event("not json")
        assert event is None

    def test_parse_empty_line(self) -> None:
        """空行返回 None。"""
        event = parse_codex_event("")
        assert event is None
        event = parse_codex_event("   ")
        assert event is None

    def test_parse_non_dict_json(self) -> None:
        """非字典 JSON 返回 None。"""
        event = parse_codex_event("[]")
        assert event is None
        event = parse_codex_event('"string"')
        assert event is None


class TestProgressIndicatorStartStop:
    """测试进度指示器启动和停止。"""

    def test_start_sets_active(self) -> None:
        """start() 设置 is_active 为 True。"""
        console = Console(file=StringIO(), force_terminal=True)
        indicator = CodexProgressIndicator(console=console)

        assert indicator.is_active() is False
        indicator.start()
        assert indicator.is_active() is True

        # 清理
        if indicator._status:
            indicator._status.stop()

    def test_stop_clears_active(self) -> None:
        """stop() 清除 is_active 状态。"""
        console = Console(file=StringIO(), force_terminal=True)
        indicator = CodexProgressIndicator(console=console)

        indicator.start()
        indicator.stop(success=True, duration=1.0, message="Done")

        assert indicator.is_active() is False

    def test_context_manager(self) -> None:
        """上下文管理器正确启动和停止。"""
        console = Console(file=StringIO(), force_terminal=True)
        indicator = CodexProgressIndicator(console=console)

        with indicator:
            assert indicator.is_active() is True

        assert indicator.is_active() is False


class TestProcessLine:
    """测试 process_line 方法。"""

    def test_process_line_extracts_session_id(self) -> None:
        """process_line 正确提取 session_id。"""
        console = Console(file=StringIO(), force_terminal=True)
        indicator = CodexProgressIndicator(console=console)
        indicator.start()

        line = '{"type":"thread.started","thread_id":"sess-abc123"}'
        session_id = indicator.process_line(line)

        assert session_id == "sess-abc123"

        indicator.stop(success=True, duration=1.0)

    def test_process_line_tracks_tool_calls(self) -> None:
        """process_line 跟踪工具调用。"""
        console = Console(file=StringIO(), force_terminal=True)
        indicator = CodexProgressIndicator(console=console)
        indicator.start()

        line = '{"type":"item.started","item":{"type":"function_call","name":"write_file"}}'
        indicator.process_line(line)

        assert "write_file" in indicator._tool_calls

        indicator.stop(success=True, duration=1.0)

    def test_process_line_counts_events(self) -> None:
        """process_line 正确计数事件。"""
        console = Console(file=StringIO(), force_terminal=True)
        indicator = CodexProgressIndicator(console=console)
        indicator.start()

        indicator.process_line('{"type":"thread.started","thread_id":"s1"}')
        indicator.process_line('{"type":"turn.completed"}')

        assert indicator._events_count == 2

        indicator.stop(success=True, duration=1.0)


class TestSummaryOutput:
    """测试完成摘要输出格式。"""

    def test_success_summary(self) -> None:
        """成功时显示正确的摘要格式。"""
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=80)
        indicator = CodexProgressIndicator(console=console)

        indicator._session_id = "sess-12345678"
        indicator._tool_calls = ["read_file", "write_file"]
        indicator._events_count = 5

        indicator.start()
        indicator.stop(success=True, duration=2.5, message="Task completed successfully")

        # 移除 ANSI 转义码后检查
        result = strip_ansi(output.getvalue())
        assert "✅" in result
        assert "成功" in result
        assert "2.5s" in result
        assert "sess-123" in result  # session_id 截断为 8 字符
        assert "read_file" in result

    def test_failure_summary(self) -> None:
        """失败时显示正确的摘要格式。"""
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=80)
        indicator = CodexProgressIndicator(console=console)

        indicator.start()
        indicator.stop(success=False, duration=1.0, message="Error occurred")

        result = strip_ansi(output.getvalue())
        assert "❌" in result
        assert "失败" in result

    def test_summary_truncates_long_message(self) -> None:
        """长消息被截断为 100 字符。"""
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=120)
        indicator = CodexProgressIndicator(console=console)

        long_message = "A" * 150

        indicator.start()
        indicator.stop(success=True, duration=1.0, message=long_message)

        result = strip_ansi(output.getvalue())
        assert "..." in result
