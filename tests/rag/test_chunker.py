"""Tests for chunker retry, fallback parse, and path normalization."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from cc_spec.codex.models import CodexErrorType, CodexResult
from cc_spec.rag.chunker import ChunkingOptions, CodexChunker
from cc_spec.rag.models import ChunkStatus, ScannedFile


def _make_scanned_file(tmp_path: Path, rel_path: str, content: str) -> ScannedFile:
    abs_path = tmp_path / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(content, encoding="utf-8")
    data = content.encode("utf-8")
    sha256 = hashlib.sha256(data).hexdigest()
    return ScannedFile(
        abs_path=abs_path,
        rel_path=Path(rel_path),
        size_bytes=len(data),
        sha256=sha256,
        is_text=True,
        is_reference=False,
    )


def test_run_and_parse_retries_on_timeout(tmp_path: Path) -> None:
    mock_codex = MagicMock()
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
            message='[{"id": "1", "summary": "ok", "content": "hello"}]',
            session_id="sess-1",
            stderr="",
            duration_seconds=1.0,
            error_type=CodexErrorType.NONE,
        ),
    ]

    chunker = CodexChunker(mock_codex, tmp_path)
    options = ChunkingOptions(max_retries=1, retry_delay_s=0.01)

    with patch("cc_spec.rag.chunker.time.sleep"):
        result = chunker._run_and_parse(
            "prompt",
            raw_content="line1\nline2\n",
            source_path="foo.txt",
            source_sha256="abc123",
            options=options,
        )

    assert mock_codex.execute.call_count == 2
    assert result.status == ChunkStatus.SUCCESS
    assert result.retry_count == 1


def test_run_and_parse_fallback_on_parse_error(tmp_path: Path) -> None:
    mock_codex = MagicMock()
    mock_codex.execute.return_value = CodexResult(
        success=True,
        exit_code=0,
        message="not-json",
        session_id="sess-1",
        stderr="",
        duration_seconds=1.0,
        error_type=CodexErrorType.NONE,
    )

    chunker = CodexChunker(mock_codex, tmp_path)
    options = ChunkingOptions()

    result = chunker._run_and_parse(
        "prompt",
        raw_content="line1\nline2\n",
        source_path="foo.txt",
        source_sha256="abc123",
        options=options,
    )

    assert result.status == ChunkStatus.FALLBACK_PARSE
    assert result.chunk_dicts
    assert result.error_message is not None
    assert result.error_message.startswith("Failed to parse JSON")
    assert result.chunk_dicts[0]["id"].startswith("fallback")


def test_chunk_files_normalizes_paths(tmp_path: Path) -> None:
    file_a = _make_scanned_file(tmp_path, "foo/bar.txt", "alpha\n")
    file_b = _make_scanned_file(tmp_path, "baz/qux.txt", "beta\n")

    payload = [
        {
            "path": "./foo/bar.txt",
            "chunks": [{"id": "a", "summary": "s1", "content": "c1"}],
        },
        {
            "path": "baz\\qux.txt",
            "chunks": [{"id": "b", "summary": "s2", "content": "c2"}],
        },
    ]

    mock_codex = MagicMock()
    mock_codex.execute.return_value = CodexResult(
        success=True,
        exit_code=0,
        message=json.dumps(payload),
        session_id="sess-1",
        stderr="",
        duration_seconds=1.0,
        error_type=CodexErrorType.NONE,
    )

    chunker = CodexChunker(mock_codex, tmp_path)
    results = chunker.chunk_files([file_a, file_b])

    assert [r.status for r in results] == [ChunkStatus.SUCCESS, ChunkStatus.SUCCESS]
    assert results[0].chunks[0].source_path == "foo/bar.txt"
    assert results[1].chunks[0].source_path == "baz/qux.txt"
    assert results[0].chunks[0].text == "c1"
    assert results[1].chunks[0].text == "c2"
