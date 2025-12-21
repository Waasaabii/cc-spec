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

from cc_spec.core.config import Config, KBChunkingConfig
from cc_spec.utils.files import get_cc_spec_dir

from .incremental import detect_git_changes
from .knowledge_base import KnowledgeBase, new_record_id
from .models import WorkflowRecord, WorkflowStep
from .pipeline import KBUpdateSummary, init_kb, update_kb
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


def try_write_mode_decision(
    project_root: Path,
    *,
    change_name: str,
    mode: str,
    reason: str,
    file_count: int | None = None,
    user_phrase: str | None = None,
    skipped_steps: list[str] | None = None,
    requirements: dict[str, Any] | None = None,
    extra_outputs: dict[str, Any] | None = None,
) -> str | None:
    """记录工作流模式决策（quick/standard）到 KB。"""
    outputs: dict[str, Any] = {
        "mode": mode,
        "reason": reason,
    }
    if file_count is not None:
        outputs["file_count"] = file_count
    if skipped_steps:
        outputs["skipped_steps"] = skipped_steps
    if user_phrase:
        outputs["user_phrase"] = user_phrase
    if requirements:
        outputs["requirements"] = requirements
    if extra_outputs:
        outputs["extra"] = extra_outputs

    return try_write_record(
        project_root,
        step=WorkflowStep.SPECIFY,
        change_name=change_name,
        outputs=outputs,
        notes="mode_decision",
    )


def try_update_kb(
    project_root: Path,
    *,
    embedding_model: str | None = None,
    reference_mode: str = "index",
    attribution: dict[str, Any] | None = None,
    chunking_config: KBChunkingConfig | None = None,
) -> tuple[KBUpdateSummary, ScanReport] | None:
    """执行一次增量 KB 更新；失败时返回 None（降级）。"""
    model = embedding_model or default_embedding_model(project_root)
    try:
        return update_kb(
            project_root,
            embedding_model=model,
            reference_mode=reference_mode,
            attribution=attribution,
            chunking_config=chunking_config,
        )
    except Exception:
        return None


def try_init_kb(
    project_root: Path,
    *,
    embedding_model: str | None = None,
    reference_mode: str = "index",
    attribution: dict[str, Any] | None = None,
    chunking_config: KBChunkingConfig | None = None,
) -> tuple[KBUpdateSummary, ScanReport] | None:
    """执行一次全量 KB 构建；失败时返回 None（降级）。"""
    model = embedding_model or default_embedding_model(project_root)
    try:
        return init_kb(
            project_root,
            embedding_model=model,
            reference_mode=reference_mode,
            attribution=attribution,
            chunking_config=chunking_config,
        )
    except Exception:
        return None


def _normalize_post_task_strategy(strategy: str | None) -> str:
    raw = str(strategy or "smart").strip().lower()
    aliases = {
        "incremental": "smart",
        "full_sync": "full",
        "none": "skip",
    }
    normalized = aliases.get(raw, raw)
    if normalized not in {"smart", "full", "skip"}:
        return "smart"
    return normalized


def _has_worktree_changes(project_root: Path) -> bool | None:
    change_set = detect_git_changes(project_root)
    if change_set is None:
        return None
    return bool(change_set.changed or change_set.removed or change_set.untracked)


def try_post_task_sync_kb(
    project_root: Path,
    *,
    config: Config | None,
    embedding_model: str | None = None,
    reference_mode: str = "index",
    attribution: dict[str, Any] | None = None,
) -> tuple[KBUpdateSummary, ScanReport] | None:
    """按 config.kb.update.post_task_sync 策略执行 KB 同步（失败时返回 None）。"""
    if config is None:
        return try_update_kb(
            project_root,
            embedding_model=embedding_model,
            reference_mode=reference_mode,
            attribution=attribution,
        )

    sync_cfg = config.kb.update.post_task_sync
    if not sync_cfg.enabled:
        return None

    strategy = _normalize_post_task_strategy(sync_cfg.strategy)
    chunking_cfg = config.kb.chunking

    if strategy == "skip":
        return None

    if strategy == "full":
        return try_init_kb(
            project_root,
            embedding_model=embedding_model,
            reference_mode=reference_mode,
            attribution=attribution,
            chunking_config=chunking_cfg,
        )

    if strategy == "smart":
        changed = _has_worktree_changes(project_root)
        if changed is False:
            return None

    return try_update_kb(
        project_root,
        embedding_model=embedding_model,
        reference_mode=reference_mode,
        attribution=attribution,
        chunking_config=chunking_cfg,
    )


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
