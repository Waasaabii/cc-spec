"""测试 chunker.py 中的重试机制。"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cc_spec.codex.models import CodexErrorType, CodexResult
from cc_spec.rag.chunker import ChunkingOptions, CodexChunker, _ParseResult
from cc_spec.rag.models import ChunkStatus


class TestChunkingOptionsRetry:
    """测试 ChunkingOptions 的重试配置。"""

    def test_default_retry_values(self) -> None:
        """默认重试配置应为 max_retries=2, retry_delay_s=1.0。"""
        options = ChunkingOptions()
        assert options.max_retries == 2
        assert options.retry_delay_s == 1.0

    def test_custom_retry_values(self) -> None:
        """可以自定义重试配置。"""
        options = ChunkingOptions(max_retries=5, retry_delay_s=0.5)
        assert options.max_retries == 5
        assert options.retry_delay_s == 0.5

    def test_zero_retries(self) -> None:
        """max_retries=0 表示不重试。"""
        options = ChunkingOptions(max_retries=0)
        assert options.max_retries == 0


class TestRetryMechanism:
    """测试 _run_and_parse 的重试机制。"""

    def test_no_retry_on_success(self, tmp_path: Path) -> None:
        """成功执行时不应重试。"""
        mock_codex = MagicMock()
        mock_codex.execute.return_value = CodexResult(
            success=True,
            exit_code=0,
            message='[{"id": "1", "summary": "test", "content": "hello"}]',
            session_id="sess-1",
            stderr="",
            duration_seconds=1.0,
            error_type=CodexErrorType.NONE,
        )

        chunker = CodexChunker(mock_codex, tmp_path)
        options = ChunkingOptions(max_retries=2)

        result = chunker._run_and_parse(
            "test prompt",
            raw_content="test content",
            source_path="test.py",
            source_sha256="abc123",
            options=options,
        )

        # 只执行了一次
        assert mock_codex.execute.call_count == 1
        assert result.status == ChunkStatus.SUCCESS
        assert result.retry_count == 0

    def test_retry_on_timeout(self, tmp_path: Path) -> None:
        """超时错误应重试。"""
        mock_codex = MagicMock()

        # 前两次超时，第三次成功
        mock_codex.execute.side_effect = [
            CodexResult(
                success=False,
                exit_code=124,
                message="timeout",
                session_id=None,
                stderr="",
                duration_seconds=60.0,
                error_type=CodexErrorType.TIMEOUT,
            ),
            CodexResult(
                success=False,
                exit_code=124,
                message="timeout",
                session_id=None,
                stderr="",
                duration_seconds=60.0,
                error_type=CodexErrorType.TIMEOUT,
            ),
            CodexResult(
                success=True,
                exit_code=0,
                message='[{"id": "1", "summary": "test", "content": "hello"}]',
                session_id="sess-1",
                stderr="",
                duration_seconds=1.0,
                error_type=CodexErrorType.NONE,
            ),
        ]

        chunker = CodexChunker(mock_codex, tmp_path)
        options = ChunkingOptions(max_retries=2, retry_delay_s=0.01)

        with patch("time.sleep"):  # 跳过实际等待
            result = chunker._run_and_parse(
                "test prompt",
                raw_content="test content",
                source_path="test.py",
                source_sha256="abc123",
                options=options,
            )

        # 执行了 3 次（1 次初始 + 2 次重试）
        assert mock_codex.execute.call_count == 3
        assert result.status == ChunkStatus.SUCCESS
        assert result.retry_count == 2

    def test_no_retry_on_exec_failed(self, tmp_path: Path) -> None:
        """非超时的执行失败不应重试。"""
        mock_codex = MagicMock()
        mock_codex.execute.return_value = CodexResult(
            success=False,
            exit_code=1,
            message="error",
            session_id=None,
            stderr="some error",
            duration_seconds=1.0,
            error_type=CodexErrorType.EXEC_FAILED,
        )

        chunker = CodexChunker(mock_codex, tmp_path)
        options = ChunkingOptions(max_retries=2)

        result = chunker._run_and_parse(
            "test prompt",
            raw_content="test content",
            source_path="test.py",
            source_sha256="abc123",
            options=options,
        )

        # 只执行了一次，不重试
        assert mock_codex.execute.call_count == 1
        assert result.status == ChunkStatus.FALLBACK_EXEC
        assert result.retry_count == 0

    def test_no_retry_on_not_found(self, tmp_path: Path) -> None:
        """CLI 未找到错误不应重试。"""
        mock_codex = MagicMock()
        mock_codex.execute.return_value = CodexResult(
            success=False,
            exit_code=127,
            message="not found",
            session_id=None,
            stderr="",
            duration_seconds=0.1,
            error_type=CodexErrorType.NOT_FOUND,
        )

        chunker = CodexChunker(mock_codex, tmp_path)
        options = ChunkingOptions(max_retries=2)

        result = chunker._run_and_parse(
            "test prompt",
            raw_content="test content",
            source_path="test.py",
            source_sha256="abc123",
            options=options,
        )

        # 只执行了一次，不重试
        assert mock_codex.execute.call_count == 1
        assert result.status == ChunkStatus.FALLBACK_EXEC
        assert result.retry_count == 0

    def test_max_retries_exhausted(self, tmp_path: Path) -> None:
        """重试次数耗尽后应返回 fallback。"""
        mock_codex = MagicMock()

        # 所有尝试都超时
        mock_codex.execute.return_value = CodexResult(
            success=False,
            exit_code=124,
            message="timeout",
            session_id=None,
            stderr="",
            duration_seconds=60.0,
            error_type=CodexErrorType.TIMEOUT,
        )

        chunker = CodexChunker(mock_codex, tmp_path)
        options = ChunkingOptions(max_retries=2, retry_delay_s=0.01)

        with patch("time.sleep"):  # 跳过实际等待
            result = chunker._run_and_parse(
                "test prompt",
                raw_content="test content\nline2\nline3",
                source_path="test.py",
                source_sha256="abc123",
                options=options,
            )

        # 执行了 3 次（1 次初始 + 2 次重试）
        assert mock_codex.execute.call_count == 3
        assert result.status == ChunkStatus.FALLBACK_EXEC
        assert result.retry_count == 2

    def test_zero_retries_no_retry(self, tmp_path: Path) -> None:
        """max_retries=0 时超时也不重试。"""
        mock_codex = MagicMock()
        mock_codex.execute.return_value = CodexResult(
            success=False,
            exit_code=124,
            message="timeout",
            session_id=None,
            stderr="",
            duration_seconds=60.0,
            error_type=CodexErrorType.TIMEOUT,
        )

        chunker = CodexChunker(mock_codex, tmp_path)
        options = ChunkingOptions(max_retries=0)

        result = chunker._run_and_parse(
            "test prompt",
            raw_content="test content",
            source_path="test.py",
            source_sha256="abc123",
            options=options,
        )

        # 只执行了一次
        assert mock_codex.execute.call_count == 1
        assert result.status == ChunkStatus.FALLBACK_EXEC
        assert result.retry_count == 0

    def test_retry_delay_is_called(self, tmp_path: Path) -> None:
        """重试时应调用 time.sleep。"""
        mock_codex = MagicMock()

        # 第一次超时，第二次成功
        mock_codex.execute.side_effect = [
            CodexResult(
                success=False,
                exit_code=124,
                message="timeout",
                session_id=None,
                stderr="",
                duration_seconds=60.0,
                error_type=CodexErrorType.TIMEOUT,
            ),
            CodexResult(
                success=True,
                exit_code=0,
                message='[{"id": "1", "summary": "test", "content": "hello"}]',
                session_id="sess-1",
                stderr="",
                duration_seconds=1.0,
                error_type=CodexErrorType.NONE,
            ),
        ]

        chunker = CodexChunker(mock_codex, tmp_path)
        options = ChunkingOptions(max_retries=2, retry_delay_s=0.5)

        with patch("cc_spec.rag.chunker.time.sleep") as mock_sleep:
            result = chunker._run_and_parse(
                "test prompt",
                raw_content="test content",
                source_path="test.py",
                source_sha256="abc123",
                options=options,
            )

        # sleep 被调用一次，延迟 0.5 秒
        mock_sleep.assert_called_once_with(0.5)
        assert result.retry_count == 1
