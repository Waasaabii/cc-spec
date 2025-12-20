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

from cc_spec.core.id_manager import IDManager
from cc_spec.rag.knowledge_base import KnowledgeBase, new_record_id
from cc_spec.rag.models import ChunkResult, ChunkStatus, WorkflowRecord, WorkflowStep
from cc_spec.rag.pipeline import (
    DEFAULT_CODEX_BATCH_MAX_CHARS,
    DEFAULT_CODEX_BATCH_MAX_FILES,
    init_kb,
    update_kb,
)
from cc_spec.rag.scanner import ScanSettings, build_file_hash_map, scan_project
from cc_spec.utils.files import find_project_root, get_cc_spec_dir

console = Console()
kb_app = typer.Typer(name="kb", help="KB（向量库）相关命令", no_args_is_help=True)


def _make_verbose_callback(console: Console) -> callable:
    """创建 verbose 模式的进度回调函数。"""

    def callback(idx: int, total: int, path: str, result: ChunkResult) -> None:
        status_icon = "✓" if result.status == ChunkStatus.SUCCESS else "⚠"
        status_text = {
            ChunkStatus.SUCCESS: "[green]成功[/green]",
            ChunkStatus.FALLBACK_EXEC: "[yellow]fallback(执行失败)[/yellow]",
            ChunkStatus.FALLBACK_PARSE: "[yellow]fallback(解析失败)[/yellow]",
            ChunkStatus.FALLBACK_EMPTY: "[yellow]fallback(结果为空)[/yellow]",
        }.get(result.status, "[red]未知[/red]")
        chunks_count = len(result.chunks)
        console.print(
            f"  [{idx + 1}/{total}] {status_icon} {path} → {chunks_count} chunks {status_text}"
        )

    return callback


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


def _emit_agent_json(payload: Any) -> None:
    """输出给 agent 使用的 JSON（不带额外文本，不输出 rich 颜色）。"""
    typer.echo(json.dumps(payload, ensure_ascii=False))


def _coerce_json_list(value: Any) -> list[str]:
    """将 metadata 中的 JSON 列表字段归一为 list[str]（兼容旧字符串）。"""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        if s.startswith("[") and s.endswith("]"):
            try:
                obj = json.loads(s)
            except Exception:
                obj = None
            if isinstance(obj, list):
                return [str(x) for x in obj if str(x).strip()]
        return [s]
    s = str(value).strip()
    return [s] if s else []


@kb_app.command("status")
def kb_status(
    json_output: bool = typer.Option(False, "--json", help="输出 JSON（给 agent 使用）"),
) -> None:
    """查看 KB 状态（manifest + 文件存在性）。"""
    project_root = _require_project_root()
    cc_spec_root = get_cc_spec_dir(project_root)
    paths = {
        "vectordb": cc_spec_root / "vectordb",
        "events": cc_spec_root / "kb.events.jsonl",
        "snapshot": cc_spec_root / "kb.snapshot.jsonl",
        "manifest": cc_spec_root / "kb.manifest.json",
        "attribution": cc_spec_root / "kb.attribution.json",
    }

    if json_output:
        items: list[dict[str, Any]] = []
        for key, path in paths.items():
            label = {
                "vectordb": "向量库",
                "events": "事件日志",
                "snapshot": "快照",
                "manifest": "清单",
                "attribution": "归属索引",
            }.get(key, key)
            items.append(
                {
                    "项目": label,
                    "键": key,
                    "路径": path.relative_to(project_root).as_posix(),
                    "存在": path.exists(),
                }
            )
        _emit_agent_json(
            {
                "命令": "kb status",
                "项目根目录": str(project_root),
                "条目": items,
            }
        )
        return

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
            "attribution": "归属索引",
        }.get(name, name)
        table.add_row(label, path.relative_to(project_root).as_posix(), "是" if path.exists() else "否")
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


def _parse_excluded_path_entry(raw: str) -> tuple[str, str]:
    """解析 `scan_project` 生成的 `path (reason)` 形式。"""
    if raw.endswith(")") and " (" in raw:
        path_part, reason_part = raw.rsplit(" (", 1)
        return path_part, reason_part[:-1]
    return raw, ""


