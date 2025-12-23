"""cc-spec 工作流的状态管理模块。

该模块负责加载、更新并校验变更工作流各阶段的状态迁移。
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class Stage(Enum):
    """变更的工作流阶段。"""

    SPECIFY = "specify"
    DETAIL = "detail"
    REVIEW = "review"
    PLAN = "plan"
    APPLY = "apply"
    ACCEPT = "accept"
    ARCHIVE = "archive"


class TaskStatus(Enum):
    """工作流中任务的状态。"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class StageInfo:
    """某个阶段的状态信息。"""

    status: TaskStatus
    started_at: str | None = None
    completed_at: str | None = None
    waves_completed: int | None = None
    waves_total: int | None = None


@dataclass
class TaskInfo:
    """任务信息数据类。

    agent_id, started_at, completed_at, error, retry_count
    用于追踪任务执行的详细状态。
    """

    id: str
    status: TaskStatus
    wave: int
    agent_id: str | None = None      # 执行该任务的 SubAgent ID
    started_at: str | None = None    # 任务开始时间 (ISO 格式)
    completed_at: str | None = None  # 任务完成时间 (ISO 格式)
    error: str | None = None         # 错误信息 (如果失败)
    retry_count: int = 0             # 重试次数


@dataclass
class ReworkEvent:
    """返工事件记录。"""

    timestamp: str
    from_stage: str
    to_stage: str
    reason: str


@dataclass
class ChangeState:
    """工作流中某个变更的状态。"""

    change_name: str
    created_at: str
    current_stage: Stage
    stages: dict[Stage, StageInfo] = field(default_factory=dict)
    tasks: list[TaskInfo] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """若未提供则初始化 stages。"""
        if not self.stages:
            self.stages = {
                Stage.SPECIFY: StageInfo(status=TaskStatus.PENDING),
                Stage.DETAIL: StageInfo(status=TaskStatus.PENDING),
                Stage.REVIEW: StageInfo(status=TaskStatus.PENDING),
                Stage.PLAN: StageInfo(status=TaskStatus.PENDING),
                Stage.APPLY: StageInfo(status=TaskStatus.PENDING),
                Stage.ACCEPT: StageInfo(status=TaskStatus.PENDING),
                Stage.ARCHIVE: StageInfo(status=TaskStatus.PENDING),
            }


