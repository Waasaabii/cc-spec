"""v0.1.5：项目扫描（用于构建/更新 KB）。"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from cc_spec.utils.ignore import DEFAULT_KB_IGNORE_PATTERNS, IgnoreRules

from .models import ScannedFile


@dataclass(frozen=True)
class ScanSettings:
    """扫描设置。"""

    max_file_bytes: int = 512 * 1024  # 512KB
    follow_symlinks: bool = False
    include_untracked: bool = True  # 文件系统扫描默认包含 untracked
    ignore_file_name: str = ".cc-specignore"
    max_report_paths: int = 5000  # 预览输出用：最多记录多少条路径（含原因）


@dataclass(frozen=True)
class ScanReport:
    """可供人类确认的扫描报告（摘要）。"""

    included: int
    excluded: int
    excluded_reasons: dict[str, int]
    sample_included: list[str]
    sample_excluded: list[str]
    excluded_paths: list[str] = field(default_factory=list)


def scan_project(
    project_root: Path,
    *,
    settings: ScanSettings | None = None,
) -> tuple[list[ScannedFile], ScanReport]:
    """扫描项目文件（代码/文档/配置），返回可入库的文件列表与报告。"""
    if settings is None:
        settings = ScanSettings()

    ignore_file = project_root / settings.ignore_file_name
    ignore_rules = IgnoreRules.from_file(ignore_file, extra_patterns=DEFAULT_KB_IGNORE_PATTERNS)

    included_files: list[ScannedFile] = []
    excluded_reasons: dict[str, int] = {}
    sample_included: list[str] = []
    sample_excluded: list[str] = []
    excluded_paths: list[str] = []

    def _exclude(rel_posix: PurePosixPath, reason: str) -> None:
        excluded_reasons[reason] = excluded_reasons.get(reason, 0) + 1
        if len(sample_excluded) < 20:
            sample_excluded.append(f"{rel_posix.as_posix()} ({reason})")
        if len(excluded_paths) < settings.max_report_paths:
            excluded_paths.append(f"{rel_posix.as_posix()} ({reason})")

    for root, dirs, files in os.walk(project_root, topdown=True, followlinks=settings.follow_symlinks):
        root_path = Path(root)
        rel_root = root_path.relative_to(project_root)
        rel_root_posix = PurePosixPath(rel_root.as_posix())

        # 目录过滤（就地修改 dirs 以剪枝）
        kept_dirs: list[str] = []
        for d in dirs:
            rel_dir = (rel_root / d) if rel_root != Path(".") else Path(d)
            rel_dir_posix = PurePosixPath(rel_dir.as_posix())
            if ignore_rules.is_ignored(rel_dir_posix, is_dir=True) and ignore_rules.should_prune_dir(
                rel_dir_posix
            ):
                _exclude(rel_dir_posix, "ignored")
                continue
            kept_dirs.append(d)
        dirs[:] = kept_dirs

        for name in files:
            abs_path = root_path / name
            rel_path = abs_path.relative_to(project_root)
            rel_posix = PurePosixPath(rel_path.as_posix())

            if ignore_rules.is_ignored(rel_posix, is_dir=False):
                _exclude(rel_posix, "ignored")
                continue

            try:
                size_bytes = abs_path.stat().st_size
            except OSError:
                _exclude(rel_posix, "stat_failed")
                continue

            if size_bytes > settings.max_file_bytes:
                _exclude(rel_posix, "too_large")
                included_files.append(
                    ScannedFile(
                        abs_path=abs_path,
                        rel_path=rel_path,
                        size_bytes=size_bytes,
                        sha256=None,
                        is_text=False,
                        is_reference=_is_reference(rel_path),
                        reason="too_large",
                    )
                )
                continue

            # binary/text 检测 + hash
            try:
                data = abs_path.read_bytes()
            except OSError:
                _exclude(rel_posix, "read_failed")
                continue

            if _looks_binary(data):
                _exclude(rel_posix, "binary")
                continue

            sha256 = hashlib.sha256(data).hexdigest()
            scanned = ScannedFile(
                abs_path=abs_path,
                rel_path=rel_path,
                size_bytes=size_bytes,
                sha256=sha256,
                is_text=True,
                is_reference=_is_reference(rel_path),
            )
            included_files.append(scanned)
            if len(sample_included) < 20:
                sample_included.append(rel_posix.as_posix())

    report = ScanReport(
        included=len(included_files),
        excluded=sum(excluded_reasons.values()),
        excluded_reasons=dict(sorted(excluded_reasons.items(), key=lambda x: (-x[1], x[0]))),
        sample_included=sample_included,
        sample_excluded=sample_excluded,
        excluded_paths=excluded_paths,
    )
    return included_files, report


def build_file_hash_map(files: list[ScannedFile]) -> dict[str, str]:
    """将扫描结果转换为 {rel_path: sha256}（仅包含可入库文本）。"""
    result: dict[str, str] = {}
    for f in files:
        if not f.is_text or not f.sha256:
            continue
        if f.reason:
            continue
        result[f.rel_path.as_posix()] = f.sha256
    return result


def diff_file_hash_map(
    old: dict[str, str],
    new: dict[str, str],
) -> tuple[list[str], list[str], list[str]]:
    """返回 (added, changed, removed)。"""
    added = sorted([p for p in new.keys() if p not in old])
    removed = sorted([p for p in old.keys() if p not in new])
    changed = sorted([p for p in new.keys() if p in old and new[p] != old[p]])
    return added, changed, removed


def _looks_binary(data: bytes) -> bool:
    # 简单启发：包含 NUL 字节则认为是二进制
    if b"\x00" in data:
        return True
    return False


def _is_reference(rel_path: Path) -> bool:
    # 约定：路径中包含 reference/ 视为参考资料
    parts = [p.lower() for p in rel_path.parts]
    return "reference" in parts