def _preview_payload(
    project_root: Path,
    *,
    scanned: list[Any],
    report: Any,
    max_file_bytes: int,
) -> dict[str, Any]:
    ingest_paths = _preview_ingest_files(scanned)
    excluded_paths = getattr(report, "excluded_paths", None) or getattr(report, "sample_excluded", None) or []

    excluded_items: list[dict[str, Any]] = []
    for raw in excluded_paths:
        path_part, reason_code = _parse_excluded_path_entry(str(raw))
        excluded_items.append(
            {
                "路径": path_part,
                "原因代码": reason_code or None,
                "原因": _reason_zh(reason_code) if reason_code else None,
            }
        )

    reason_items: list[dict[str, Any]] = []
    for code, count in (getattr(report, "excluded_reasons", None) or {}).items():
        reason_items.append(
            {
                "原因代码": str(code),
                "原因": _reason_zh(str(code)),
                "数量": int(count),
            }
        )

    return {
        "命令": "kb preview",
        "项目根目录": str(project_root),
        "参数": {"max_file_bytes": int(max_file_bytes)},
        "统计": {
            "扫描候选文件数": int(getattr(report, "included", len(scanned))),
            "待入库文件数_将调用Codex语义切片": int(len(ingest_paths)),
            "排除文件数": int(getattr(report, "excluded", 0)),
        },
        "待入库文件": ingest_paths,
        "排除原因": reason_items,
        "排除文件": excluded_items,
    }


