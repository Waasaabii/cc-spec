"""v0.1.5：KB 构建/增量更新管线（scan → chunk → upsert）。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from cc_spec.codex.client import CodexClient

from .chunker import ChunkingOptions, CodexChunker
from .incremental import detect_git_changes, diff_git_commits, get_git_head
from .knowledge_base import KnowledgeBase
from .models import Chunk, ChunkResult, ChunkStatus, ScannedFile
from .scanner import ScanReport, ScanSettings, build_file_hash_map, diff_file_hash_map, scan_paths, scan_project


# 进度回调类型：(当前索引, 总数, 文件路径, ChunkResult)
ProgressCallback = Callable[[int, int, str, ChunkResult], None]

DEFAULT_CODEX_BATCH_MAX_FILES = 8
DEFAULT_CODEX_BATCH_MAX_CHARS = 120_000


def _estimate_prompt_chars(scanned: ScannedFile, *, options: ChunkingOptions) -> int:
    """估算 batch prompt 中该文件占用的字符数（粗略上界）。"""
    if not scanned.is_text or scanned.sha256 is None or scanned.reason:
        return 0
    # reference 默认索引级入库，除非指定 full 或是入口文件
    is_entry = scanned.rel_path.name.lower() in {"readme.md", "readme", "install.md"}
    if scanned.is_reference and options.reference_mode == "index" and not is_entry:
        return min(scanned.size_bytes, 8000)
    return min(scanned.size_bytes, options.max_content_chars)


def _flush_batch(
    batch: list[ScannedFile],
    *,
    chunker: CodexChunker,
    options: ChunkingOptions,
) -> list[ChunkResult]:
    if not batch:
        return []
    if len(batch) == 1:
        return [chunker.chunk_file(batch[0], options=options)]
    return chunker.chunk_files(batch, options=options)


@dataclass(frozen=True)
class KBUpdateSummary:
    scanned: int
    added: int
    changed: int
    removed: int
    chunks_written: int
    reference_mode: str
    # v0.1.6: 切片质量统计
    chunking_success: int = 0
    chunking_fallback: int = 0
    fallback_files: tuple[str, ...] = ()


def scan_for_kb(project_root: Path, *, settings: ScanSettings | None = None) -> tuple[list, ScanReport]:
    return scan_project(project_root, settings=settings)


def init_kb(
    project_root: Path,
    *,
    embedding_model: str = "intfloat/multilingual-e5-small",
    reference_mode: str = "index",
    codex_batch_max_files: int = DEFAULT_CODEX_BATCH_MAX_FILES,
    codex_batch_max_chars: int = DEFAULT_CODEX_BATCH_MAX_CHARS,
    scan_settings: ScanSettings | None = None,
    attribution: dict[str, Any] | None = None,
    skip_list_fields: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> tuple[KBUpdateSummary, ScanReport]:
    scanned, report = scan_project(project_root, settings=scan_settings)
    file_hashes = build_file_hash_map(scanned)

    kb = KnowledgeBase(project_root, embedding_model=embedding_model)
    chunker = CodexChunker(CodexClient(), project_root)

    chunks_written = 0

    # reference 目录结构索引（轻量）
    ref_chunk = chunker.build_reference_index_chunk(scanned)
    kb.upsert_chunks([ref_chunk], attribution=attribution, skip_list_fields=skip_list_fields)
    chunks_written += 1

    options = ChunkingOptions(reference_mode=reference_mode)
    chunking_success = 0
    chunking_fallback = 0
    fallback_files: list[str] = []
    total_files = len(scanned)

    batch: list[ScannedFile] = []
    batch_chars = 0
    batch_indices: list[int] = []

    def process_batch() -> None:
        nonlocal chunks_written, chunking_success, chunking_fallback, batch, batch_chars, batch_indices
        if not batch:
            return
        results = _flush_batch(batch, chunker=chunker, options=options)

        # 逐文件回调与统计（保持 idx/total 一致）
        collected: list[Chunk] = []
        for f, idx, res in zip(batch, batch_indices, results, strict=True):
            if progress_callback is not None:
                progress_callback(idx, total_files, f.rel_path.as_posix(), res)

            if not res.chunks:
                continue

            if res.status == ChunkStatus.SUCCESS:
                chunking_success += 1
            else:
                chunking_fallback += 1
                fallback_files.append(res.source_path)

            collected.extend(res.chunks)

        if collected:
            kb.upsert_chunks(collected, attribution=attribution, skip_list_fields=skip_list_fields)
            chunks_written += len(collected)

        batch = []
        batch_chars = 0
        batch_indices = []

    for idx, f in enumerate(scanned):
        # 不可入库文件：保持原逻辑（仍输出进度，但不触发 Codex）
        if not f.is_text or f.sha256 is None or f.reason:
            process_batch()
            res = chunker.chunk_file(f, options=options)
            if progress_callback is not None:
                progress_callback(idx, total_files, f.rel_path.as_posix(), res)
            continue

        est = _estimate_prompt_chars(f, options=options)
        if batch and (
            len(batch) >= codex_batch_max_files or batch_chars + est > codex_batch_max_chars
        ):
            process_batch()

        batch.append(f)
        batch_indices.append(idx)
        batch_chars += est

    process_batch()

    # v0.1.6：记录当前 git HEAD 与 dirty 状态（用于后续增量更新的正确性）
    worktree = detect_git_changes(project_root)
    kb.update_manifest_files(
        file_hashes,
        git_head=get_git_head(project_root),
        git_dirty=(
            bool(worktree.changed or worktree.removed or worktree.untracked)
            if worktree is not None
            else None
        ),
    )
    return (
        KBUpdateSummary(
            scanned=len(scanned),
            added=len(file_hashes),
            changed=0,
            removed=0,
            chunks_written=chunks_written,
            reference_mode=reference_mode,
            chunking_success=chunking_success,
            chunking_fallback=chunking_fallback,
            fallback_files=tuple(fallback_files),
        ),
        report,
    )


def update_kb(
    project_root: Path,
    *,
    embedding_model: str = "intfloat/multilingual-e5-small",
    reference_mode: str = "index",
    codex_batch_max_files: int = DEFAULT_CODEX_BATCH_MAX_FILES,
    codex_batch_max_chars: int = DEFAULT_CODEX_BATCH_MAX_CHARS,
    scan_settings: ScanSettings | None = None,
    attribution: dict[str, Any] | None = None,
    skip_list_fields: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> tuple[KBUpdateSummary, ScanReport]:
    kb = KnowledgeBase(project_root, embedding_model=embedding_model)
    chunker = CodexChunker(CodexClient(), project_root)

    manifest = kb.store.load_manifest()
    old_hashes = manifest.get("files", {})
    if not isinstance(old_hashes, dict):
        old_hashes = {}
    old_hashes_str = {str(k): str(v) for k, v in old_hashes.items()}

    # v0.1.6：优先使用 git 增量（仅处理变化文件），失败则回退到全量 scan
    worktree_set = detect_git_changes(project_root)
    worktree_dirty = (
        bool(worktree_set.changed or worktree_set.removed or worktree_set.untracked)
        if worktree_set is not None
        else None
    )
    current_head = get_git_head(project_root)

    # manifest 记录的 git 状态（若存在）
    stored_head: str | None = None
    stored_dirty: bool | None = None
    git_meta = manifest.get("git") if isinstance(manifest, dict) else None
    if isinstance(git_meta, dict):
        sh = git_meta.get("head")
        if isinstance(sh, str) and sh.strip():
            stored_head = sh.strip()
        sd = git_meta.get("dirty")
        if isinstance(sd, bool):
            stored_dirty = sd

    change_set = worktree_set

    # 工作区 clean：仍需处理 “HEAD 变化但工作区无 diff” 的情况（否则 KB 会滞后）
    if worktree_set is not None and not (worktree_set.changed or worktree_set.removed or worktree_set.untracked):
        # 仅在能证明 manifest 已同步到当前 HEAD 且当时也是 clean 时才快速返回
        if (
            stored_head
            and current_head
            and stored_head == current_head
            and stored_dirty is False
        ):
            empty_report = ScanReport(
                included=0,
                excluded=0,
                excluded_reasons={},
                sample_included=[],
                sample_excluded=[],
                excluded_paths=[],
            )
            return (
                KBUpdateSummary(
                    scanned=0,
                    added=0,
                    changed=0,
                    removed=0,
                    chunks_written=0,
                    reference_mode=reference_mode,
                ),
                empty_report,
            )

        # 若 manifest 记录了旧 head，尝试用 commit diff 作为增量列表，避免全量 scan
        if stored_head and current_head and stored_head != current_head:
            commit_set = diff_git_commits(project_root, stored_head, current_head)
            change_set = commit_set if commit_set is not None else None
        else:
            change_set = None

    if change_set is not None and (change_set.changed or change_set.removed or change_set.untracked):
        settings = scan_settings or ScanSettings()
        scan_list = list(dict.fromkeys([*change_set.changed, *change_set.untracked]))
        scanned, report = scan_paths(project_root, scan_list, settings=settings)
        partial_hashes = build_file_hash_map(scanned)

        # 变化但不可入库（ignored/binary/too_large）且历史入库过：视为 removed
        removed_set = {p for p in change_set.removed if p in old_hashes_str}
        for p in scan_list:
            if p in old_hashes_str and p not in partial_hashes:
                removed_set.add(p)

        added = sorted([p for p, sha in partial_hashes.items() if p not in old_hashes_str])
        changed = sorted([p for p, sha in partial_hashes.items() if p in old_hashes_str and old_hashes_str[p] != sha])
        removed = sorted(removed_set)

        # 删除移除文件
        for path in removed:
            kb.delete_chunks_for_file(path, attribution=attribution)

        # 对新增/变化文件重新切片
        options = ChunkingOptions(reference_mode=reference_mode)
        chunks_written = 0
        chunking_success = 0
        chunking_fallback = 0
        fallback_files: list[str] = []

        lookup = {f.rel_path.as_posix(): f for f in scanned}
        paths_to_process = added + changed
        total_files = len(paths_to_process)
        ordered: list[ScannedFile] = []
        ordered_paths: list[str] = []
        for path in paths_to_process:
            f = lookup.get(path)
            if f:
                ordered.append(f)
                ordered_paths.append(path)

        batch: list[ScannedFile] = []
        batch_chars = 0
        batch_start_idx = 0

        def process_batch(start_idx: int) -> int:
            nonlocal chunks_written, chunking_success, chunking_fallback, batch, batch_chars
            if not batch:
                return start_idx
            results = _flush_batch(batch, chunker=chunker, options=options)

            collected: list[Chunk] = []
            for offset, (f, res) in enumerate(zip(batch, results, strict=True)):
                idx = start_idx + offset
                path = ordered_paths[idx]
                if progress_callback is not None:
                    progress_callback(idx, total_files, path, res)

                if not res.chunks:
                    continue

                if res.status == ChunkStatus.SUCCESS:
                    chunking_success += 1
                else:
                    chunking_fallback += 1
                    fallback_files.append(res.source_path)

                collected.extend(res.chunks)

            if collected:
                kb.upsert_chunks(collected, attribution=attribution, skip_list_fields=skip_list_fields)
                chunks_written += len(collected)

            next_idx = start_idx + len(batch)
            batch = []
            batch_chars = 0
            return next_idx

        for f in ordered:
            est = _estimate_prompt_chars(f, options=options)
            if batch and (
                len(batch) >= codex_batch_max_files or batch_chars + est > codex_batch_max_chars
            ):
                batch_start_idx = process_batch(batch_start_idx)

            batch.append(f)
            batch_chars += est

        batch_start_idx = process_batch(batch_start_idx)

        # 合并更新 manifest（仅改动部分）
        merged_hashes = dict(old_hashes_str)
        for p in removed:
            merged_hashes.pop(p, None)
        for p, sha in partial_hashes.items():
            merged_hashes[p] = sha

        kb.update_manifest_files(
            merged_hashes,
            git_head=current_head,
            git_dirty=worktree_dirty,
        )

        return (
            KBUpdateSummary(
                scanned=len(scanned),
                added=len(added),
                changed=len(changed),
                removed=len(removed),
                chunks_written=chunks_written,
                reference_mode=reference_mode,
                chunking_success=chunking_success,
                chunking_fallback=chunking_fallback,
                fallback_files=tuple(fallback_files),
            ),
            report,
        )

    # fallback：全量 scan + diff
    scanned, report = scan_project(project_root, settings=scan_settings)
    new_hashes = build_file_hash_map(scanned)
    added, changed, removed = diff_file_hash_map(old_hashes_str, new_hashes)

    # 删除移除文件
    for path in removed:
        kb.delete_chunks_for_file(path, attribution=attribution)

    # 对新增/变化文件重新切片
    options = ChunkingOptions(reference_mode=reference_mode)
    chunks_written = 0
    chunking_success = 0
    chunking_fallback = 0
    fallback_files: list[str] = []

    lookup = {f.rel_path.as_posix(): f for f in scanned}
    paths_to_process = added + changed
    total_files = len(paths_to_process)
    ordered: list[ScannedFile] = []
    ordered_paths: list[str] = []
    for path in paths_to_process:
        f = lookup.get(path)
        if f:
            ordered.append(f)
            ordered_paths.append(path)

    batch: list[ScannedFile] = []
    batch_chars = 0
    batch_start_idx = 0

    def process_batch(start_idx: int) -> int:
        nonlocal chunks_written, chunking_success, chunking_fallback, batch, batch_chars
        if not batch:
            return start_idx
        results = _flush_batch(batch, chunker=chunker, options=options)

        collected: list[Chunk] = []
        for offset, (f, res) in enumerate(zip(batch, results, strict=True)):
            idx = start_idx + offset
            path = ordered_paths[idx]
            if progress_callback is not None:
                progress_callback(idx, total_files, path, res)

            if not res.chunks:
                continue

            if res.status == ChunkStatus.SUCCESS:
                chunking_success += 1
            else:
                chunking_fallback += 1
                fallback_files.append(res.source_path)

            collected.extend(res.chunks)

        if collected:
            kb.upsert_chunks(collected, attribution=attribution, skip_list_fields=skip_list_fields)
            chunks_written += len(collected)

        next_idx = start_idx + len(batch)
        batch = []
        batch_chars = 0
        return next_idx

    for f in ordered:
        est = _estimate_prompt_chars(f, options=options)
        if batch and (
            len(batch) >= codex_batch_max_files or batch_chars + est > codex_batch_max_chars
        ):
            batch_start_idx = process_batch(batch_start_idx)

        batch.append(f)
        batch_chars += est

    batch_start_idx = process_batch(batch_start_idx)

    kb.update_manifest_files(
        new_hashes,
        git_head=current_head,
        git_dirty=worktree_dirty,
    )

    return (
        KBUpdateSummary(
            scanned=len(scanned),
            added=len(added),
            changed=len(changed),
            removed=len(removed),
            chunks_written=chunks_written,
            reference_mode=reference_mode,
            chunking_success=chunking_success,
            chunking_fallback=chunking_fallback,
            fallback_files=tuple(fallback_files),
        ),
        report,
    )
