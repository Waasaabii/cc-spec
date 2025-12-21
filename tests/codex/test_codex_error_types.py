"""测试 Codex 模型和客户端。"""

from unittest.mock import MagicMock, patch

import pytest

from cc_spec.codex.models import CodexErrorType, CodexResult


class TestCodexErrorType:
    """测试 CodexErrorType 枚举。"""

    def test_error_type_values(self) -> None:
        """验证所有错误类型的值。"""
        assert CodexErrorType.NONE.value == "none"
        assert CodexErrorType.NOT_FOUND.value == "not_found"
        assert CodexErrorType.TIMEOUT.value == "timeout"
        assert CodexErrorType.EXEC_FAILED.value == "exec_failed"
        assert CodexErrorType.PARSE_FAILED.value == "parse_failed"

    def test_error_type_is_str_enum(self) -> None:
        """CodexErrorType 应该是字符串枚举。"""
        assert isinstance(CodexErrorType.NONE, str)
        assert CodexErrorType.TIMEOUT == "timeout"


class TestCodexResult:
    """测试 CodexResult 数据类。"""

    def test_default_error_type_is_none(self) -> None:
        """默认 error_type 应为 NONE。"""
        result = CodexResult(
            success=True,
            exit_code=0,
            message="OK",
            session_id="test-session",
            stderr="",
            duration_seconds=1.0,
        )
        assert result.error_type == CodexErrorType.NONE

    def test_error_type_can_be_set(self) -> None:
        """error_type 可以被显式设置。"""
        result = CodexResult(
            success=False,
            exit_code=127,
            message="Not found",
            session_id=None,
            stderr="",
            duration_seconds=0.5,
            error_type=CodexErrorType.NOT_FOUND,
        )
        assert result.error_type == CodexErrorType.NOT_FOUND

    def test_timeout_error_type(self) -> None:
        """超时错误应使用 TIMEOUT 类型。"""
        result = CodexResult(
            success=False,
            exit_code=124,
            message="Timeout",
            session_id=None,
            stderr="",
            duration_seconds=60.0,
            error_type=CodexErrorType.TIMEOUT,
        )
        assert result.error_type == CodexErrorType.TIMEOUT

    def test_exec_failed_error_type(self) -> None:
        """执行失败应使用 EXEC_FAILED 类型。"""
        result = CodexResult(
            success=False,
            exit_code=1,
            message="Error",
            session_id="sess-123",
            stderr="some error",
            duration_seconds=2.0,
            error_type=CodexErrorType.EXEC_FAILED,
        )
        assert result.error_type == CodexErrorType.EXEC_FAILED


class TestCodexClientErrorTypes:
    """测试 CodexClient 返回的 error_type。"""

    def test_not_found_returns_not_found_error_type(self, tmp_path) -> None:
        """FileNotFoundError 应返回 NOT_FOUND 错误类型。"""
        from cc_spec.codex.client import CodexClient

        # 使用一个不存在的命令
        client = CodexClient(codex_bin="nonexistent-codex-command-12345")
        result = client.execute("test task", tmp_path)

        assert result.success is False
        assert result.exit_code == 127
        assert result.error_type == CodexErrorType.NOT_FOUND

    def test_timeout_returns_timeout_error_type(self, tmp_path) -> None:
        """超时应返回 TIMEOUT 错误类型。"""
        import subprocess

        from cc_spec.codex.client import CodexClient

        with patch("subprocess.run") as mock_run:
            # TimeoutExpired 需要手动设置 stdout/stderr 属性
            exc = subprocess.TimeoutExpired(cmd=["codex"], timeout=1.0)
            exc.stdout = ""
            exc.stderr = ""
            mock_run.side_effect = exc

            client = CodexClient(codex_bin="codex")
            result = client.execute("test task", tmp_path, timeout_ms=1000)

            assert result.success is False
            assert result.exit_code == 124
            assert result.error_type == CodexErrorType.TIMEOUT

    def test_exec_failed_returns_exec_failed_error_type(self, tmp_path) -> None:
        """非零退出码应返回 EXEC_FAILED 错误类型。"""
        import subprocess

        from cc_spec.codex.client import CodexClient

        mock_completed = MagicMock()
        mock_completed.returncode = 1
        mock_completed.stdout = ""
        mock_completed.stderr = "error message"

        with patch("subprocess.run", return_value=mock_completed):
            client = CodexClient(codex_bin="codex")
            result = client.execute("test task", tmp_path)

            assert result.success is False
            assert result.exit_code == 1
            assert result.error_type == CodexErrorType.EXEC_FAILED

    def test_success_returns_none_error_type(self, tmp_path) -> None:
        """成功执行应返回 NONE 错误类型。"""
        import subprocess

        from cc_spec.codex.client import CodexClient

        mock_completed = MagicMock()
        mock_completed.returncode = 0
        mock_completed.stdout = '{"type":"session.start","session_id":"test-sess"}\n'
        mock_completed.stderr = ""

        with patch("subprocess.run", return_value=mock_completed):
            client = CodexClient(codex_bin="codex")
            result = client.execute("test task", tmp_path)

            assert result.success is True
            assert result.exit_code == 0
            assert result.error_type == CodexErrorType.NONE
