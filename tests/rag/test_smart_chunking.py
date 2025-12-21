"""Tests for SmartChunker strategy selection."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from cc_spec.codex.client import CodexClient
from cc_spec.rag.chunker import CodexChunker
from cc_spec.rag.models import ScannedFile
from cc_spec.rag.smart_chunker import SmartChunker, SmartChunkingOptions


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


def _make_chunker(tmp_path: Path, options: SmartChunkingOptions) -> SmartChunker:
    codex_chunker = CodexChunker(CodexClient(), tmp_path)
    return SmartChunker(codex_chunker, tmp_path, options=options)


def test_select_strategy_llm_priority(tmp_path: Path) -> None:
    options = SmartChunkingOptions(
        strategy="smart",
        llm_enabled=True,
        llm_priority_files=["readme.md"],
        ast_supported_extensions=[".py"],
    )
    chunker = _make_chunker(tmp_path, options)
    scanned = _make_scanned_file(tmp_path, "README.md", "# Title\n")
    assert chunker._select_strategy(scanned) == "llm"


def test_line_strategy_when_ast_disabled(tmp_path: Path) -> None:
    options = SmartChunkingOptions(
        strategy="ast-only",
        llm_enabled=False,
        ast_supported_extensions=[],
    )
    chunker = _make_chunker(tmp_path, options)
    scanned = _make_scanned_file(tmp_path, "notes.txt", "line1\nline2\n")
    result = chunker.chunk_file(scanned)
    assert result.strategy == "line"
    assert result.chunks


def test_ast_strategy_for_python(tmp_path: Path) -> None:
    pytest.importorskip("tree_sitter_language_pack")
    options = SmartChunkingOptions(
        strategy="ast-only",
        llm_enabled=False,
        ast_supported_extensions=[".py"],
    )
    chunker = _make_chunker(tmp_path, options)
    scanned = _make_scanned_file(tmp_path, "main.py", "def foo():\n    return 1\n")
    result = chunker.chunk_file(scanned)
    assert result.strategy == "ast"
    assert result.chunks