def _print_preview_report(
    project_root: Path,
    *,
    scanned: list[Any],
    report: Any,
    max_file_bytes: int,
) -> None:
    ingest_paths = _preview_ingest_files(scanned)
    ingest_count = len(ingest_paths)
    scanned_count = int(getattr(report, "included", len(scanned)))

    console.print(
        Panel.fit(
            "\n".join(
                [
                    "说明：",
                    "- 预览（扫描）= 统计文件清单（忽略规则/大小/hash），不调用 Codex",
                    "- 入库 = 对待入库文件调用 Codex 语义切片，然后写入向量库",
                    "",
                    f"本次预览：",
                    f"- 扫描候选：{scanned_count} 个文件（仅统计/校验）",
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
    json_output: bool = typer.Option(False, "--json", help="输出 JSON（给 agent 使用）"),
) -> None:
    """预览将入库的文件清单（不执行入库）。"""
    project_root = _require_project_root()
    scanned, report = scan_project(project_root, settings=ScanSettings(max_file_bytes=max_file_bytes))
    if json_output:
        _emit_agent_json(_preview_payload(project_root, scanned=scanned, report=report, max_file_bytes=max_file_bytes))
        return
    _print_preview_report(project_root, scanned=scanned, report=report, max_file_bytes=max_file_bytes)


@kb_app.command("scan")
def kb_scan(
    max_file_bytes: int = typer.Option(512 * 1024, "--max-bytes", help="单文件最大扫描字节数"),
    json_output: bool = typer.Option(False, "--json", help="输出 JSON（给 agent 使用）"),
) -> None:
    """（兼容）预览将入库的文件清单（不执行入库）。"""
    kb_preview(max_file_bytes=max_file_bytes, json_output=json_output)


@kb_app.command("init")
def kb_init(
    embedding_model: Optional[str] = typer.Option(None, "--model", help="Embedding 模型"),
    reference_mode: str = typer.Option("index", "--reference-mode", help="reference 入库模式：index/full"),
    max_file_bytes: int = typer.Option(512 * 1024, "--max-bytes", help="单文件最大扫描字节数"),
    codex_batch_max_files: int = typer.Option(
        DEFAULT_CODEX_BATCH_MAX_FILES,
        "--codex-batch-files",
        help="Codex 批处理：单次调用最多处理文件数（越大越快，但更易超时/格式不稳）",
    ),
    codex_batch_max_chars: int = typer.Option(
        DEFAULT_CODEX_BATCH_MAX_CHARS,
        "--codex-batch-chars",
        help="Codex 批处理：单次调用 prompt 估算字符上限（越大越快，但更易超时/格式不稳）",
    ),
    preview_only: bool = typer.Option(
        False,
        "--preview-only",
        "--report-only",
        help="只预览文件清单，不执行入库",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="输出详细处理进度"),
    json_output: bool = typer.Option(False, "--json", help="输出 JSON（给 agent 使用）"),
) -> None:
    """全量构建/刷新 KB。"""
    project_root = _require_project_root()
    model = embedding_model or _default_embedding_model(project_root)

    if preview_only:
        kb_preview(max_file_bytes=max_file_bytes, json_output=json_output)
        raise typer.Exit(0)

    # verbose 模式：创建进度回调
    progress_callback = _make_verbose_callback(console) if verbose else None

    summary, report = init_kb(
        project_root,
        embedding_model=model,
        reference_mode=reference_mode,
        codex_batch_max_files=codex_batch_max_files,
        codex_batch_max_chars=codex_batch_max_chars,
        scan_settings=ScanSettings(max_file_bytes=max_file_bytes),
        attribution={"step": "kb.init", "by": "kb.init"},
        progress_callback=progress_callback,
    )
    if json_output:
        _emit_agent_json(
            {
                "命令": "kb init",
                "项目根目录": str(project_root),
                "参数": {
                    "embedding_model": model,
                    "reference_mode": reference_mode,
                    "max_file_bytes": int(max_file_bytes),
                    "codex_batch_max_files": int(codex_batch_max_files),
                    "codex_batch_max_chars": int(codex_batch_max_chars),
                },
                "统计": {
                    "扫描候选文件数": int(summary.scanned),
                    "已入库文件数_已调用Codex语义切片": int(summary.added),
                    "写入切片数": int(summary.chunks_written),
                    "reference_mode": str(summary.reference_mode),
                    "排除文件数": int(getattr(report, "excluded", 0)),
                    "语义切片成功": int(summary.chunking_success),
                    "fallback切片": int(summary.chunking_fallback),
                },
                "fallback文件": list(summary.fallback_files),
                "排除原因": [
                    {
                        "原因代码": str(code),
                        "原因": _reason_zh(str(code)),
                        "数量": int(count),
                    }
                    for code, count in (getattr(report, "excluded_reasons", None) or {}).items()
                ],
            }
        )
        return

    # 切片质量信息
    chunking_info = [
        f"语义切片成功：{summary.chunking_success} 个文件",
        f"Fallback 切片：{summary.chunking_fallback} 个文件",
    ]
    if summary.fallback_files:
        chunking_info.append(f"  ↳ {', '.join(summary.fallback_files[:5])}" + ("..." if len(summary.fallback_files) > 5 else ""))

    console.print(
        Panel.fit(
            "\n".join(
                [
                    f"扫描候选：{summary.scanned} 个文件",
                    f"已入库文件：{summary.added} 个（已调用 Codex 语义切片）",
                    f"写入切片：{summary.chunks_written} 个",
                    f"reference 模式：{summary.reference_mode}",
                    f"排除：{report.excluded} 个文件",
                    "─" * 30,
                    *chunking_info,
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
    codex_batch_max_files: int = typer.Option(
        DEFAULT_CODEX_BATCH_MAX_FILES,
        "--codex-batch-files",
        help="Codex 批处理：单次调用最多处理文件数（越大越快，但更易超时/格式不稳）",
    ),
    codex_batch_max_chars: int = typer.Option(
        DEFAULT_CODEX_BATCH_MAX_CHARS,
        "--codex-batch-chars",
        help="Codex 批处理：单次调用 prompt 估算字符上限（越大越快，但更易超时/格式不稳）",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="输出详细处理进度"),
    json_output: bool = typer.Option(False, "--json", help="输出 JSON（给 agent 使用）"),
) -> None:
    """增量更新 KB（基于 manifest 中的文件 hash）。"""
    project_root = _require_project_root()
    model = embedding_model or _default_embedding_model(project_root)

    # verbose 模式：创建进度回调
    progress_callback = _make_verbose_callback(console) if verbose else None

    summary, report = update_kb(
        project_root,
        embedding_model=model,
        reference_mode=reference_mode,
        codex_batch_max_files=codex_batch_max_files,
        codex_batch_max_chars=codex_batch_max_chars,
        scan_settings=ScanSettings(max_file_bytes=max_file_bytes),
        attribution={"step": "kb.update", "by": "kb.update"},
        progress_callback=progress_callback,
    )
    if json_output:
        _emit_agent_json(
            {
                "命令": "kb update",
                "项目根目录": str(project_root),
                "参数": {
                    "embedding_model": model,
                    "reference_mode": reference_mode,
                    "max_file_bytes": int(max_file_bytes),
                    "codex_batch_max_files": int(codex_batch_max_files),
                    "codex_batch_max_chars": int(codex_batch_max_chars),
                },
                "统计": {
                    "扫描候选文件数": int(summary.scanned),
                    "新增文件数_将调用Codex语义切片": int(summary.added),
                    "变更文件数_将调用Codex语义切片": int(summary.changed),
                    "移除文件数_已从向量库删除": int(summary.removed),
                    "待入库文件数_将调用Codex语义切片": int(summary.added + summary.changed),
                    "写入切片数": int(summary.chunks_written),
                    "reference_mode": str(summary.reference_mode),
                    "排除文件数": int(getattr(report, "excluded", 0)),
                    "语义切片成功": int(summary.chunking_success),
                    "fallback切片": int(summary.chunking_fallback),
                },
                "fallback文件": list(summary.fallback_files),
                "排除原因": [
                    {
                        "原因代码": str(code),
                        "原因": _reason_zh(str(code)),
                        "数量": int(count),
                    }
                    for code, count in (getattr(report, "excluded_reasons", None) or {}).items()
                ],
            }
        )
        return

    # 切片质量信息
    chunking_info = [
        f"语义切片成功：{summary.chunking_success} 个文件",
        f"Fallback 切片：{summary.chunking_fallback} 个文件",
    ]
    if summary.fallback_files:
        chunking_info.append(f"  ↳ {', '.join(summary.fallback_files[:5])}" + ("..." if len(summary.fallback_files) > 5 else ""))

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
                    "─" * 30,
                    *chunking_info,
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
    json_output: bool = typer.Option(False, "--json", help="输出 JSON（给 agent 使用）"),
) -> None:
    """向量检索。"""
    project_root = _require_project_root()
    kb = KnowledgeBase(project_root, embedding_model=_default_embedding_model(project_root))
    res = kb.query(query, n=n, collection=collection)

    ids = (res.get("ids") or [[]])[0]
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]

    if json_output:
        items: list[dict[str, Any]] = []
        for i, _id in enumerate(ids):
            meta = metas[i] if i < len(metas) else {}
            items.append(
                {
                    "序号": i + 1,
                    "ID": str(_id),
                    "距离": dists[i] if i < len(dists) else None,
                    "来源": meta.get("source_path", "") if isinstance(meta, dict) else "",
                    "类型": meta.get("type", meta.get("step", "")) if isinstance(meta, dict) else "",
                    "摘要": meta.get("summary", "") if isinstance(meta, dict) else "",
                }
            )
        _emit_agent_json(
            {
                "命令": "kb query",
                "项目根目录": str(project_root),
                "参数": {"query": query, "n": int(n), "collection": str(collection)},
                "结果": items,
            }
        )
        return

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
    lang: str = typer.Option("en", "--lang", help="输出语言：en/zh（md 格式生效）"),
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
            payload.append({"ID": _id, "元数据": meta, "内容": doc})
        _emit_agent_json({"命令": "kb context", "查询": query, "结果": payload})
        return

    use_zh = lang.lower().strip() == "zh"
    lines: list[str] = []
    if use_zh:
        lines.append(f"# KB 上下文\n\n查询：{query}\n")
    else:
        lines.append(f"# KB Context\n\nQuery: {query}\n")
    for i, _id in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        doc = docs[i] if i < len(docs) else ""
        source = meta.get("source_path", "")
        typ = meta.get("type", "")
        summary = meta.get("summary", "")
        lines.append(f"## {i + 1}) {source} ({typ})\n")
        if summary:
            label = "摘要" if use_zh else "Summary"
            lines.append(f"{label}: {summary}\n")
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
    json_output: bool = typer.Option(False, "--json", help="输出 JSON（给 agent 使用）"),
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
    if json_output:
        _emit_agent_json(
            {
                "命令": "kb record",
                "项目根目录": str(project_root),
                "record_id": rec.record_id,
                "step": rec.step.value,
                "change": rec.change_name,
                "task_id": rec.task_id,
                "session_id": rec.session_id,
                "created_at": rec.created_at,
            }
        )
        return
    console.print(f"[green]√[/green] 已写入记录：{rec.record_id}")


@kb_app.command("compact")
def kb_compact(
    json_output: bool = typer.Option(False, "--json", help="输出 JSON（给 agent 使用）"),
) -> None:
    """将 events 合并为 snapshot，并更新 manifest。"""
    project_root = _require_project_root()
    kb = KnowledgeBase(project_root, embedding_model=_default_embedding_model(project_root))
    kb.compact()
    if json_output:
        _emit_agent_json({"命令": "kb compact", "项目根目录": str(project_root), "状态": "ok"})
        return
    console.print("[green]√[/green] KB 压缩完成")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        if isinstance(obj, dict):
            items.append(obj)
    return items


def _load_timeline_events(project_root: Path) -> list[dict[str, Any]]:
    """读取 KB 时间线：snapshot（历史） + events（未 compact）。"""
    cc_spec_root = get_cc_spec_dir(project_root)
    snapshot = _read_jsonl(cc_spec_root / "kb.snapshot.jsonl")
    events = _read_jsonl(cc_spec_root / "kb.events.jsonl")

    # snapshot 第一行通常是 meta；过滤掉 meta 行
    snap_events = [e for e in snapshot if not str(e.get("type", "")).startswith("snapshot.")]
    return snap_events + events


def _resolve_change(project_root: Path, change_or_id: str) -> tuple[str | None, str]:
    """返回 (change_id, change_name)。"""
    change_or_id = (change_or_id or "").strip()
    if not change_or_id:
        return (None, "")

    cc_spec_root = get_cc_spec_dir(project_root)
    idm = IDManager(cc_spec_root)
    if change_or_id.startswith("C-"):
        entry = idm.get_change_entry(change_or_id)
        if entry:
            return (change_or_id, entry.name)
        return (change_or_id, change_or_id)

    found = idm.get_change_by_name(change_or_id)
    if found:
        return (found[0], found[1].name)
    return (None, change_or_id)


@kb_app.command("stats")
def kb_stats(
    json_output: bool = typer.Option(False, "--json", help="输出 JSON（给 agent 使用）"),
) -> None:
    """查看 KB 统计信息（manifest + events/snapshot + vectordb）。"""
    project_root = _require_project_root()
    cc_spec_root = get_cc_spec_dir(project_root)

    manifest_path = cc_spec_root / "kb.manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    events_count = len(_read_jsonl(cc_spec_root / "kb.events.jsonl"))
    snapshot_count = len(_read_jsonl(cc_spec_root / "kb.snapshot.jsonl"))

    chunks_count: int | None = None
    records_count: int | None = None
    try:
        import chromadb  # type: ignore[import-not-found]

        client = chromadb.PersistentClient(path=str(cc_spec_root / "vectordb"))
        chunks_count = int(client.get_or_create_collection("chunks").count())
        records_count = int(client.get_or_create_collection("records").count())
    except Exception:
        chunks_count = None
        records_count = None

    payload = {
        "命令": "kb stats",
        "项目根目录": str(project_root),
        "向量库": {
            "路径": str((cc_spec_root / "vectordb").relative_to(project_root).as_posix()),
            "chunks": chunks_count,
            "records": records_count,
        },
        "文件": {
            "manifest": str(manifest_path.relative_to(project_root).as_posix()),
            "events": str((cc_spec_root / "kb.events.jsonl").relative_to(project_root).as_posix()),
            "snapshot": str((cc_spec_root / "kb.snapshot.jsonl").relative_to(project_root).as_posix()),
        },
        "统计": {
            "manifest_files": int(len((manifest.get("files") or {}) if isinstance(manifest.get("files"), dict) else {})),
            "events_lines": int(events_count),
            "snapshot_lines": int(snapshot_count),
            "last_scan_at": manifest.get("last_scan_at"),
            "last_compact_at": manifest.get("last_compact_at"),
            "embedding_model": (manifest.get("embedding") or {}).get("model") if isinstance(manifest.get("embedding"), dict) else None,
            "schema_version": manifest.get("schema_version"),
        },
    }

    if json_output:
        _emit_agent_json(payload)
        return

    table = Table(title="KB 统计", show_lines=True)
    table.add_column("项目")
    table.add_column("值")
    table.add_row("chunks", str(chunks_count) if chunks_count is not None else "未知（未安装/不可用）")
    table.add_row("records", str(records_count) if records_count is not None else "未知（未安装/不可用）")
    table.add_row("manifest_files", str(payload["统计"]["manifest_files"]))
    table.add_row("events_lines", str(events_count))
    table.add_row("snapshot_lines", str(snapshot_count))
    table.add_row("last_scan_at", str(payload["统计"]["last_scan_at"] or ""))
    table.add_row("last_compact_at", str(payload["统计"]["last_compact_at"] or ""))
    table.add_row("embedding_model", str(payload["统计"]["embedding_model"] or ""))
    table.add_row("schema_version", str(payload["统计"]["schema_version"] or ""))
    console.print(table)


@kb_app.command("trace")
def kb_trace(
    change: str = typer.Option(..., "--change", "-c", help="变更名称或 ID（例如 add-oauth 或 C-001）"),
    json_output: bool = typer.Option(False, "--json", help="输出 JSON（给 agent 使用）"),
) -> None:
    """追踪某个变更关联到哪些文件（基于 KB events attribution）。"""
    project_root = _require_project_root()
    change_id, change_name = _resolve_change(project_root, change)
    events = _load_timeline_events(project_root)

    def _match(ev: dict[str, Any]) -> bool:
        attr = ev.get("attribution")
        if not isinstance(attr, dict):
            return False
        if change_id and attr.get("change_id") == change_id:
            return True
        if change_name and attr.get("change_name") == change_name:
            return True
        return False

    touched: dict[str, dict[str, Any]] = {}
    for ev in events:
        if not _match(ev):
            continue
        typ = str(ev.get("type", ""))
        ts = str(ev.get("ts", ""))
        if typ == "chunks.upsert":
            sources = ev.get("sources") or []
            if not isinstance(sources, list):
                continue
            for p in sources:
                path = str(p)
                info = touched.setdefault(path, {"upsert": 0, "delete": 0, "last_ts": ""})
                info["upsert"] += 1
                info["last_ts"] = max(info["last_ts"], ts)
        elif typ == "chunks.delete":
            path = str(ev.get("source_path", ""))
            if not path:
                continue
            info = touched.setdefault(path, {"upsert": 0, "delete": 0, "last_ts": ""})
            info["delete"] += 1
            info["last_ts"] = max(info["last_ts"], ts)

    items = [
        {"路径": p, "upsert": v["upsert"], "delete": v["delete"], "last_ts": v["last_ts"]}
        for p, v in sorted(touched.items(), key=lambda x: x[0])
    ]
    payload = {
        "命令": "kb trace",
        "项目根目录": str(project_root),
        "参数": {"change": change, "change_id": change_id, "change_name": change_name},
        "文件数": int(len(items)),
        "文件": items,
    }
    if json_output:
        _emit_agent_json(payload)
        return

    title = f"KB Trace（{change_name or change}）"
    table = Table(title=title, show_lines=True)
    table.add_column("路径")
    table.add_column("upsert")
    table.add_column("delete")
    table.add_column("last_ts")
    for it in items[:500]:
        table.add_row(str(it["路径"]), str(it["upsert"]), str(it["delete"]), str(it["last_ts"]))
    console.print(table)
    if len(items) > 500:
        console.print(f"[dim]仅展示前 500 条，共 {len(items)} 条[/dim]")


@kb_app.command("blame")
def kb_blame(
    file: str = typer.Argument(..., help="文件路径（可选：path:start-end）"),
    json_output: bool = typer.Option(False, "--json", help="输出 JSON（给 agent 使用）"),
) -> None:
    """查看某个文件的 KB 写入历史（基于 KB events attribution）。"""
    project_root = _require_project_root()
    # 兼容 `path (reason)`（来自 preview 输出）
    path, _ = _parse_excluded_path_entry(file.strip())
    # 兼容 `path:start-end`
    try:
        from cc_spec.rag.context_provider import _parse_file_ref as _parse_file_ref  # type: ignore
    except Exception:
        _parse_file_ref = None  # type: ignore[assignment]

    line_start: int | None = None
    line_end: int | None = None
    if _parse_file_ref is not None:
        p, a, b = _parse_file_ref(path)
        if p:
            path = p
            line_start, line_end = a, b

    events = _load_timeline_events(project_root)
    history: list[dict[str, Any]] = []
    for ev in events:
        typ = str(ev.get("type", ""))
        ts = str(ev.get("ts", ""))
        attr = ev.get("attribution") if isinstance(ev.get("attribution"), dict) else None
        if typ == "chunks.upsert":
            sources = ev.get("sources") or []
            if isinstance(sources, list) and path in [str(p) for p in sources]:
                history.append({"ts": ts, "type": typ, "attribution": attr})
        elif typ == "chunks.delete":
            if str(ev.get("source_path", "")) == path:
                history.append({"ts": ts, "type": typ, "attribution": attr})

    # 当前 chunks（可选按行过滤）
    chunks: list[dict[str, Any]] = []
    try:
        import chromadb  # type: ignore[import-not-found]

        cc_spec_root = get_cc_spec_dir(project_root)
        client = chromadb.PersistentClient(path=str(cc_spec_root / "vectordb"))
        col = client.get_or_create_collection("chunks")
        # chromadb 的 get 默认包含 ids；include 仅支持 documents/embeddings/metadatas 等
        res = col.get(where={"source_path": path}, include=["metadatas"])  # type: ignore[arg-type]
        ids = res.get("ids") if isinstance(res, dict) else None
        metas = res.get("metadatas") if isinstance(res, dict) else None
        if isinstance(ids, list) and isinstance(metas, list):
            for i, cid in enumerate(ids):
                meta = metas[i] if i < len(metas) and isinstance(metas[i], dict) else {}
                s_line = meta.get("start_line")
                e_line = meta.get("end_line")
                try:
                    s_i = int(s_line) if s_line is not None else None
                except Exception:
                    s_i = None
                try:
                    e_i = int(e_line) if e_line is not None else None
                except Exception:
                    e_i = None

                if line_start is not None and line_end is not None and s_i is not None and e_i is not None:
                    if e_i < line_start or s_i > line_end:
                        continue

                chunks.append(
                    {
                        "ID": str(cid),
                        "start_line": s_i,
                        "end_line": e_i,
                        "summary": meta.get("summary", ""),
                        "created_by": meta.get("created_by", ""),
                        "modified_by": _coerce_json_list(meta.get("modified_by")),
                    }
                )
    except Exception:
        chunks = []

    payload = {
        "命令": "kb blame",
        "项目根目录": str(project_root),
        "参数": {"file": path, "start": line_start, "end": line_end},
        "历史": history,
        "当前切片": chunks,
    }

    if json_output:
        _emit_agent_json(payload)
        return

    title = f"KB Blame（{path}）"
    if line_start and line_end:
        title += f":{line_start}-{line_end}"
    console.print(Panel.fit(f"历史事件：{len(history)} 条；当前切片：{len(chunks)} 条", title=title))

    if history:
        t = Table(title="写入历史（events）", show_lines=True)
        t.add_column("ts")
        t.add_column("type")
        t.add_column("by")
        t.add_column("change/task")
        for h in history[-50:]:
            attr = h.get("attribution") if isinstance(h.get("attribution"), dict) else {}
            by = str(attr.get("by", "")) if isinstance(attr, dict) else ""
            change_name = str(attr.get("change_name", "")) if isinstance(attr, dict) else ""
            task_id = str(attr.get("task_id", "")) if isinstance(attr, dict) else ""
            t.add_row(str(h.get("ts", "")), str(h.get("type", "")), by, f"{change_name} {task_id}".strip())
        console.print(t)
        if len(history) > 50:
            console.print(f"[dim]仅展示最近 50 条，共 {len(history)} 条[/dim]")

    if chunks:
        t = Table(title="当前切片（chunks）", show_lines=True)
        t.add_column("ID")
        t.add_column("lines")
        t.add_column("created_by")
        t.add_column("modified_by")
        t.add_column("summary")
        for c in chunks[:80]:
            lines = ""
            if c.get("start_line") and c.get("end_line"):
                lines = f"{c['start_line']}-{c['end_line']}"
            modified = c.get("modified_by") or []
            if isinstance(modified, list):
                modified_disp = ", ".join([str(x) for x in modified if str(x).strip()])
            else:
                modified_disp = str(modified)
            t.add_row(str(c["ID"]), lines, str(c["created_by"]), modified_disp, str(c["summary"])[:80])
        console.print(t)
        if len(chunks) > 80:
            console.print(f"[dim]仅展示前 80 条，共 {len(chunks)} 条[/dim]")