def load_state(state_path: Path) -> ChangeState:
    """从 YAML 文件加载状态。

    参数：
        state_path：status.yaml 文件路径

    返回：
        ChangeState 对象

    异常：
        FileNotFoundError：状态文件不存在
        ValueError：状态文件内容不合法
    """
    if not state_path.exists():
        raise FileNotFoundError(f"未找到状态文件：{state_path}")

    with open(state_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        raise ValueError("状态文件为空")

    # 解析 stages
    stages_data = data.get("stages", {})
    stages: dict[Stage, StageInfo] = {}

    for stage_name, stage_data in stages_data.items():
        try:
            stage = Stage(stage_name)
            status = TaskStatus(stage_data.get("status", "pending"))
            stages[stage] = StageInfo(
                status=status,
                started_at=stage_data.get("started_at"),
                completed_at=stage_data.get("completed_at"),
                waves_completed=stage_data.get("waves_completed"),
                waves_total=stage_data.get("waves_total"),
            )
        except ValueError:
            # 跳过未知阶段
            continue

    # 解析任务列表
    tasks_data = data.get("tasks", [])
    tasks: list[TaskInfo] = []

    for task_data in tasks_data:
        try:
            status = TaskStatus(task_data.get("status", "pending"))
            tasks.append(
                TaskInfo(
                    id=task_data["id"],
                    status=status,
                    wave=task_data.get("wave", 0),
                    agent_id=task_data.get("agent_id"),
                    started_at=task_data.get("started_at"),
                    completed_at=task_data.get("completed_at"),
                    error=task_data.get("error"),
                    retry_count=task_data.get("retry_count", 0),
                )
            )
        except (KeyError, ValueError):
            # 跳过无效任务
            continue

    # 解析 meta
    meta = data.get("meta", {})
    if not isinstance(meta, dict):
        meta = {}

    # 解析当前阶段
    current_stage_raw = data.get("current_stage", "specify")
    try:
        current_stage = Stage(current_stage_raw)
    except ValueError:
        current_stage = Stage.SPECIFY

    return ChangeState(
        change_name=data.get("change_name", ""),
        created_at=data.get("created_at", datetime.now().isoformat()),
        current_stage=current_stage,
        stages=stages,
        tasks=tasks,
        meta=meta,
    )


def update_state(state_path: Path, state: ChangeState) -> None:
    """将状态更新写入 YAML 文件。

    参数：
        state_path：status.yaml 文件路径
        state：要保存的 ChangeState 对象

    异常：
        IOError：无法写入文件
    """
    # 构建 stages 字典
    stages_dict: dict[str, Any] = {}
    for stage, info in state.stages.items():
        stage_data: dict[str, Any] = {"status": info.status.value}

        if info.started_at:
            stage_data["started_at"] = info.started_at
        if info.completed_at:
            stage_data["completed_at"] = info.completed_at
        if info.waves_completed is not None:
            stage_data["waves_completed"] = info.waves_completed
        if info.waves_total is not None:
            stage_data["waves_total"] = info.waves_total

        stages_dict[stage.value] = stage_data

    # 构建任务列表
    tasks_list = []
    for task in state.tasks:
        task_data: dict[str, Any] = {
            "id": task.id,
            "status": task.status.value,
            "wave": task.wave,
        }
        if task.agent_id:
            task_data["agent_id"] = task.agent_id
        if task.started_at:
            task_data["started_at"] = task.started_at
        if task.completed_at:
            task_data["completed_at"] = task.completed_at
        if task.error:
            task_data["error"] = task.error
        if task.retry_count > 0:
            task_data["retry_count"] = task.retry_count
        tasks_list.append(task_data)

    # 构建最终数据结构
    data = {
        "change_name": state.change_name,
        "created_at": state.created_at,
        "current_stage": state.current_stage.value,
        "stages": stages_dict,
        "tasks": tasks_list,
    }
    if state.meta:
        data["meta"] = state.meta

    # 写入文件
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def append_rework_event(state: ChangeState, from_stage: str, to_stage: str, reason: str) -> None:
    """记录返工事件到 meta.rework。"""
    if state.meta is None:
        state.meta = {}

    rework_events = state.meta.get("rework")
    if not isinstance(rework_events, list):
        rework_events = []
        state.meta["rework"] = rework_events

    event = ReworkEvent(
        timestamp=datetime.now().isoformat(),
        from_stage=from_stage,
        to_stage=to_stage,
        reason=reason,
    )
    rework_events.append(asdict(event))


def get_current_change(cc_spec_root: Path) -> ChangeState | None:
    """获取当前激活的变更状态。

    在 .cc-spec/changes/ 目录中查找 status.yaml，并返回最近的未归档变更。

    参数：
        cc_spec_root：.cc-spec 目录路径

    返回：
        当前变更的 ChangeState；若无激活变更则返回 None
    """
    changes_dir = cc_spec_root / "changes"
    if not changes_dir.exists():
        return None

    # 查找所有 status.yaml（排除已归档）
    status_files: list[tuple[Path, datetime]] = []

    for change_dir in changes_dir.iterdir():
        if not change_dir.is_dir():
            continue

        # 跳过 archive 目录
        if change_dir.name == "archive":
            continue

        status_file = change_dir / "status.yaml"
        if status_file.exists():
            # 获取创建时间
            try:
                state = load_state(status_file)
                created_at = datetime.fromisoformat(state.created_at)
                status_files.append((status_file, created_at))
            except (ValueError, FileNotFoundError):
                continue

    if not status_files:
        return None

    # 返回最近的变更
    most_recent = max(status_files, key=lambda x: x[1])
    return load_state(most_recent[0])


def validate_stage_transition(current: Stage, target: Stage) -> bool:
    """校验阶段迁移是否允许。

    阶段迁移遵循线性流程：
    specify -> detail -> review -> plan -> apply -> accept -> archive

    允许回退（用于返工）；不允许向前跳过阶段。

    参数：
        current：当前阶段
        target：目标阶段

    返回：
        迁移合法则为 True，否则为 False
    """
    stage_order = [
        Stage.SPECIFY,
        Stage.DETAIL,
        Stage.REVIEW,
        Stage.PLAN,
        Stage.APPLY,
        Stage.ACCEPT,
        Stage.ARCHIVE,
    ]

    try:
        current_idx = stage_order.index(current)
        target_idx = stage_order.index(target)
    except ValueError:
        return False

    # 允许回退（返工）
    if target_idx < current_idx:
        return True

    # 只允许前进到下一阶段
    if target_idx == current_idx + 1:
        return True

    # 允许停留在同一阶段
    if target_idx == current_idx:
        return True

    # 不允许向前跳过阶段
    return False
