"""Utilities for AST/line chunking and shared chunk helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import Chunk, ChunkType


def infer_chunk_type(rel_path: Path) -> ChunkType:
    p = rel_path.as_posix().lower()
    if p.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".kt")):
        return ChunkType.CODE
    if p.endswith((".md", ".rst", ".txt")):
        return ChunkType.DOC
    if p.endswith((".yaml", ".yml", ".toml", ".json", ".ini", ".cfg")):
        return ChunkType.CONFIG
    return ChunkType.DOC


def _as_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def finalize_chunk(
    item: dict[str, Any],
    *,
    chunk_type: ChunkType,
    source_path: str,
    source_sha256: str,
    language: str | None = None,
) -> Chunk:
    idx = int(item.get("_idx", 0))
    raw_id = str(item.get("id", f"chunk_{idx}"))
    chunk_id = f"{source_sha256[:12]}:{idx:04d}:{raw_id}"
    summary = str(item.get("summary", "")).strip()
    content = str(item.get("content", "")).strip()

    start_line = _as_int_or_none(item.get("start_line"))
    end_line = _as_int_or_none(item.get("end_line"))

    extra = {"raw_type": item.get("type"), "raw_id": raw_id}
    return Chunk(
        chunk_id=chunk_id,
        text=content,
        summary=summary,
        chunk_type=chunk_type,
        source_path=source_path,
        source_sha256=source_sha256,
        start_line=start_line,
        end_line=end_line,
        language=language or item.get("language"),
        extra=extra,
    )


def simple_text_chunks(
    content: str,
    *,
    source_path: str,
    source_sha256: str,
    lines_per_chunk: int = 100,
    overlap_lines: int = 10,
) -> list[dict[str, Any]]:
    """Line-based chunking (fallback for non-AST/LLM)."""
    lines = content.splitlines(keepends=True)
    total_lines = len(lines)

    if total_lines == 0:
        return []

    if total_lines <= lines_per_chunk:
        return [
            {
                "id": "fallback_0",
                "type": "other",
                "summary": f"fallback chunk for {source_path} (lines 1-{total_lines})",
                "content": content[:4000],
                "start_line": 1,
                "end_line": total_lines,
                "_idx": 0,
                "_source_sha256": source_sha256,
            }
        ]

    chunks: list[dict[str, Any]] = []
    step = max(1, lines_per_chunk - overlap_lines)
    idx = 0

    for start in range(0, total_lines, step):
        end = min(start + lines_per_chunk, total_lines)
        chunk_lines = lines[start:end]
        chunk_content = "".join(chunk_lines)

        if len(chunk_content) > 4000:
            chunk_content = chunk_content[:4000]

        chunks.append(
            {
                "id": f"fallback_{idx}",
                "type": "other",
                "summary": f"fallback chunk for {source_path} (lines {start + 1}-{end})",
                "content": chunk_content,
                "start_line": start + 1,
                "end_line": end,
                "_idx": idx,
                "_source_sha256": source_sha256,
            }
        )
        idx += 1

        if end >= total_lines:
            break

    return chunks
