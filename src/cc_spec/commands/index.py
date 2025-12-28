"""多级索引（Project Multi-level Index）相关命令。

背景：
- v0.2.x 起，项目结构理解不再依赖向量库，而是通过多级索引文件：
  - PROJECT_INDEX.md（项目根索引）
  - FOLDER_INDEX.md（文件夹索引）
  - （可选）文件头注释（L3，默认不修改源文件）

本模块提供：
- `cc-spec init-index`：初始化索引
- `cc-spec update-index`：更新索引（目前等价于 init-index，保留接口）
- `cc-spec check-index`：一致性检查（轻量）
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import typer
from rich.console import Console

from cc_spec.core.standards_renderer import write_managed_file
from cc_spec.utils.ignore import DEFAULT_SCAN_IGNORE_PATTERNS, IgnoreRules

console = Console()

PROJECT_INDEX_NAME = "PROJECT_INDEX.md"
FOLDER_INDEX_NAME = "FOLDER_INDEX.md"

SUPPORTED_CODE_EXTENSIONS: set[str] = {
    # JS/TS
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".mjs",
    ".cjs",
    # Python
    ".py",
    # JVM
    ".java",
    ".kt",
    # Systems
    ".rs",
    ".go",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".php",
    ".rb",
    ".swift",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_levels(levels: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for raw in levels or []:
        v = (raw or "").strip().lower()
        if not v:
            continue
        if v.startswith("l") and len(v) == 2 and v[1].isdigit():
            normalized.append(v)
            continue
        if v in {"1", "2", "3"}:
            normalized.append(f"l{v}")
            continue
    # 默认推荐 L1+L2
    if not normalized:
        normalized = ["l1", "l2"]
    # 去重、保持顺序
    seen: set[str] = set()
    result: list[str] = []
    for v in normalized:
        if v not in {"l1", "l2", "l3"}:
            continue
        if v in seen:
            continue
        seen.add(v)
        result.append(v)
    return result or ["l1", "l2"]


def _build_ignore_rules(project_root: Path) -> IgnoreRules:
    ignore_file = project_root / ".cc-specignore"
    extra = list(DEFAULT_SCAN_IGNORE_PATTERNS)
    # 索引文件本身也要忽略，避免自举污染扫描统计
    extra.extend([PROJECT_INDEX_NAME, FOLDER_INDEX_NAME])
    extra.extend([".cc-spec/index/"])
    return IgnoreRules.from_file(ignore_file, extra_patterns=extra)


def _iter_code_files(project_root: Path) -> list[Path]:
    rules = _build_ignore_rules(project_root)
    result: list[Path] = []

    # 遍历时用 posix 相对路径匹配
    def rel_posix(path: Path) -> PurePosixPath:
        return PurePosixPath(path.relative_to(project_root).as_posix())

    for root, dirs, files in _walk(project_root):
        rel_dir = rel_posix(root)
        if rel_dir.as_posix() and rules.should_prune_dir(rel_dir):
            dirs[:] = []
            continue

        # 过滤子目录（避免进入被剪枝目录）
        kept_dirs: list[str] = []
        for d in dirs:
            p = root / d
            if rules.should_prune_dir(rel_posix(p)):
                continue
            kept_dirs.append(d)
        dirs[:] = kept_dirs

        for name in files:
            p = root / name
            rel = rel_posix(p)
            if rules.is_ignored(rel, is_dir=False):
                continue
            if p.suffix.lower() not in SUPPORTED_CODE_EXTENSIONS:
                continue
            result.append(p)

    result.sort(key=lambda p: p.as_posix().lower())
    return result


def _walk(project_root: Path):
    # Path.rglob 在 Windows 大仓库上会慢；使用 os.walk 风格实现
    import os

    for root, dirs, files in os.walk(project_root):
        yield Path(root), dirs, files


def _group_files_by_folder(project_root: Path, files: list[Path]) -> dict[Path, list[Path]]:
    grouped: dict[Path, list[Path]] = {}
    for p in files:
        folder = p.parent
        grouped.setdefault(folder, []).append(p)
    # 排序
    for folder, items in grouped.items():
        items.sort(key=lambda x: x.name.lower())
    return dict(sorted(grouped.items(), key=lambda kv: kv[0].as_posix().lower()))


def _render_folder_index(
    *,
    project_root: Path,
    folder: Path,
    files: list[Path],
) -> str:
    rel = folder.relative_to(project_root).as_posix().rstrip("/")
    title = f"{rel}/" if rel else "./"
    lines: list[str] = []
    lines.append(f"## 📁 {title}")
    lines.append("")
    lines.append("**Files**：")
    for f in files:
        lines.append(f"- `{f.name}`")
    lines.append("")
    lines.append(
        "🔁 **自指声明**：当本文件夹内文件发生变化时，请更新本索引与 PROJECT_INDEX.md。"
    )
    return "\n".join(lines).strip() + "\n"


def _render_project_index(
    *,
    project_root: Path,
    folders: list[Path],
    files: list[Path],
) -> str:
    project_name = project_root.name
    lines: list[str] = []
    lines.append(f"# {project_name} - Project Index")
    lines.append("")
    lines.append("## 🧭 Project Overview")
    lines.append("")
    lines.append("（由 cc-spec 多级索引系统自动生成，可在受管理区块外补充说明。）")
    lines.append("")
    lines.append("## 🗂️ Directory Structure")
    lines.append("")
    # 简单树：按相对路径列出有索引的文件夹
    for folder in folders:
        rel = folder.relative_to(project_root).as_posix().rstrip("/")
        if not rel:
            continue
        lines.append(f"- `{rel}/`")
    lines.append("")
    lines.append("## 📊 Statistics")
    lines.append("")
    lines.append(f"- Total folders: {len([f for f in folders if f != project_root])}")
    lines.append(f"- Total files: {len(files)}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("🔁 **自指声明**：当项目结构变化时，请更新本索引。")
    lines.append("")
    lines.append("Generated by cc-spec (Project Multi-level Index).")
    return "\n".join(lines).strip() + "\n"


@dataclass(frozen=True)
class IndexManifest:
    version: str
    generated_at: str
    levels: list[str]
    files: list[str]
    folders: list[str]

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "levels": list(self.levels),
            "files": list(self.files),
            "folders": list(self.folders),
        }


def _write_manifest(project_root: Path, manifest: IndexManifest) -> Path:
    cc_spec_dir = project_root / ".cc-spec"
    index_dir = cc_spec_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    path = index_dir / "manifest.json"
    path.write_text(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _write_status(project_root: Path, *, levels: list[str], file_count: int) -> Path:
    cc_spec_dir = project_root / ".cc-spec"
    index_dir = cc_spec_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    status_path = index_dir / "status.json"
    payload = {
        "initialized": True,
        "last_updated": _utc_now_iso(),
        "file_count": int(file_count),
        "index_version": "0.2.2",
        "levels": {
            "l1_summary": "l1" in levels,
            "l2_symbols": "l2" in levels,
            "l3_details": "l3" in levels,
        },
    }
    status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return status_path


def init_index_command(
    path: Path = typer.Option(Path.cwd(), "--path", "-p", help="项目根目录（默认：当前目录）"),
    level: list[str] = typer.Option(
        [],
        "--level",
        "-L",
        help="索引层级：l1=PROJECT_INDEX，l2=FOLDER_INDEX，l3=文件头注释（当前默认不修改源码）",
    ),
    silent: bool = typer.Option(False, "--silent", help="减少输出"),
    json_output: bool = typer.Option(False, "--json", help="输出 summary JSON（便于 tool 解析）"),
) -> None:
    project_root = path.resolve()
    if not project_root.exists() or not project_root.is_dir():
        raise typer.BadParameter(f"项目路径不存在或不是目录: {project_root}")

    levels = _normalize_levels(level)

    if not silent:
        console.print(f"[cyan]Index[/cyan] 初始化多级索引：root={project_root} levels={levels}")

    code_files = _iter_code_files(project_root)
    grouped = _group_files_by_folder(project_root, code_files)
    folders = list(grouped.keys())

    if not silent:
        console.print(f"[green]✓[/green] 扫描完成：files={len(code_files)} folders={len(folders)}")

    # 1) folder indexes（L2）
    if "l2" in levels:
        for folder, files in grouped.items():
            # 根目录不生成 FOLDER_INDEX（避免与 PROJECT_INDEX 重叠）
            if folder == project_root:
                continue
            content = _render_folder_index(project_root=project_root, folder=folder, files=files)
            write_managed_file(folder / FOLDER_INDEX_NAME, content)
        if not silent:
            console.print(f"[green]✓[/green] 已生成/更新 {FOLDER_INDEX_NAME}（count={len([f for f in folders if f != project_root])}）")

    # 2) project index（L1）
    if "l1" in levels:
        content = _render_project_index(project_root=project_root, folders=folders, files=code_files)
        write_managed_file(project_root / PROJECT_INDEX_NAME, content)
        if not silent:
            console.print(f"[green]✓[/green] 已生成/更新 {PROJECT_INDEX_NAME}")

    # 3) L3（预留）：默认不修改源码，只写入 manifest/status 标记
    if "l3" in levels and not silent:
        console.print("[yellow]i[/yellow] L3（文件头注释）当前默认不修改源码，仅记录到 manifest/status。")

    rel_files = [p.relative_to(project_root).as_posix() for p in code_files]
    rel_folders = [p.relative_to(project_root).as_posix().rstrip("/") for p in folders if p != project_root]
    manifest = IndexManifest(
        version="0.2.2",
        generated_at=_utc_now_iso(),
        levels=levels,
        files=rel_files,
        folders=rel_folders,
    )
    manifest_path = _write_manifest(project_root, manifest)
    status_path = _write_status(project_root, levels=levels, file_count=len(code_files))

    if not silent:
        console.print(f"[green]✓[/green] 已写入 manifest：{manifest_path}")
        console.print(f"[green]✓[/green] 已写入 status：{status_path}")

    if json_output:
        console.print(
            json.dumps(
                {
                    "success": True,
                    "project_root": str(project_root),
                    "levels": levels,
                    "files": len(code_files),
                    "folders": len(rel_folders),
                    "project_index": PROJECT_INDEX_NAME,
                    "folder_index": FOLDER_INDEX_NAME,
                    "manifest": str(manifest_path),
                    "status": str(status_path),
                },
                ensure_ascii=False,
            )
        )


def update_index_command(
    path: Path = typer.Option(Path.cwd(), "--path", "-p", help="项目根目录（默认：当前目录）"),
    level: list[str] = typer.Option(
        [],
        "--level",
        "-L",
        help="索引层级：l1=PROJECT_INDEX，l2=FOLDER_INDEX，l3=文件头注释（当前默认不修改源码）",
    ),
    file: Path | None = typer.Option(None, "--file", help="（预留）仅更新与该文件相关的索引"),
    silent: bool = typer.Option(False, "--silent", help="减少输出"),
) -> None:
    # 当前实现：等价于 init-index，保留接口以兼容 hook / 后续增量更新。
    _ = file
    init_index_command(path=path, level=level, silent=silent, json_output=False)


def check_index_command(
    path: Path = typer.Option(Path.cwd(), "--path", "-p", help="项目根目录（默认：当前目录）"),
    json_output: bool = typer.Option(False, "--json", help="输出 JSON 结果"),
) -> None:
    project_root = path.resolve()
    project_index = project_root / PROJECT_INDEX_NAME
    cc_spec_status = project_root / ".cc-spec" / "index" / "status.json"
    ok = project_index.exists() and cc_spec_status.exists()
    payload = {
        "ok": bool(ok),
        "project_index": str(project_index),
        "status": str(cc_spec_status),
        "missing": [
            name
            for name, exists in [
                (PROJECT_INDEX_NAME, project_index.exists()),
                (".cc-spec/index/status.json", cc_spec_status.exists()),
            ]
            if not exists
        ],
    }
    if json_output:
        console.print(json.dumps(payload, ensure_ascii=False))
    else:
        if ok:
            console.print("[green]✓[/green] 索引文件齐全")
        else:
            console.print("[red]✗[/red] 索引文件缺失")
            for missing in payload["missing"]:
                console.print(f"- missing: {missing}")
