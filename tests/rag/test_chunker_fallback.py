"""测试 chunker.py 中的 fallback 文本切分逻辑。"""

import pytest

from cc_spec.rag.chunker import _simple_text_chunks


class TestSimpleTextChunks:
    """测试 _simple_text_chunks 函数。"""

    def test_empty_content_returns_empty_list(self) -> None:
        """空内容应返回空列表。"""
        result = _simple_text_chunks(
            "",
            source_path="test.py",
            source_sha256="abc123",
        )
        assert result == []

    def test_small_file_returns_single_chunk(self) -> None:
        """小文件（行数 <= lines_per_chunk）应返回单个 chunk。"""
        content = "line1\nline2\nline3\n"
        result = _simple_text_chunks(
            content,
            source_path="test.py",
            source_sha256="abc123",
            lines_per_chunk=100,
        )
        assert len(result) == 1
        assert result[0]["id"] == "fallback_0"
        assert result[0]["start_line"] == 1
        assert result[0]["end_line"] == 3
        assert "fallback chunk for test.py" in result[0]["summary"]
        assert "line1" in result[0]["content"]

    def test_large_file_splits_into_multiple_chunks(self) -> None:
        """大文件应被切分为多个 chunk。"""
        # 创建 250 行的内容
        lines = [f"line {i}\n" for i in range(1, 251)]
        content = "".join(lines)

        result = _simple_text_chunks(
            content,
            source_path="test.py",
            source_sha256="abc123",
            lines_per_chunk=100,
            overlap_lines=10,
        )

        # 250 行，100 行/块，10 行重叠，步长 90
        # 块 0: 1-100, 块 1: 91-190, 块 2: 181-250
        assert len(result) == 3

        # 检查第一个块
        assert result[0]["id"] == "fallback_0"
        assert result[0]["start_line"] == 1
        assert result[0]["end_line"] == 100
        assert "lines 1-100" in result[0]["summary"]

        # 检查第二个块
        assert result[1]["id"] == "fallback_1"
        assert result[1]["start_line"] == 91
        assert result[1]["end_line"] == 190
        assert "lines 91-190" in result[1]["summary"]

        # 检查第三个块
        assert result[2]["id"] == "fallback_2"
        assert result[2]["start_line"] == 181
        assert result[2]["end_line"] == 250
        assert "lines 181-250" in result[2]["summary"]

    def test_chunks_have_correct_idx(self) -> None:
        """每个 chunk 应有正确的 _idx。"""
        lines = [f"line {i}\n" for i in range(1, 201)]
        content = "".join(lines)

        result = _simple_text_chunks(
            content,
            source_path="test.py",
            source_sha256="abc123",
            lines_per_chunk=100,
            overlap_lines=10,
        )

        for idx, chunk in enumerate(result):
            assert chunk["_idx"] == idx

    def test_chunks_contain_source_sha256(self) -> None:
        """每个 chunk 应包含 source_sha256。"""
        content = "line1\nline2\n"
        result = _simple_text_chunks(
            content,
            source_path="test.py",
            source_sha256="test_sha_256",
        )
        assert len(result) == 1
        assert result[0]["_source_sha256"] == "test_sha_256"

    def test_content_truncated_if_too_long(self) -> None:
        """单个 chunk 内容超过 4000 字符应被截断。"""
        # 创建超长行
        long_line = "x" * 5000 + "\n"
        content = long_line

        result = _simple_text_chunks(
            content,
            source_path="test.py",
            source_sha256="abc123",
            lines_per_chunk=100,
        )

        assert len(result) == 1
        assert len(result[0]["content"]) == 4000

    def test_no_overlap_when_overlap_is_zero(self) -> None:
        """overlap_lines=0 时，chunk 之间无重叠。"""
        lines = [f"line {i}\n" for i in range(1, 201)]
        content = "".join(lines)

        result = _simple_text_chunks(
            content,
            source_path="test.py",
            source_sha256="abc123",
            lines_per_chunk=100,
            overlap_lines=0,
        )

        # 200 行，100 行/块，无重叠，应有 2 个块
        assert len(result) == 2
        assert result[0]["start_line"] == 1
        assert result[0]["end_line"] == 100
        assert result[1]["start_line"] == 101
        assert result[1]["end_line"] == 200

    def test_exact_lines_per_chunk_boundary(self) -> None:
        """行数刚好等于 lines_per_chunk 时应返回单个 chunk。"""
        lines = [f"line {i}\n" for i in range(1, 101)]
        content = "".join(lines)

        result = _simple_text_chunks(
            content,
            source_path="test.py",
            source_sha256="abc123",
            lines_per_chunk=100,
        )

        assert len(result) == 1
        assert result[0]["start_line"] == 1
        assert result[0]["end_line"] == 100
