"""v0.2.x：智能上下文提供者（Smart Context）。

目标：
- 不依赖额外索引服务：基于多级文本索引（PROJECT_INDEX / FOLDER_INDEX）与手动文件引用构建上下文
- 支持 tasks.yaml 的 context 配置：queries / related_files / mode / max_chunks
- 输出可直接注入 prompt 的 Markdown（尽量短）
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


PROJECT_INDEX_NAME = "PROJECT_INDEX.md"
FOLDER_INDEX_NAME = "FOLDER_INDEX.md"


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数量（用于统计展示，不用于计费/精确控制）。"""
    if not text:
        return 0
    chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 1.5 + other_chars / 4)


@dataclass(frozen=True)
class ContextConfig:
    """任务/变更的上下文配置。"""

    queries: list[str] = field(default_factory=list)
    related_files: list[str] = field(default_factory=list)
    max_chunks: int = 10
    mode: Literal["auto", "manual", "hybrid"] = "auto"
    where: dict[str, Any] | None = None


@dataclass(frozen=True)
class ContextChunk:
    """注入上下文中的单个 chunk（对外暴露的精简结构）。"""

    chunk_id: str
    distance: float | None
    source_path: str
    chunk_type: str
    summary: str
    content: str


@dataclass(frozen=True)
class InjectedContext:
    """注入的上下文结果。"""

    chunks: list[ContextChunk]
    total_tokens: int
    sources: list[str]
    query_results: dict[str, list[ContextChunk]] = field(default_factory=dict)

    def to_markdown(self, *, max_items: int | None = None, max_chars: int = 800) -> str:
        """渲染为可直接注入 prompt 的 Markdown（尽量短）。"""
        items = self.chunks[: max_items] if max_items else self.chunks
        lines: list[str] = []
        for i, c in enumerate(items, start=1):
            title = f"### {i}) {c.source_path} ({c.chunk_type})"
            if c.distance is not None:
                title += f"  [dist={c.distance:.4f}]"
            lines.append(title)
            if c.summary:
                lines.append(f"Summary: {c.summary}")
            snippet = (c.content or "").strip()
            if snippet:
                snippet = snippet[:max_chars].rstrip()
                lines.append("```text")
                lines.append(snippet)
                lines.append("```")
            lines.append("")
        return "\n".join(lines).strip()


