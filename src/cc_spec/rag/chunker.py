"""v0.1.5：通过 Codex 进行语义切片（chunking）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cc_spec.codex.client import CodexClient

from .models import Chunk, ChunkType, ScannedFile
from .prompts import chunk_file_prompt, reference_index_prompt


@dataclass(frozen=True)
class ChunkingOptions:
    """切片策略选项。"""

    reference_mode: str = "index"  # "index" | "full"
    max_content_chars: int = 120_000  # 防止超长输入（约等于几十 KB 文本）


class CodexChunker:
    """使用 Codex 对文本文件进行语义切片。"""

    def __init__(self, codex: CodexClient, project_root: Path) -> None:
        self.codex = codex
        self.project_root = project_root

    def chunk_file(self, scanned: ScannedFile, *, options: ChunkingOptions | None = None) -> list[Chunk]:
        if options is None:
            options = ChunkingOptions()

        if not scanned.is_text or scanned.sha256 is None:
            return []

        rel_path_str = scanned.rel_path.as_posix()
        content = scanned.abs_path.read_text(encoding="utf-8", errors="replace")

        # reference 默认索引级入库，除非指定 full 或是入口文件
        is_entry = scanned.rel_path.name.lower() in {"readme.md", "readme", "install.md"}
        if scanned.is_reference and options.reference_mode == "index" and not is_entry:
            prompt = reference_index_prompt(rel_path=rel_path_str, content=content)
            chunks = self._run_and_parse(prompt, source_path=rel_path_str, source_sha256=scanned.sha256)
            return [
                _finalize_chunk(c, chunk_type=ChunkType.REFERENCE, source_path=rel_path_str, source_sha256=scanned.sha256)
                for c in chunks
            ]

        prompt = chunk_file_prompt(rel_path=rel_path_str, content=content[: options.max_content_chars])
        chunks = self._run_and_parse(prompt, source_path=rel_path_str, source_sha256=scanned.sha256)

        file_type = _infer_chunk_type(scanned.rel_path)
        if scanned.is_reference:
            file_type = ChunkType.REFERENCE

        return [
            _finalize_chunk(c, chunk_type=file_type, source_path=rel_path_str, source_sha256=scanned.sha256)
            for c in chunks
        ]

    def build_reference_index_chunk(self, reference_files: list[ScannedFile]) -> Chunk:
        """构建 reference/** 的目录结构索引（不依赖 Codex）。"""
        paths = sorted(sf.rel_path.as_posix() for sf in reference_files if sf.is_reference)
        text = "\n".join(paths[:5000])
        sha = "reference-index"
        return Chunk(
            chunk_id=f"{sha}:dir",
            text=text,
            summary="reference 目录索引（路径列表）",
            chunk_type=ChunkType.REFERENCE,
            source_path="reference/",
            source_sha256=sha,
            extra={"mode": "dir_index"},
        )

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _run_and_parse(self, prompt: str, *, source_path: str, source_sha256: str) -> list[dict[str, Any]]:
        result = self.codex.execute(prompt, self.project_root)
        if not result.success:
            return [_fallback_chunk_dict(prompt, source_path=source_path, source_sha256=source_sha256)]

        parsed = _extract_json_array(result.message)
        if parsed is None:
            return [_fallback_chunk_dict(result.message, source_path=source_path, source_sha256=source_sha256)]

        chunks: list[dict[str, Any]] = []
        for idx, item in enumerate(parsed):
            normalized = _normalize_chunk_dict(item, idx=idx)
            if normalized:
                chunks.append(normalized)
        return chunks or [_fallback_chunk_dict(result.message, source_path=source_path, source_sha256=source_sha256)]


def _infer_chunk_type(rel_path: Path) -> ChunkType:
    p = rel_path.as_posix().lower()
    if p.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".kt")):
        return ChunkType.CODE
    if p.endswith((".md", ".rst", ".txt")):
        return ChunkType.DOC
    if p.endswith((".yaml", ".yml", ".toml", ".json", ".ini", ".cfg")):
        return ChunkType.CONFIG
    return ChunkType.DOC


def _finalize_chunk(
    item: dict[str, Any],
    *,
    chunk_type: ChunkType,
    source_path: str,
    source_sha256: str,
) -> Chunk:
    idx = int(item.get("_idx", 0))
    raw_id = str(item.get("id", f"chunk_{idx}"))
    chunk_id = f"{source_sha256[:12]}:{idx:04d}:{raw_id}"
    summary = str(item.get("summary", "")).strip()
    content = str(item.get("content", "")).strip()

    start_line = _as_int_or_none(item.get("start_line"))
    end_line = _as_int_or_none(item.get("end_line"))
    language = str(item.get("language")).strip() if item.get("language") else None

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
        language=language,
        extra=extra,
    )


def _as_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _normalize_chunk_dict(item: Any, *, idx: int) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    content = item.get("content")
    summary = item.get("summary")
    if not isinstance(content, str) or not content.strip():
        return None
    if not isinstance(summary, str):
        item["summary"] = ""
    if "id" not in item or not isinstance(item.get("id"), str):
        item["id"] = f"chunk_{idx}"
    if "type" not in item or not isinstance(item.get("type"), str):
        item["type"] = "other"
    item["_idx"] = idx
    return item


def _extract_json_array(text: str) -> list[Any] | None:
    # Codex 有时会输出额外前后缀；尽量提取第一个 [...] JSON 数组
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except Exception:
        return None
    return obj if isinstance(obj, list) else None


def _fallback_chunk_dict(message: str, *, source_path: str, source_sha256: str) -> dict[str, Any]:
    return {
        "id": "fallback",
        "type": "other",
        "summary": f"fallback chunk for {source_path}",
        "content": message[:4000],
        "_idx": 0,
        "_source_sha256": source_sha256,
    }

