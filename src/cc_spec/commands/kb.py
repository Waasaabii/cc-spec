"""v0.1.5：KB（向量库）相关命令。

命令族：`cc-spec kb ...`
- init：全量建库（文件清单预览 → Codex 语义切片 → upsert）
- update：增量更新（基于 manifest 文件 hash）
- query：向量检索（chunks/records）
- context：输出给 Codex 可直接使用的上下文片段
- record：写入工作流记录（可追溯）
- compact：将 events 合并为 snapshot，并更新 manifest
- status：查看 KB 状态
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cc_spec.rag.knowledge_base import KnowledgeBase, new_record_id
from cc_spec.rag.models import WorkflowRecord, WorkflowStep
from cc_spec.rag.pipeline import init_kb, update_kb
from cc_spec.rag.scanner import ScanSettings, build_file_hash_map, scan_project
from cc_spec.utils.files import find_project_root, get_cc_spec_dir

console = Console()
kb_app = typer.Typer(name="kb", help="KB（向量库）相关命令", no_args_is_help=True)


def _require_project_root() -> Path:
    project_root = find_project_root()
    if project_root is None:
        console.print("[red]错误：[/red] 这不是 cc-spec 项目，请先运行 `cc-spec init`。")
        raise typer.Exit(1)
    return project_root


def _default_embedding_model(project_root: Path) -> str:
    cc_spec_root = get_cc_spec_dir(project_root)
    manifest = cc_spec_root / "kb.manifest.json"
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            model = data.get("embedding", {}).get("model")
            if isinstance(model, str) and model.strip():
                return model.strip()
        except Exception:
            pass
    return "intfloat/multilingual-e5-small"


@kb_app.command("status")
def kb_status() -> None:
    """查看 KB 状态（manifest + 文件存在性）。"""
    project_root = _require_project_root()
    cc_spec_root = get_cc_spec_dir(project_root)
    paths = {
        "vectordb": cc_spec_root / "vectordb",
        "events": cc_spec_root / "kb.events.jsonl",
        "snapshot": cc_spec_root / "kb.snapshot.jsonl",
        "manifest": cc_spec_root / "kb.manifest.json",
    }

    table = Table(title="KB 状态", show_lines=True)
    table.add_column("项目")
    table.add_column("路径")
    table.add_column("存在")
    for name, path in paths.items():
        label = {
            "vectordb": "向量库",
            "events": "事件日志",
            "snapshot": "快照",
            "manifest": "清单",
        }.get(name, name)
        table.add_row(label, str(path.relative_to(project_root)), "是" if path.exists() else "否")
    console.print(table)


def _reason_zh(reason: str) -> str:
    return {
        "ignored": "忽略规则",
        "binary": "二进制文件",
        "too_large": "文件过大",
        "stat_failed": "无法读取文件信息",
        "read_failed": "无法读取文件内容",
    }.get(reason, reason)


def _preview_ingest_files(scanned: list[Any]) -> list[str]:
    """严格模式：返回“真正会触发 Codex 语义切片并写入向量库”的文件路径列表。"""
    # build_file_hash_map 只会包含：is_text=True 且 sha256 存在，且无 reason 的文件
    file_hashes = build_file_hash_map(scanned)  # type: ignore[arg-type]
    return sorted(file_hashes.keys())


def _print_preview_report(
    project_root: Path,
    *,
    scanned: list[Any],
    report: Any,
    max_file_bytes: int,
) -> None:
    ingest_paths = _preview_ingest_files(scanned)
    ingest_count = len(ingest_paths)

    console.print(
        Panel.fit(
            "\n".join(
                [
                    "说明：",
                    "- 预览（扫描）= 统计文件清单（忽略规则/大小/hash），不调用 Codex",
                    "- 入库 = 对待入库文件调用 Codex 语义切片，然后写入向量库",
                    "",
                    f"本次预览：",
                    f"- 待入库：{ingest_count} 个文件（将触发 Codex 语义切片）",
                    f"- 排除：{report.excluded} 个文件",
                    f"- 单文件上限：{max_file_bytes} bytes",
                ]
            ),
            title="文件清单预览",
        )
    )

    if getattr(report, "excluded_reasons", None):
        t = Table(title="排除原因")
        t.add_column("原因")
        t.add_column("数量")
        for k, v in report.excluded_reasons.items():
            t.add_row(_reason_zh(str(k)), str(v))
        console.print(t)

    # 待入库文件清单：尽可能详细（默认最多展示前 2000 条）
    if ingest_paths:
        max_show = 2000
        shown = ingest_paths[:max_show]
        t_inc = Table(title=f"待入库文件（展示前 {len(shown)} / 共 {ingest_count}）")
        t_inc.add_column("序号")
        t_inc.add_column("路径")
        for i, p in enumerate(shown, start=1):
            t_inc.add_row(str(i), p)
        console.print(t_inc)

    # 排除文件清单：尽可能详细（若 report.excluded_paths 存在则优先使用）
    excluded_paths = getattr(report, "excluded_paths", None) or getattr(report, "sample_excluded", None) or []
    if excluded_paths:
        max_show = 2000
        shown = list(excluded_paths)[:max_show]
        more = max(0, len(excluded_paths) - len(shown))
        title = f"排除文件（展示前 {len(shown)} / 共 {len(excluded_paths)}）"
        if more > 0:
            title += f"，剩余 {more} 条未展示"
        t_exc = Table(title=title)
        t_exc.add_column("序号")
        t_exc.add_column("路径（原因）")
        for i, p in enumerate(shown, start=1):
            t_exc.add_row(str(i), str(p))
        console.print(t_exc)


@kb_app.command("preview")
def kb_preview(
    max_file_bytes: int = typer.Option(512 * 1024, "--max-bytes", help="单文件最大扫描字节数"),
) -> None:
    """预览将入库的文件清单（不执行入库）。"""
    project_root = _require_project_root()
    scanned, report = scan_project(project_root, settings=ScanSettings(max_file_bytes=max_file_bytes))
    _print_preview_report(project_root, scanned=scanned, report=report, max_file_bytes=max_file_bytes)


@kb_app.command("scan")
def kb_scan(
    max_file_bytes: int = typer.Option(512 * 1024, "--max-bytes", help="单文件最大扫描字节数"),
) -> None:
    """（兼容）预览将入库的文件清单（不执行入库）。"""
    kb_preview(max_file_bytes=max_file_bytes)


@kb_app.command("init")
def kb_init(
    embedding_model: Optional[str] = typer.Option(None, "--model", help="Embedding 模型"),
    reference_mode: str = typer.Option("index", "--reference-mode", help="reference 入库模式：index/full"),
    max_file_bytes: int = typer.Option(512 * 1024, "--max-bytes", help="单文件最大扫描字节数"),
    preview_only: bool = typer.Option(
        False,
        "--preview-only",
        "--report-only",
        help="只预览文件清单，不执行入库",
    ),
) -> None:
    """全量构建/刷新 KB。"""
    project_root = _require_project_root()
    model = embedding_model or _default_embedding_model(project_root)

    if preview_only:
        kb_preview(max_file_bytes=max_file_bytes)
        raise typer.Exit(0)

    summary, report = init_kb(
        project_root,
        embedding_model=model,
        reference_mode=reference_mode,
        scan_settings=ScanSettings(max_file_bytes=max_file_bytes),
    )
    console.print(
        Panel.fit(
            "\n".join(
                [
                    f"扫描候选：{summary.scanned} 个文件",
                    f"已入库文件：{summary.added} 个（已调用 Codex 语义切片）",
                    f"写入切片：{summary.chunks_written} 个",
                    f"reference 模式：{summary.reference_mode}",
                    f"排除：{report.excluded} 个文件",
                ]
            ),
            title="KB 构建完成",
        )
    )


@kb_app.command("update")
def kb_update(
    embedding_model: Optional[str] = typer.Option(None, "--model", help="Embedding 模型"),
    reference_mode: str = typer.Option("index", "--reference-mode", help="reference 入库模式：index/full"),
    max_file_bytes: int = typer.Option(512 * 1024, "--max-bytes", help="单文件最大扫描字节数"),
) -> None:
    """增量更新 KB（基于 manifest 中的文件 hash）。"""
    project_root = _require_project_root()
    model = embedding_model or _default_embedding_model(project_root)
    summary, report = update_kb(
        project_root,
        embedding_model=model,
        reference_mode=reference_mode,
        scan_settings=ScanSettings(max_file_bytes=max_file_bytes),
    )
    console.print(
        Panel.fit(
            "\n".join(
                [
                    f"新增：{summary.added} 个文件（将触发 Codex 语义切片）",
                    f"变更：{summary.changed} 个文件（将触发 Codex 语义切片）",
                    f"移除：{summary.removed} 个文件（已从向量库删除）",
                    f"写入切片：{summary.chunks_written} 个",
                    f"待入库：{summary.added + summary.changed} 个文件",
                    f"排除：{report.excluded} 个文件",
                ]
            ),
            title="KB 更新完成",
        )
    )


@kb_app.command("query")
def kb_query(
    query: str = typer.Argument(..., help="检索 query 文本"),
    n: int = typer.Option(5, "--n", help="返回条数"),
    collection: str = typer.Option("chunks", "--collection", help="切片/记录（chunks/records）"),
) -> None:
    """向量检索。"""
    project_root = _require_project_root()
    kb = KnowledgeBase(project_root, embedding_model=_default_embedding_model(project_root))
    res = kb.query(query, n=n, collection=collection)

    ids = (res.get("ids") or [[]])[0]
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]

    collection_zh = {"chunks": "切片", "records": "记录"}.get(collection, collection)
    table = Table(title=f"KB 检索结果（{collection_zh}）")
    table.add_column("序号")
    table.add_column("ID")
    table.add_column("距离")
    table.add_column("来源/类型")
    table.add_column("摘要")

    for i, _id in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        dist = dists[i] if i < len(dists) else ""
        source = meta.get("source_path", "")
        typ = meta.get("type", meta.get("step", ""))
        summary = meta.get("summary", "")
        table.add_row(str(i + 1), str(_id), str(dist), f"{source} ({typ})", str(summary)[:80])
    console.print(table)


@kb_app.command("context")
def kb_context(
    query: str = typer.Argument(..., help="检索 query 文本"),
    n: int = typer.Option(8, "--n", help="返回条数"),
    format: str = typer.Option("md", "--format", help="md/json"),
) -> None:
    """输出给 Codex 可直接使用的上下文片段。"""
    project_root = _require_project_root()
    kb = KnowledgeBase(project_root, embedding_model=_default_embedding_model(project_root))
    res = kb.query(query, n=n, collection="chunks")

    ids = (res.get("ids") or [[]])[0]
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]

    if format == "json":
        payload: list[dict[str, Any]] = []
        for i, _id in enumerate(ids):
            meta = metas[i] if i < len(metas) else {}
            doc = docs[i] if i < len(docs) else ""
            payload.append({"id": _id, "metadata": meta, "content": doc})
        console.print_json(data=payload)
        return

    lines: list[str] = []
    lines.append(f"# KB 上下文\n\n查询：{query}\n")
    for i, _id in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        doc = docs[i] if i < len(docs) else ""
        source = meta.get("source_path", "")
        typ = meta.get("type", "")
        summary = meta.get("summary", "")
        lines.append(f"## {i + 1}) {source} ({typ})\n")
        if summary:
            lines.append(f"摘要：{summary}\n")
        lines.append("```text\n")
        lines.append(doc[:2000].rstrip())
        lines.append("\n```\n")
    console.print("\n".join(lines))


@kb_app.command("record")
def kb_record(
    step: WorkflowStep = typer.Option(..., "--step", help="工作流步骤"),
    change: str = typer.Option("unknown", "--change", help="变更名称"),
    task_id: Optional[str] = typer.Option(None, "--task-id", help="任务 ID"),
    session_id: Optional[str] = typer.Option(None, "--session-id", help="Codex session_id"),
    notes: Optional[str] = typer.Option(None, "--notes", help="备注"),
) -> None:
    """写入工作流记录（records + events）。"""
    project_root = _require_project_root()
    kb = KnowledgeBase(project_root, embedding_model=_default_embedding_model(project_root))
    rec = WorkflowRecord(
        record_id=new_record_id(),
        step=step,
        change_name=change,
        created_at=datetime.now().isoformat(),
        task_id=task_id,
        session_id=session_id,
        notes=notes,
    )
    kb.add_record(rec)
    console.print(f"[green]√[/green] 已写入记录：{rec.record_id}")


@kb_app.command("compact")
def kb_compact() -> None:
    """将 events 合并为 snapshot，并更新 manifest。"""
    project_root = _require_project_root()
    kb = KnowledgeBase(project_root, embedding_model=_default_embedding_model(project_root))
    kb.compact()
    console.print("[green]√[/green] KB 压缩完成")