class ContextProvider:
    """智能上下文提供者。

说明：
- v0.2.x 起不再依赖向量检索；默认注入 PROJECT_INDEX.md。
- manual/hybrid 模式下支持按 `path[:start-end]` 读取少量文件片段。
"""

    def __init__(
        self,
        project_root: Path,
        *,
        cache_ttl_s: int = 300,
        cache_enabled: bool = True,
    ) -> None:
        self.project_root = project_root
        self._cache_ttl_s = cache_ttl_s
        self._cache_enabled = cache_enabled
        self._cache: dict[str, tuple[float, str]] = {}

    def get_context_for_task(
        self,
        task_id: str,
        config: ContextConfig | None = None,
    ) -> InjectedContext:
        """为指定任务构建上下文。

task_id 仅用于追溯/展示；上下文内容由 config 控制。
"""
        _ = task_id
        cfg = config or ContextConfig()

        chunks: list[ContextChunk] = []

        if cfg.mode in ("auto", "hybrid"):
            chunks.extend(self._read_project_index())

        if cfg.mode in ("manual", "hybrid") and cfg.related_files:
            chunks.extend(self._read_related_files(cfg.related_files))
            chunks.extend(self._read_folder_indexes_for_refs(cfg.related_files))

        # 合并去重（保留首次出现）
        merged: dict[str, ContextChunk] = {}
        for c in chunks:
            if c.chunk_id in merged:
                continue
            merged[c.chunk_id] = c

        items = list(merged.values())
        items = items[: max(cfg.max_chunks, 1)]

        md = InjectedContext(chunks=items, total_tokens=0, sources=[], query_results={}).to_markdown()
        total_tokens = _estimate_tokens(md)
        sources = sorted({c.source_path for c in items if c.source_path})

        return InjectedContext(
            chunks=items,
            total_tokens=total_tokens,
            sources=sources,
            query_results={},
        )

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _read_text_file(self, path: Path, *, max_lines: int) -> str:
        key = path.as_posix()
        if self._cache_enabled:
            cached = self._cache.get(key)
            if cached:
                ts, text = cached
                if time.time() - ts <= self._cache_ttl_s:
                    return text

        if not path.exists() or not path.is_file():
            return ""
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return ""

        text = "\n".join(lines[:max_lines]).strip()
        if self._cache_enabled:
            self._cache[key] = (time.time(), text)
        return text

    def _read_project_index(self) -> list[ContextChunk]:
        path = self.project_root / PROJECT_INDEX_NAME
        content = self._read_text_file(path, max_lines=260)
        if not content:
            return []
        return [
            ContextChunk(
                chunk_id=f"index:{PROJECT_INDEX_NAME}",
                distance=None,
                source_path=PROJECT_INDEX_NAME,
                chunk_type="index.project",
                summary="Project structure overview (auto-generated index)",
                content=content,
            )
        ]

    def _read_folder_indexes_for_refs(self, refs: list[str]) -> list[ContextChunk]:
        root = self.project_root.resolve()
        folders: list[Path] = []
        seen: set[str] = set()

        for raw in refs:
            path_str, _, _ = _parse_file_ref(raw)
            if not path_str:
                continue
            rel_candidate = Path(path_str)
            if rel_candidate.is_absolute():
                continue
            if any(part == ".." for part in rel_candidate.parts):
                continue

            abs_path = (root / rel_candidate).resolve()
            try:
                abs_path.relative_to(root)
            except Exception:
                continue

            folder = abs_path.parent
            key = folder.as_posix().lower()
            if key in seen:
                continue
            seen.add(key)
            folders.append(folder)

        chunks: list[ContextChunk] = []
        for folder in folders:
            idx = folder / FOLDER_INDEX_NAME
            content = self._read_text_file(idx, max_lines=220)
            if not content:
                continue
            try:
                rel = idx.relative_to(root).as_posix()
            except Exception:
                rel = idx.as_posix()
            chunks.append(
                ContextChunk(
                    chunk_id=f"index:{rel}",
                    distance=None,
                    source_path=rel,
                    chunk_type="index.folder",
                    summary="Folder file list (auto-generated index)",
                    content=content,
                )
            )
        return chunks

    def _read_related_files(self, refs: list[str]) -> list[ContextChunk]:
        """将 related_files 引用转成少量可注入片段。"""
        chunks: list[ContextChunk] = []
        root = self.project_root.resolve()
        for raw in refs:
            path_str, start, end = _parse_file_ref(raw)
            if not path_str:
                continue
            rel_candidate = Path(path_str)
            # 安全限制：只允许项目根目录内的相对路径，拒绝绝对路径与 ".." 逃逸
            if rel_candidate.is_absolute():
                continue
            if any(part == ".." for part in rel_candidate.parts):
                continue
            abs_path = (root / rel_candidate).resolve()
            try:
                rel_path = abs_path.relative_to(root).as_posix()
            except Exception:
                continue

            if not abs_path.exists() or not abs_path.is_file():
                continue
            try:
                lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue

            snippet = _slice_lines(lines, start=start, end=end, max_lines=200)
            if not snippet.strip():
                continue

            chunk_id = f"file:{rel_path}:{start or ''}-{end or ''}"
            chunks.append(
                ContextChunk(
                    chunk_id=chunk_id,
                    distance=None,
                    source_path=f"{rel_path}:{start}-{end}" if start and end else rel_path,
                    chunk_type="manual",
                    summary="Manually linked file reference",
                    content=snippet,
                )
            )
        return chunks


def _parse_file_ref(raw: str) -> tuple[str, int | None, int | None]:
    """解析 `path[:start-end]` 形式的引用。"""
    s = (raw or "").strip()
    if not s:
        return ("", None, None)

    # windows path 可能包含 `C:\\...`，只解析最后一个 `:` 右侧是否为数字范围
    if ":" not in s:
        return (s, None, None)

    path_part, tail = s.rsplit(":", 1)
    tail = tail.strip()
    if not tail:
        return (s, None, None)

    # 单行或行范围
    if "-" in tail:
        a, b = tail.split("-", 1)
        try:
            start = int(a.strip())
            end = int(b.strip())
            if start <= 0 or end <= 0:
                return (s, None, None)
            if end < start:
                start, end = end, start
            return (path_part, start, end)
        except Exception:
            return (s, None, None)
    try:
        line = int(tail)
        if line <= 0:
            return (s, None, None)
        return (path_part, line, line)
    except Exception:
        return (s, None, None)


def _slice_lines(lines: list[str], *, start: int | None, end: int | None, max_lines: int) -> str:
    if not lines:
        return ""
    if start is None or end is None:
        # 没有行号：取前 max_lines 行作为兜底
        return "\n".join(lines[:max_lines])

    start_i = max(start - 1, 0)
    end_i = min(end, len(lines))
    sliced = lines[start_i:end_i]
    if len(sliced) > max_lines:
        sliced = sliced[:max_lines]
    return "\n".join(sliced)
