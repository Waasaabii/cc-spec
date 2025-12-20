"""v0.1.5：通过 Codex 进行语义切片（chunking）。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cc_spec.codex.client import CodexClient
from cc_spec.codex.models import CodexErrorType

from .models import Chunk, ChunkResult, ChunkStatus, ChunkType, ScannedFile
from .prompts import chunk_file_prompt, chunk_files_prompt, reference_index_prompt


@dataclass(frozen=True)
class ChunkingOptions:
    """切片策略选项。"""

    reference_mode: str = "index"  # "index" | "full"
    max_content_chars: int = 120_000  # 防止超长输入（约等于几十 KB 文本）
    # fallback 文本切分配置
    fallback_lines_per_chunk: int = 100  # 每个 fallback chunk 的行数
    fallback_overlap_lines: int = 10  # 重叠行数
    # 重试配置
    max_retries: int = 2  # 超时时最大重试次数
    retry_delay_s: float = 1.0  # 重试间隔（秒）


@dataclass
class _ParseResult:
    """内部解析结果（用于 _run_and_parse 传递状态）。"""

    chunk_dicts: list[dict[str, Any]]
    status: ChunkStatus
    error_message: str | None = None
    exit_code: int | None = None
    retry_count: int = 0  # 实际重试次数


class CodexChunker:
    """使用 Codex 对文本文件进行语义切片。"""

    def __init__(self, codex: CodexClient, project_root: Path) -> None:
        self.codex = codex
        self.project_root = project_root

    def chunk_files(
        self, scanned_files: list[ScannedFile], *, options: ChunkingOptions | None = None
    ) -> list[ChunkResult]:
        """对多个文件批量切片（一次 Codex 调用）。

        目的：减少 `codex exec` 的启动/上下文准备开销。
        返回结果顺序与输入一致。
        """
        if options is None:
            options = ChunkingOptions()

        if not scanned_files:
            return []

        prepared: list[dict[str, str]] = []
        raw_by_path: dict[str, str] = {}
        sha_by_path: dict[str, str] = {}
        type_by_path: dict[str, ChunkType] = {}

        # 非文本/不可入库文件：保持与 chunk_file 一致的行为（返回空 chunks）
        passthrough: list[ChunkResult] = []

        for scanned in scanned_files:
            rel_path_str = scanned.rel_path.as_posix()

            if not scanned.is_text or scanned.sha256 is None:
                passthrough.append(
                    ChunkResult(
                        chunks=[],
                        status=ChunkStatus.SUCCESS,
                        source_path=rel_path_str,
                    )
                )
                continue

            raw_content = scanned.abs_path.read_text(encoding="utf-8", errors="replace")
            raw_by_path[rel_path_str] = raw_content
            sha_by_path[rel_path_str] = scanned.sha256

            # reference 默认索引级入库，除非指定 full 或是入口文件
            is_entry = scanned.rel_path.name.lower() in {"readme.md", "readme", "install.md"}
            if scanned.is_reference and options.reference_mode == "index" and not is_entry:
                prepared.append(
                    {
                        "path": rel_path_str,
                        "mode": "reference_index",
                        "content": raw_content[:8000],
                    }
                )
                type_by_path[rel_path_str] = ChunkType.REFERENCE
                continue

            prepared.append(
                {
                    "path": rel_path_str,
                    "mode": "chunk",
                    "content": raw_content[: options.max_content_chars],
                }
            )

            file_type = _infer_chunk_type(scanned.rel_path)
            if scanned.is_reference:
                file_type = ChunkType.REFERENCE
            type_by_path[rel_path_str] = file_type

        # 若没有可切片内容，直接返回 passthrough
        if not prepared:
            return passthrough

        prompt_files: list[dict[str, str]] = []
        for item in prepared:
            prompt_files.append(
                {
                    "path": item["path"],
                    "mode": item["mode"],
                    "content": item["content"],
                }
            )
        prompt = chunk_files_prompt(files=prompt_files)

        # 执行 Codex，支持超时重试（与 _run_and_parse 行为一致，但作用于批量）
        last_result = None
        for attempt in range(options.max_retries + 1):
            result = self.codex.execute(prompt, self.project_root)
            last_result = result
            if result.success:
                break
            if result.error_type != CodexErrorType.TIMEOUT:
                break
            if attempt < options.max_retries:
                time.sleep(options.retry_delay_s)

        assert last_result is not None
        result = last_result

        def _fallback_chunks_for(path: str) -> list[dict[str, Any]]:
            raw = raw_by_path.get(path, "")
            sha = sha_by_path.get(path, "")
            chunks = _simple_text_chunks(
                raw,
                source_path=path,
                source_sha256=sha,
                lines_per_chunk=options.fallback_lines_per_chunk,
                overlap_lines=options.fallback_overlap_lines,
            )
            if not chunks:
                chunks = [_fallback_chunk_dict(raw, source_path=path, source_sha256=sha)]
            return chunks

        # 执行失败：对所有 prepared 文件 fallback
        if not result.success:
            out: list[ChunkResult] = []
            for item in prepared:
                path = str(item["path"])
                sha = sha_by_path.get(path, "")
                typ = type_by_path.get(path, ChunkType.DOC)
                dicts = _fallback_chunks_for(path)
                chunks = [
                    _finalize_chunk(c, chunk_type=typ, source_path=path, source_sha256=sha) for c in dicts
                ]
                out.append(
                    ChunkResult(
                        chunks=chunks,
                        status=ChunkStatus.FALLBACK_EXEC,
                        source_path=path,
                        error_message=result.message or result.stderr,
                        codex_exit_code=result.exit_code,
                    )
                )
            return _merge_passthrough(scanned_files, passthrough=passthrough, prepared_results=out)

        parsed = _extract_json_array(result.message)
        if parsed is None:
            out = []
            for item in prepared:
                path = str(item["path"])
                sha = sha_by_path.get(path, "")
                typ = type_by_path.get(path, ChunkType.DOC)
                dicts = _fallback_chunks_for(path)
                chunks = [
                    _finalize_chunk(c, chunk_type=typ, source_path=path, source_sha256=sha) for c in dicts
                ]
                out.append(
                    ChunkResult(
                        chunks=chunks,
                        status=ChunkStatus.FALLBACK_PARSE,
                        source_path=path,
                        error_message=f"Failed to parse JSON from Codex output: {result.message[:200]}",
                        codex_exit_code=result.exit_code,
                    )
                )
            return _merge_passthrough(scanned_files, passthrough=passthrough, prepared_results=out)

        # 支持：单文件时 Codex 误输出为 “chunks array” 而非 wrapper array
        by_path: dict[str, list[Any]] = {}
        if parsed and isinstance(parsed[0], dict) and ("chunks" in parsed[0] or "path" in parsed[0]):
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                path_val = item.get("path") or item.get("file") or item.get("rel_path")
                chunks_val = item.get("chunks")
                if isinstance(path_val, str) and isinstance(chunks_val, list):
                    by_path[path_val] = chunks_val
        elif len(prepared) == 1:
            by_path[str(prepared[0]["path"])] = parsed

        out: list[ChunkResult] = []
        for item in prepared:
            path = str(item["path"])
            sha = sha_by_path.get(path, "")
            typ = type_by_path.get(path, ChunkType.DOC)

            chunks_raw = by_path.get(path)
            if chunks_raw is None:
                chunks_raw = by_path.get(path.replace("/", "\\"))

            if not isinstance(chunks_raw, list):
                dicts = _fallback_chunks_for(path)
                chunks = [
                    _finalize_chunk(c, chunk_type=typ, source_path=path, source_sha256=sha) for c in dicts
                ]
                out.append(
                    ChunkResult(
                        chunks=chunks,
                        status=ChunkStatus.FALLBACK_EMPTY,
                        source_path=path,
                        error_message="Codex batch output missing file entry",
                        codex_exit_code=result.exit_code,
                    )
                )
                continue

            normalized: list[dict[str, Any]] = []
            for idx, ch in enumerate(chunks_raw):
                n = _normalize_chunk_dict(ch, idx=idx)
                if n:
                    normalized.append(n)

            if not normalized:
                dicts = _fallback_chunks_for(path)
                chunks = [
                    _finalize_chunk(c, chunk_type=typ, source_path=path, source_sha256=sha) for c in dicts
                ]
                out.append(
                    ChunkResult(
                        chunks=chunks,
                        status=ChunkStatus.FALLBACK_EMPTY,
                        source_path=path,
                        error_message="Codex returned empty chunks after normalization",
                        codex_exit_code=result.exit_code,
                    )
                )
                continue

            chunks = [
                _finalize_chunk(c, chunk_type=typ, source_path=path, source_sha256=sha) for c in normalized
            ]
            out.append(
                ChunkResult(
                    chunks=chunks,
                    status=ChunkStatus.SUCCESS,
                    source_path=path,
                    codex_exit_code=result.exit_code,
                )
            )

        return _merge_passthrough(scanned_files, passthrough=passthrough, prepared_results=out)

    def chunk_file(self, scanned: ScannedFile, *, options: ChunkingOptions | None = None) -> ChunkResult:
        if options is None:
            options = ChunkingOptions()

        rel_path_str = scanned.rel_path.as_posix()

        if not scanned.is_text or scanned.sha256 is None:
            return ChunkResult(
                chunks=[],
                status=ChunkStatus.SUCCESS,
                source_path=rel_path_str,
            )

        content = scanned.abs_path.read_text(encoding="utf-8", errors="replace")

        # reference 默认索引级入库，除非指定 full 或是入口文件
        is_entry = scanned.rel_path.name.lower() in {"readme.md", "readme", "install.md"}
        if scanned.is_reference and options.reference_mode == "index" and not is_entry:
            prompt = reference_index_prompt(rel_path=rel_path_str, content=content)
            parsed = self._run_and_parse(
                prompt,
                raw_content=content,
                source_path=rel_path_str,
                source_sha256=scanned.sha256,
                options=options,
            )
            chunks = [
                _finalize_chunk(c, chunk_type=ChunkType.REFERENCE, source_path=rel_path_str, source_sha256=scanned.sha256)
                for c in parsed.chunk_dicts
            ]
            return ChunkResult(
                chunks=chunks,
                status=parsed.status,
                source_path=rel_path_str,
                error_message=parsed.error_message,
                codex_exit_code=parsed.exit_code,
            )

        prompt = chunk_file_prompt(rel_path=rel_path_str, content=content[: options.max_content_chars])
        parsed = self._run_and_parse(
            prompt,
            raw_content=content,
            source_path=rel_path_str,
            source_sha256=scanned.sha256,
            options=options,
        )

        file_type = _infer_chunk_type(scanned.rel_path)
        if scanned.is_reference:
            file_type = ChunkType.REFERENCE

        chunks = [
            _finalize_chunk(c, chunk_type=file_type, source_path=rel_path_str, source_sha256=scanned.sha256)
            for c in parsed.chunk_dicts
        ]
        return ChunkResult(
            chunks=chunks,
            status=parsed.status,
            source_path=rel_path_str,
            error_message=parsed.error_message,
            codex_exit_code=parsed.exit_code,
        )

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

    def _run_and_parse(
        self,
        prompt: str,
        *,
        raw_content: str,
        source_path: str,
        source_sha256: str,
        options: ChunkingOptions,
    ) -> _ParseResult:
        retry_count = 0
        last_result = None

        # 执行 Codex，支持超时重试
        for attempt in range(options.max_retries + 1):
            result = self.codex.execute(prompt, self.project_root)
            last_result = result

            # 成功执行，跳出重试循环
            if result.success:
                break

            # 只对超时错误进行重试
            if result.error_type != CodexErrorType.TIMEOUT:
                break

            # 还有重试机会
            if attempt < options.max_retries:
                retry_count += 1
                time.sleep(options.retry_delay_s)
            # 否则结束重试

        # 此时 last_result 一定不为 None
        assert last_result is not None
        result = last_result

        if not result.success:
            fallback_chunks = _simple_text_chunks(
                raw_content,
                source_path=source_path,
                source_sha256=source_sha256,
                lines_per_chunk=options.fallback_lines_per_chunk,
                overlap_lines=options.fallback_overlap_lines,
            )
            # 如果切分失败（空内容），使用单个 fallback chunk
            if not fallback_chunks:
                fallback_chunks = [_fallback_chunk_dict(raw_content, source_path=source_path, source_sha256=source_sha256)]
            return _ParseResult(
                chunk_dicts=fallback_chunks,
                status=ChunkStatus.FALLBACK_EXEC,
                error_message=result.message or result.stderr,
                exit_code=result.exit_code,
                retry_count=retry_count,
            )

        parsed = _extract_json_array(result.message)
        if parsed is None:
            fallback_chunks = _simple_text_chunks(
                raw_content,
                source_path=source_path,
                source_sha256=source_sha256,
                lines_per_chunk=options.fallback_lines_per_chunk,
                overlap_lines=options.fallback_overlap_lines,
            )
            if not fallback_chunks:
                fallback_chunks = [_fallback_chunk_dict(raw_content, source_path=source_path, source_sha256=source_sha256)]
            return _ParseResult(
                chunk_dicts=fallback_chunks,
                status=ChunkStatus.FALLBACK_PARSE,
                error_message=f"Failed to parse JSON from Codex output: {result.message[:200]}",
                exit_code=result.exit_code,
                retry_count=retry_count,
            )

        chunks: list[dict[str, Any]] = []
        for idx, item in enumerate(parsed):
            normalized = _normalize_chunk_dict(item, idx=idx)
            if normalized:
                chunks.append(normalized)

        if not chunks:
            fallback_chunks = _simple_text_chunks(
                raw_content,
                source_path=source_path,
                source_sha256=source_sha256,
                lines_per_chunk=options.fallback_lines_per_chunk,
                overlap_lines=options.fallback_overlap_lines,
            )
            if not fallback_chunks:
                fallback_chunks = [_fallback_chunk_dict(raw_content, source_path=source_path, source_sha256=source_sha256)]
            return _ParseResult(
                chunk_dicts=fallback_chunks,
                status=ChunkStatus.FALLBACK_EMPTY,
                error_message="Codex returned empty chunks after normalization",
                exit_code=result.exit_code,
                retry_count=retry_count,
            )

        return _ParseResult(
            chunk_dicts=chunks,
            status=ChunkStatus.SUCCESS,
            exit_code=result.exit_code,
            retry_count=retry_count,
        )


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


def _simple_text_chunks(
    content: str,
    *,
    source_path: str,
    source_sha256: str,
    lines_per_chunk: int = 100,
    overlap_lines: int = 10,
) -> list[dict[str, Any]]:
    """基于行的简单文本切分（用于 Codex 失败时的 fallback）。

    Args:
        content: 文件内容
        source_path: 文件相对路径
        source_sha256: 文件 SHA256
        lines_per_chunk: 每个 chunk 的目标行数
        overlap_lines: 相邻 chunk 的重叠行数

    Returns:
        chunk dict 列表，每个 dict 包含 id, type, summary, content, start_line, end_line
    """
    lines = content.splitlines(keepends=True)
    total_lines = len(lines)

    if total_lines == 0:
        return []

    # 小文件直接返回单个 chunk
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

        # 限制单个 chunk 内容长度
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

        # 如果已经到文件末尾，停止
        if end >= total_lines:
            break

    return chunks


def _merge_passthrough(
    scanned_files: list[ScannedFile],
    *,
    passthrough: list[ChunkResult],
    prepared_results: list[ChunkResult],
) -> list[ChunkResult]:
    """将 batch 结果按输入顺序合并回去。

    `prepared_results` 与 `prepared` 的顺序一致；
    `passthrough` 保存的是非文本/不可切片文件的结果。
    """
    by_path: dict[str, ChunkResult] = {}
    for r in passthrough:
        by_path[r.source_path] = r
    for r in prepared_results:
        by_path[r.source_path] = r

    out: list[ChunkResult] = []
    for f in scanned_files:
        key = f.rel_path.as_posix()
        r = by_path.get(key)
        if r is None:
            # 理论上不应发生；兜底为 “空成功”
            out.append(ChunkResult(chunks=[], status=ChunkStatus.SUCCESS, source_path=key))
            continue
        out.append(r)
    return out
