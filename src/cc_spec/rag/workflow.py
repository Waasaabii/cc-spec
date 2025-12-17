"""v0.1.5：工作流与 KB 的轻量集成工具。

设计目标：
- 命令侧（specify/plan/apply/checklist/archive）只需调用少量 helper
- KB 不可用时（未安装依赖/未初始化）应尽量降级而非直接阻断
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from cc_spec.utils.files import get_cc_spec_dir

from .knowledge_base import KnowledgeBase, new_record_id
from .models import WorkflowRecord, WorkflowStep
from .pipeline import KBUpdateSummary, update_kb
from .scanner import ScanReport


def default_embedding_model(project_root: Path) -> str:
    """从 manifest 读取 embedding 模型；不存在则返回默认模型。"""
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


def try_get_kb(project_root: Path, *, embedding_model: str | None = None) -> KnowledgeBase | None:
    """尽力返回 KnowledgeBase；失败时返回 None（降级）。"""
    model = embedding_model or default_embedding_model(project_root)
    try:
        return KnowledgeBase(project_root, embedding_model=model)
    except Exception:
        return None


def try_write_record(
    project_root: Path,
    *,
    step: WorkflowStep,
    change_name: str,
    task_id: str | None = None,
    session_id: str | None = None,
    inputs: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
    changed_files: list[str] | None = None,
    notes: str | None = None,
) -> str | None:
    """写入一条 workflow record；失败时返回 None。"""
    kb = try_get_kb(project_root)
    if kb is None:
        return None

    rec = WorkflowRecord(
        record_id=new_record_id(),
        step=step,
        change_name=change_name,
        created_at=datetime.now().isoformat(),
        task_id=task_id,
        session_id=session_id,
        inputs=inputs or {},
        outputs=outputs or {},
        changed_files=changed_files or [],
        notes=notes,
    )
    try:
        kb.add_record(rec)
        return rec.record_id
    except Exception:
        return None


def try_update_kb(
    project_root: Path,
    *,
    embedding_model: str | None = None,
    reference_mode: str = "index",
) -> tuple[KBUpdateSummary, ScanReport] | None:
    """执行一次增量 KB 更新；失败时返回 None（降级）。"""
    model = embedding_model or default_embedding_model(project_root)
    try:
        return update_kb(project_root, embedding_model=model, reference_mode=reference_mode)
    except Exception:
        return None


def try_compact_kb(project_root: Path, *, embedding_model: str | None = None) -> bool:
    """执行 KB compact（events → snapshot）；失败时返回 False。"""
    kb = try_get_kb(project_root, embedding_model=embedding_model)
    if kb is None:
        return False
    try:
        kb.compact()
        return True
    except Exception:
        return False

