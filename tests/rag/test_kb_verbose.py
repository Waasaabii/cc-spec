"""测试 kb 命令的 verbose 模式。"""

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from cc_spec.commands.kb import _make_verbose_callback
from cc_spec.rag.models import ChunkResult, ChunkStatus


class TestMakeVerboseCallback:
    """测试 _make_verbose_callback 函数。"""

    def test_callback_prints_success_status(self) -> None:
        """成功状态应显示绿色的'成功'标记。"""
        output = StringIO()
        # 使用 no_color=True 禁用 ANSI 转义码
        console = Console(file=output, force_terminal=False, no_color=True, width=120)
        callback = _make_verbose_callback(console)

        result = ChunkResult(
            chunks=[MagicMock()],
            status=ChunkStatus.SUCCESS,
            source_path="test.py",
        )
        callback(0, 10, "src/test.py", result)

        out = output.getvalue()
        assert "1/10" in out
        assert "src/test.py" in out
        assert "1 chunks" in out
        assert "✓" in out
        assert "成功" in out

    def test_callback_prints_fallback_exec_status(self) -> None:
        """执行失败的 fallback 状态应显示黄色警告。"""
        output = StringIO()
        console = Console(file=output, force_terminal=False, no_color=True, width=120)
        callback = _make_verbose_callback(console)

        result = ChunkResult(
            chunks=[MagicMock(), MagicMock()],
            status=ChunkStatus.FALLBACK_EXEC,
            source_path="test.py",
            error_message="Codex execution failed",
        )
        callback(5, 20, "src/large_file.py", result)

        out = output.getvalue()
        assert "6/20" in out
        assert "src/large_file.py" in out
        assert "2 chunks" in out
        assert "⚠" in out
        assert "fallback" in out
        assert "执行失败" in out

    def test_callback_prints_fallback_parse_status(self) -> None:
        """解析失败的 fallback 状态应正确显示。"""
        output = StringIO()
        console = Console(file=output, force_terminal=False, no_color=True, width=120)
        callback = _make_verbose_callback(console)

        result = ChunkResult(
            chunks=[],
            status=ChunkStatus.FALLBACK_PARSE,
            source_path="test.py",
            error_message="JSON parse error",
        )
        callback(9, 10, "src/broken.py", result)

        out = output.getvalue()
        assert "10/10" in out
        assert "src/broken.py" in out
        assert "0 chunks" in out
        assert "⚠" in out
        assert "解析失败" in out

    def test_callback_prints_fallback_empty_status(self) -> None:
        """空结果的 fallback 状态应正确显示。"""
        output = StringIO()
        console = Console(file=output, force_terminal=False, no_color=True, width=120)
        callback = _make_verbose_callback(console)

        result = ChunkResult(
            chunks=[],
            status=ChunkStatus.FALLBACK_EMPTY,
            source_path="test.py",
        )
        callback(0, 1, "src/empty.py", result)

        out = output.getvalue()
        assert "1/1" in out
        assert "src/empty.py" in out
        assert "⚠" in out
        assert "结果为空" in out

    def test_callback_returns_callable(self) -> None:
        """_make_verbose_callback 应返回可调用对象。"""
        console = Console()
        callback = _make_verbose_callback(console)
        assert callable(callback)


class TestKbInitVerboseOption:
    """测试 kb init 命令的 --verbose 选项。"""

    def test_kb_init_has_verbose_option(self) -> None:
        """kb init 命令应有 --verbose/-v 选项。"""
        from typer.testing import CliRunner

        from cc_spec import app

        runner = CliRunner()
        result = runner.invoke(app, ["kb", "init", "--help"])
        assert result.exit_code == 0
        assert "--verbose" in result.output or "-v" in result.output


class TestKbUpdateVerboseOption:
    """测试 kb update 命令的 --verbose 选项。"""

    def test_kb_update_has_verbose_option(self) -> None:
        """kb update 命令应有 --verbose/-v 选项。"""
        from typer.testing import CliRunner

        from cc_spec import app

        runner = CliRunner()
        result = runner.invoke(app, ["kb", "update", "--help"])
        assert result.exit_code == 0
        assert "--verbose" in result.output or "-v" in result.output
