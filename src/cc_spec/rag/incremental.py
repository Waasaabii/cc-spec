"""v0.1.6：增量更新辅助（基于 git diff / status）。"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitChangeSet:
    changed: list[str]
    removed: list[str]
    untracked: list[str]


def detect_git_changes(project_root: Path) -> GitChangeSet | None:
    """检测工作区相对 HEAD 的变化文件（含 untracked）。

    返回：
        - GitChangeSet：成功检测到变更
        - None：非 git 仓库 / git 不可用 / 检测失败
    """
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if inside.lower() != "true":
            return None
    except Exception:
        return None

    changed: set[str] = set()
    removed: set[str] = set()

    # 1) tracked: working tree + index vs HEAD
    try:
        out = subprocess.run(
            ["git", "diff", "--name-status", "HEAD"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except Exception:
        out = ""

    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if not parts:
            continue
        status = parts[0].strip()
        if not status:
            continue

        code = status[0]
        if code in {"M", "A", "T", "U"} and len(parts) >= 2:
            changed.add(parts[1].strip())
        elif code == "D" and len(parts) >= 2:
            removed.add(parts[1].strip())
        elif code in {"R", "C"} and len(parts) >= 3:
            old = parts[1].strip()
            new = parts[2].strip()
            if old:
                removed.add(old)
            if new:
                changed.add(new)

    # 2) untracked
    untracked: set[str] = set()
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except Exception:
        out = ""

    for line in out.splitlines():
        if not line.startswith("?? "):
            continue
        p = line[3:].strip()
        if p:
            untracked.add(p)

    # 展开未跟踪目录为文件列表（scan_paths 会跳过目录）
    if untracked:
        expanded_untracked: set[str] = set()
        for p in untracked:
            abs_path = project_root / p
            if abs_path.is_dir():
                for root, _, files in os.walk(abs_path):
                    for name in files:
                        file_path = Path(root) / name
                        try:
                            rel = file_path.relative_to(project_root)
                        except Exception:
                            continue
                        expanded_untracked.add(rel.as_posix())
            else:
                expanded_untracked.add(p)
        untracked = expanded_untracked

    # 防御：去掉空字符串
    changed = {p for p in changed if p}
    removed = {p for p in removed if p}
    untracked = {p for p in untracked if p}

    return GitChangeSet(
        changed=sorted(changed),
        removed=sorted(removed),
        untracked=sorted(untracked),
    )


def get_git_head(project_root: Path) -> str | None:
    """获取当前 git HEAD commit SHA。

    返回：
        - str：成功获取到 HEAD
        - None：非 git 仓库 / git 不可用 / 获取失败
    """
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if inside.lower() != "true":
            return None
    except Exception:
        return None

    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return head if head else None
    except Exception:
        return None


def diff_git_commits(project_root: Path, old: str, new: str) -> GitChangeSet | None:
    """比较两个 commit 之间的文件变更（不包含 untracked）。

    用途：当工作区是 clean（相对 HEAD 没有 diff），但仍需要对比两个快照（commit）时，
    用 commit diff 得到“需要增量处理”的文件列表，避免全量扫描。
    """
    if not old or not new:
        return None

    try:
        out = subprocess.run(
            ["git", "diff", "--name-status", old, new],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except Exception:
        return None

    changed: set[str] = set()
    removed: set[str] = set()

    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if not parts:
            continue
        status = parts[0].strip()
        if not status:
            continue

        code = status[0]
        if code in {"M", "A", "T", "U"} and len(parts) >= 2:
            changed.add(parts[1].strip())
        elif code == "D" and len(parts) >= 2:
            removed.add(parts[1].strip())
        elif code in {"R", "C"} and len(parts) >= 3:
            old_p = parts[1].strip()
            new_p = parts[2].strip()
            if old_p:
                removed.add(old_p)
            if new_p:
                changed.add(new_p)

    changed = {p for p in changed if p}
    removed = {p for p in removed if p}

    return GitChangeSet(
        changed=sorted(changed),
        removed=sorted(removed),
        untracked=[],
    )
