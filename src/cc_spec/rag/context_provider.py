"""v0.1.6：智能上下文提供者（Smart Context）。

目标：
- 自动从 KB 检索并注入最相关的上下文片段
- 支持多 query 合并去重、来源统计、token 估算
- 为 apply/plan 等工作流提供统一的上下文构建入口
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from cc_spec.utils.files import get_cc_spec_dir

from .knowledge_base import KnowledgeBase

DEFAULT_EMBEDDING_MODEL = "intfloat/multilingual-e5-small"


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
    - 当前实现只依赖 KB（向量库）；related_files 走少量本地读取（可控范围）。
    - 对于 query 结果，优先按距离排序并在全局层面去重（按 chunk_id）。
    """

    def __init__(
        self,
        project_root: Path,
        *,
        kb: KnowledgeBase | None = None,
        embedding_model: str | None = None,
        cache_ttl_s: int = 300,
        cache_enabled: bool = True,
    ) -> None:
        self.project_root = project_root
        self._kb = kb
        self._embedding_model = embedding_model
        self._cache_ttl_s = cache_ttl_s
        self._cache_enabled = cache_enabled
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def get_context_for_task(
        self,
        task_id: str,
        config: ContextConfig | None = None,
    ) -> InjectedContext:
        """为指定任务构建上下文。

        task_id 仅用于追溯/展示；检索行为由 config 控制。
        """
        cfg = config or ContextConfig()

        # 1) 相关文件（manual/hybrid）
        manual_chunks: list[ContextChunk] = []
        if cfg.mode in ("manual", "hybrid") and cfg.related_files:
            manual_chunks = self._read_related_files(cfg.related_files)

        # 2) KB 向量检索（auto/hybrid）
        query_results: dict[str, list[ContextChunk]] = {}
        kb_chunks: list[ContextChunk] = []
        if cfg.mode in ("auto", "hybrid") and cfg.queries:
            for q in cfg.queries:
                res = self._kb_query(q, n=max(cfg.max_chunks, 1), where=cfg.where)
                chunks = self._convert_query_result(res)
                query_results[q] = chunks
                kb_chunks.extend(chunks)

        # 3) 合并去重 + 排序
        merged: dict[str, ContextChunk] = {}
        for c in manual_chunks + kb_chunks:
            existing = merged.get(c.chunk_id)
            if existing is None:
                merged[c.chunk_id] = c
                continue
            # 对同一 id，保留距离更小（更相关）的那个
            if existing.distance is None:
                merged[c.chunk_id] = c
            elif c.distance is not None and c.distance < existing.distance:
                merged[c.chunk_id] = c

        items = list(merged.values())
        items.sort(key=lambda c: (c.distance is None, c.distance if c.distance is not None else 1e9))
        items = items[: max(cfg.max_chunks, 1)]

        md = InjectedContext(chunks=items, total_tokens=0, sources=[], query_results=query_results).to_markdown()
        total_tokens = _estimate_tokens(md)
        sources = sorted({c.source_path for c in items if c.source_path})

        return InjectedContext(
            chunks=items,
            total_tokens=total_tokens,
            sources=sources,
            query_results=query_results,
        )

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _get_kb(self) -> KnowledgeBase:
        if self._kb is not None:
            return self._kb
        # 允许注入 embedding_model；否则从 manifest/config 读取，回退默认值
        model = _resolve_embedding_model(self.project_root, override=self._embedding_model)
        self._kb = KnowledgeBase(self.project_root, embedding_model=model)
        return self._kb

    def _cache_key(self, *, query: str, n: int, where: dict[str, Any] | None) -> str:
        return f"q={query}\nn={n}\nwhere={where!r}"

    def _kb_query(self, query: str, *, n: int, where: dict[str, Any] | None) -> dict[str, Any]:
        key = self._cache_key(query=query, n=n, where=where)
        if self._cache_enabled:
            cached = self._cache.get(key)
            if cached:
                ts, payload = cached
                if time.time() - ts <= self._cache_ttl_s:
                    return payload

        kb = self._get_kb()
        payload = kb.query(query, n=n, where=where, collection="chunks")
        if self._cache_enabled:
            self._cache[key] = (time.time(), payload)
        return payload

    def _convert_query_result(self, res: dict[str, Any]) -> list[ContextChunk]:
        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]

        if not isinstance(ids, list) or not isinstance(docs, list) or not isinstance(metas, list):
            return []

        items: list[ContextChunk] = []
        for i in range(min(len(ids), len(docs), len(metas))):
            meta = metas[i] if isinstance(metas[i], dict) else {}
            source_path = str(meta.get("source_path", ""))
            chunk_type = str(meta.get("type", ""))
            summary = str(meta.get("summary", "")) if meta.get("summary") is not None else ""
            content = str(docs[i]) if docs[i] is not None else ""
            dist_val: float | None = None
            if isinstance(dists, list) and i < len(dists):
                try:
                    dist_val = float(dists[i])
                except Exception:
                    dist_val = None
            items.append(
                ContextChunk(
                    chunk_id=str(ids[i]),
                    distance=dist_val,
                    source_path=source_path,
                    chunk_type=chunk_type,
                    summary=summary,
                    content=content,
                )
            )
        return items

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

    # windows path 可能包含 `C:\...`，只解析最后一个 `:` 右侧是否为数字范围
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


def _resolve_embedding_model(project_root: Path, *, override: str | None) -> str:
    if isinstance(override, str) and override.strip():
        return override.strip()
    model = _read_embedding_model_from_manifest(project_root)
    if model:
        return model
    model = _read_embedding_model_from_config(project_root)
    if model:
        return model
    return DEFAULT_EMBEDDING_MODEL


def _read_embedding_model_from_manifest(project_root: Path) -> str | None:
    cc_spec_root = get_cc_spec_dir(project_root)
    manifest = cc_spec_root / "kb.manifest.json"
    if not manifest.exists():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    embedding = data.get("embedding")
    if isinstance(embedding, dict):
        model = embedding.get("model")
        if isinstance(model, str) and model.strip():
            return model.strip()
    return None


def _read_embedding_model_from_config(project_root: Path) -> str | None:
    cc_spec_root = get_cc_spec_dir(project_root)
    config_path = cc_spec_root / "config.yaml"
    if not config_path.exists():
        return None
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    kb = data.get("kb")
    if isinstance(kb, dict):
        model = kb.get("embedding_model")
        if isinstance(model, str) and model.strip():
            return model.strip()
        embedding = kb.get("embedding")
        if isinstance(embedding, dict):
            model = embedding.get("model") or embedding.get("embedding_model")
            if isinstance(model, str) and model.strip():
                return model.strip()
    model = data.get("embedding_model")
    if isinstance(model, str) and model.strip():
        return model.strip()
    return None
