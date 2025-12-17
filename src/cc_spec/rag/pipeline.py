"""v0.1.5：KB 构建/增量更新管线（scan → chunk → upsert）。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cc_spec.codex.client import CodexClient

from .chunker import ChunkingOptions, CodexChunker
from .knowledge_base import KnowledgeBase
from .scanner import ScanReport, ScanSettings, build_file_hash_map, diff_file_hash_map, scan_project


@dataclass(frozen=True)
class KBUpdateSummary:
    scanned: int
    added: int
    changed: int
    removed: int
    chunks_written: int
    reference_mode: str


def scan_for_kb(project_root: Path, *, settings: ScanSettings | None = None) -> tuple[list, ScanReport]:
    return scan_project(project_root, settings=settings)


def init_kb(
    project_root: Path,
    *,
    embedding_model: str = "intfloat/multilingual-e5-small",
    reference_mode: str = "index",
    scan_settings: ScanSettings | None = None,
) -> tuple[KBUpdateSummary, ScanReport]:
    scanned, report = scan_project(project_root, settings=scan_settings)
    file_hashes = build_file_hash_map(scanned)

    kb = KnowledgeBase(project_root, embedding_model=embedding_model)
    chunker = CodexChunker(CodexClient(), project_root)

    chunks_written = 0

    # reference 目录结构索引（轻量）
    ref_chunk = chunker.build_reference_index_chunk(scanned)
    kb.upsert_chunks([ref_chunk])
    chunks_written += 1

    options = ChunkingOptions(reference_mode=reference_mode)
    for f in scanned:
        chunks = chunker.chunk_file(f, options=options)
        if not chunks:
            continue
        kb.upsert_chunks(chunks)
        chunks_written += len(chunks)

    kb.update_manifest_files(file_hashes)
    return (
        KBUpdateSummary(
            scanned=len(scanned),
            added=len(file_hashes),
            changed=0,
            removed=0,
            chunks_written=chunks_written,
            reference_mode=reference_mode,
        ),
        report,
    )


def update_kb(
    project_root: Path,
    *,
    embedding_model: str = "intfloat/multilingual-e5-small",
    reference_mode: str = "index",
    scan_settings: ScanSettings | None = None,
) -> tuple[KBUpdateSummary, ScanReport]:
    kb = KnowledgeBase(project_root, embedding_model=embedding_model)
    chunker = CodexChunker(CodexClient(), project_root)

    scanned, report = scan_project(project_root, settings=scan_settings)
    new_hashes = build_file_hash_map(scanned)

    manifest = kb.store.load_manifest()
    old_hashes = manifest.get("files", {})
    if not isinstance(old_hashes, dict):
        old_hashes = {}
    old_hashes_str = {str(k): str(v) for k, v in old_hashes.items()}

    added, changed, removed = diff_file_hash_map(old_hashes_str, new_hashes)

    # 删除移除文件
    for path in removed:
        kb.delete_chunks_for_file(path)

    # 对新增/变化文件重新切片
    options = ChunkingOptions(reference_mode=reference_mode)
    chunks_written = 0
    lookup = {f.rel_path.as_posix(): f for f in scanned}
    for path in added + changed:
        f = lookup.get(path)
        if not f:
            continue
        chunks = chunker.chunk_file(f, options=options)
        if not chunks:
            continue
        kb.upsert_chunks(chunks)
        chunks_written += len(chunks)

    kb.update_manifest_files(new_hashes)

    return (
        KBUpdateSummary(
            scanned=len(scanned),
            added=len(added),
            changed=len(changed),
            removed=len(removed),
            chunks_written=chunks_written,
            reference_mode=reference_mode,
        ),
        report,
    )

