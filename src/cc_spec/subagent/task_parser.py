"""cc-spec 的任务解析模块。

本模块用于解析 tasks.yaml 文件，提取任务信息，
并在规格驱动工作流中管理任务状态与检查清单。


v0.1.6: 新增任务级 `context` 配置，用于智能上下文注入。
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from cc_spec.version import TASKS_YAML_VERSION

from cc_spec.core.scoring import CheckItem, CheckStatus, parse_checklist


class TaskStatus:
    """工作流中的任务状态。"""

    IDLE = "idle"           # 🟦 任务尚未开始
    IN_PROGRESS = "in_progress"  # 🟨 正在执行中
    COMPLETED = "completed"   # 🟩 已成功完成
    FAILED = "failed"        # 🟥 执行失败
    TIMEOUT = "timeout"      # ⏱️ 执行超时


# 用于状态转换的映射
STATUS_MAP = {
    "idle": TaskStatus.IDLE,
    "in_progress": TaskStatus.IN_PROGRESS,
    "completed": TaskStatus.COMPLETED,
    "failed": TaskStatus.FAILED,
    "timeout": TaskStatus.TIMEOUT,
}


@dataclass(frozen=True)
class TaskContext:
    """v0.1.6: 任务上下文配置（用于自动注入 KB 上下文）。"""

    queries: list[str] = field(default_factory=list)
    related_files: list[str] = field(default_factory=list)
    max_chunks: int = 10
    mode: str = "auto"  # auto | manual | hybrid


@dataclass
class ExecutionLog:
    """任务的执行日志条目。

    属性：
        completed_at: 任务完成的 ISO 时间戳
        subagent_id: 执行该任务的 SubAgent ID
        session_id: Codex 线程/会话 ID（用于 resume）
        exit_code: Codex CLI 退出码（可选）
        notes: 可选的执行备注
    """

    completed_at: str | None = None
    subagent_id: str | None = None
    session_id: str | None = None
    exit_code: int | None = None
    notes: str | None = None


@dataclass
class Task:
    """工作流中的单个任务。

    属性：
        task_id: 任务唯一标识（例如："01-SETUP"）
        name: 可读的任务名称
        wave: 所属 Wave 编号
        status: 当前任务状态
        dependencies: 依赖的任务 ID 列表
        estimated_tokens: 上下文的预估 token 数
        required_docs: 必读文档路径列表
        code_entry_points: 核心代码入口路径列表
        checklist_items: 该任务的检查清单项列表
        execution_log: 执行日志条目（若已完成）
        profile: SubAgent Profile 名称
        context: v0.1.6 任务上下文配置
    """

    task_id: str
    name: str
    wave: int
    status: str
    dependencies: list[str] = field(default_factory=list)
    estimated_tokens: int = 0
    required_docs: list[str] = field(default_factory=list)
    code_entry_points: list[str] = field(default_factory=list)
    checklist_items: list[CheckItem] = field(default_factory=list)
    execution_log: ExecutionLog | None = None
    profile: str | None = None  # 
    context: TaskContext | None = None  # v0.1.6：任务上下文配置


@dataclass
class Wave:
    """可并行执行的一组任务（Wave）。

    属性：
        wave_number: Wave 编号（0、1、2...）
        tasks: 本 Wave 内的任务列表
    """

    wave_number: int
    tasks: list[Task] = field(default_factory=list)


@dataclass
class TasksDocument:
    """解析后的完整 tasks.yaml 文档。

    属性：
        change_name: 该任务列表所属的变更名称
        waves: 包含任务的 Wave 列表
        all_tasks: 任务 ID 到 Task 对象的映射
    """

    change_name: str
    waves: list[Wave] = field(default_factory=list)
    all_tasks: dict[str, Task] = field(default_factory=dict)


# ============================================================================
# YAML 格式解析
# ============================================================================


def parse_tasks_yaml(
    content: str,
    cc_spec_dir: Path | None = None,
) -> TasksDocument:
    """解析 tasks.yaml 内容并提取所有任务信息。

    tasks.yaml 格式紧凑，支持 $templates/ 引用。

    参数：
        content: tasks.yaml 的原始 YAML 内容
        cc_spec_dir: .cc-spec 目录路径（用于解析 $templates/ 引用）

    返回：
        包含所有解析结果的 TasksDocument 对象

    异常：
        ValueError: tasks.yaml 格式无效时抛出
    """
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ValueError(f"tasks.yaml 格式无效：{e}")

    if not isinstance(data, dict):
        raise ValueError("tasks.yaml 必须是有效的 YAML 对象")

    # 提取元信息
    version = data.get("version")
    if version != TASKS_YAML_VERSION:
        raise ValueError(f"tasks.yaml 版本不兼容：期望 {TASKS_YAML_VERSION}，实际 {version!r}")

    change_name = data.get("change", "")
    if not change_name:
        raise ValueError("tasks.yaml 必须包含 'change' 字段")

    tasks_data = data.get("tasks", {})
    if not isinstance(tasks_data, dict):
        raise ValueError("tasks.yaml 的 'tasks' 字段必须是对象")

    # 解析任务
    all_tasks: dict[str, Task] = {}
    waves_dict: dict[int, list[Task]] = {}

    for task_id, task_info in tasks_data.items():
        task = _parse_yaml_task(task_id, task_info, cc_spec_dir)
        all_tasks[task_id] = task

        wave_num = task.wave
        if wave_num not in waves_dict:
            waves_dict[wave_num] = []
        waves_dict[wave_num].append(task)

    # 创建 Wave 对象
    waves = [
        Wave(wave_number=num, tasks=tasks)
        for num, tasks in sorted(waves_dict.items())
    ]

    return TasksDocument(
        change_name=change_name,
        waves=waves,
        all_tasks=all_tasks,
    )


def _parse_yaml_task(
    task_id: str,
    task_info: dict[str, Any],
    cc_spec_dir: Path | None = None,
) -> Task:
    """解析单个 YAML 格式的任务。

    参数：
        task_id: 任务 ID
        task_info: 任务信息字典
        cc_spec_dir: .cc-spec 目录路径

    返回：
        Task 对象
    """
    # 解析基本信息
    wave = task_info.get("wave", 0)
    name = task_info.get("name", task_id)
    status_str = task_info.get("status", "idle")

    # 解析状态
    status = STATUS_MAP.get(status_str, TaskStatus.IDLE)

    # 解析预估 token 数
    tokens_str = task_info.get("tokens", "0")
    estimated_tokens = _parse_tokens_str(tokens_str)

    # 解析依赖
    deps = task_info.get("deps", [])
    if isinstance(deps, str):
        deps = [d.strip() for d in deps.split(",") if d.strip()]

    # 解析文档和代码入口
    docs = task_info.get("docs", [])
    if isinstance(docs, str):
        docs = [docs]

    code = task_info.get("code", [])
    if isinstance(code, str):
        code = [code]

    # 解析检查清单（支持 $templates/ 引用）
    checklist_items = _parse_yaml_checklist(
        task_info.get("checklist", []),
        cc_spec_dir,
    )

    # 解析 Profile
    profile = task_info.get("profile")

    # v0.1.6: 解析任务上下文配置
    context = _parse_task_context(task_info.get("context"))

    # 解析执行日志
    execution_log = None
    log_info = task_info.get("log")
    if log_info and isinstance(log_info, dict):
        exit_code_raw = log_info.get("exit_code")
        exit_code: int | None = None
        try:
            if exit_code_raw is not None:
                exit_code = int(exit_code_raw)
        except (TypeError, ValueError):
            exit_code = None
        execution_log = ExecutionLog(
            completed_at=log_info.get("completed_at"),
            subagent_id=log_info.get("subagent_id"),
            session_id=log_info.get("session_id"),
            exit_code=exit_code,
            notes=log_info.get("notes"),
        )

    return Task(
        task_id=task_id,
        name=name,
        wave=wave,
        status=status,
        dependencies=deps,
        estimated_tokens=estimated_tokens,
        required_docs=docs,
        code_entry_points=code,
        checklist_items=checklist_items,
        execution_log=execution_log,
        profile=profile,
        context=context,
    )


def _parse_tokens_str(tokens_str: str | int) -> int:
    """解析 token 数量字符串。

    支持格式：30k, 30K, 30000, 30

    参数：
        tokens_str: token 数量字符串或整数

    返回：
        token 数量（整数）
    """
    if isinstance(tokens_str, int):
        return tokens_str

    tokens_str = str(tokens_str).lower().strip()
    if not tokens_str:
        return 0

    match = re.search(r"(\d+)k?", tokens_str)
    if match:
        value = int(match.group(1))
        if "k" in tokens_str:
            value *= 1000
        return value

    return 0


def _parse_yaml_checklist(
    checklist: list | str,
    cc_spec_dir: Path | None = None,
) -> list[CheckItem]:
    """解析 YAML 格式的检查清单。

    支持：
    - 内联列表：["item1", "item2"]
    - 模板引用：$templates/setup-checklist

    参数：
        checklist: 检查清单数据
        cc_spec_dir: .cc-spec 目录路径

    返回：
        CheckItem 列表
    """
    if not checklist:
        return []

    # 处理模板引用
    if isinstance(checklist, str):
        if checklist.startswith("$templates/"):
            if cc_spec_dir is None:
                # 无法解析模板引用，返回空列表
                return []

            # 使用 templates.py 中的解析函数
            from cc_spec.core.templates import TemplateError, resolve_template_ref

            try:
                template_content = resolve_template_ref(checklist, cc_spec_dir)
                # 解析模板内容中的检查清单
                return parse_checklist(template_content)
            except TemplateError:
                return []
        else:
            # 单个字符串项
            return [
                CheckItem(
                    description=checklist,
                    status=CheckStatus.FAILED,  # FAILED 表示未完成
                    score=0,
                )
            ]

    # 处理列表
    items: list[CheckItem] = []
    for item in checklist:
        if isinstance(item, str):
            # 检查是否为 Markdown 检查清单格式
            if item.strip().startswith("- ["):
                items.extend(parse_checklist(item))
            else:
                items.append(
                    CheckItem(
                        description=item,
                        status=CheckStatus.FAILED,  # FAILED 表示未完成
                        score=0,
                    )
                )
        elif isinstance(item, dict):
            # 结构化格式：{desc: "xxx", done: true}
            desc = item.get("desc", item.get("description", ""))
            done = item.get("done", item.get("checked", False))
            items.append(
                CheckItem(
                    description=desc,
                    status=CheckStatus.PASSED if done else CheckStatus.FAILED,
                    score=10 if done else 0,
                )
            )

    return items


def _parse_task_context(raw: Any) -> TaskContext | None:
    """解析 tasks.yaml 中的 `context` 字段（v0.1.6）。"""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None

    queries_raw = raw.get("queries", [])
    if isinstance(queries_raw, str):
        queries = [q.strip() for q in queries_raw.splitlines() if q.strip()]
    elif isinstance(queries_raw, list):
        queries = [str(q).strip() for q in queries_raw if str(q).strip()]
    else:
        queries = []

    related_raw = raw.get("related_files", [])
    if isinstance(related_raw, str):
        related_files = [p.strip() for p in related_raw.splitlines() if p.strip()]
    elif isinstance(related_raw, list):
        related_files = [str(p).strip() for p in related_raw if str(p).strip()]
    else:
        related_files = []

    max_chunks_raw = raw.get("max_chunks", 10)
    try:
        max_chunks = int(max_chunks_raw)
    except (TypeError, ValueError):
        max_chunks = 10
    if max_chunks <= 0:
        max_chunks = 10

    mode = str(raw.get("mode", "auto")).strip() or "auto"
    if mode not in {"auto", "manual", "hybrid"}:
        mode = "auto"

    return TaskContext(queries=queries, related_files=related_files, max_chunks=max_chunks, mode=mode)


def generate_tasks_yaml(doc: TasksDocument) -> str:
    """从 TasksDocument 生成 tasks.yaml 内容。

    参数：
        doc: TasksDocument 对象

    返回：
        YAML 格式的字符串
    """
    data: dict[str, Any] = {
        "version": TASKS_YAML_VERSION,
        "change": doc.change_name,
        "tasks": {},
    }

    for task_id, task in doc.all_tasks.items():
        task_data: dict[str, Any] = {
            "wave": task.wave,
            "name": task.name,
        }

        # 状态（非默认时添加）
        if task.status != TaskStatus.IDLE:
            task_data["status"] = task.status

        # token 预估（使用紧凑格式）
        if task.estimated_tokens > 0:
            if task.estimated_tokens >= 1000:
                task_data["tokens"] = f"{task.estimated_tokens // 1000}k"
            else:
                task_data["tokens"] = task.estimated_tokens

        # 依赖
        if task.dependencies:
            task_data["deps"] = task.dependencies

        # 文档
        if task.required_docs:
            task_data["docs"] = task.required_docs

        # 代码入口
        if task.code_entry_points:
            task_data["code"] = task.code_entry_points

        # 检查清单（内联格式）
        if task.checklist_items:
            task_data["checklist"] = [
                item.description for item in task.checklist_items
            ]

        # Profile
        if task.profile:
            task_data["profile"] = task.profile

        # v0.1.6: 智能上下文配置
        if task.context:
            task_data["context"] = {
                "mode": task.context.mode,
                "max_chunks": task.context.max_chunks,
                "queries": task.context.queries,
                "related_files": task.context.related_files,
            }

        # 执行日志
        if task.execution_log:
            log_data: dict[str, Any] = {}
            if task.execution_log.completed_at:
                log_data["completed_at"] = task.execution_log.completed_at
            if task.execution_log.subagent_id:
                log_data["subagent_id"] = task.execution_log.subagent_id
            if task.execution_log.session_id:
                log_data["session_id"] = task.execution_log.session_id
            if task.execution_log.exit_code is not None:
                log_data["exit_code"] = task.execution_log.exit_code
            if task.execution_log.notes:
                log_data["notes"] = task.execution_log.notes
            if log_data:
                task_data["log"] = log_data

        data["tasks"][task_id] = task_data

    # 生成 YAML（使用中文友好的选项）
    return yaml.dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )


# ============================================================================
# 工具函数
# ============================================================================

def get_tasks_by_wave(doc: TasksDocument, wave_num: int) -> list[Task]:
    """获取指定 wave 中的所有任务。

    参数：
        doc: 要查询的 TasksDocument
        wave_num: 要获取的 wave 编号

    返回：
        指定 wave 的任务列表（若不存在则返回空列表）
    """
    for wave in doc.waves:
        if wave.wave_number == wave_num:
            return wave.tasks
    return []


def get_pending_tasks(doc: TasksDocument) -> list[Task]:
    """获取所有待执行任务（status=idle）。

    参数：
        doc: 要查询的 TasksDocument

    返回：
        状态为 idle 的任务列表
    """
    return [task for task in doc.all_tasks.values() if task.status == TaskStatus.IDLE]


def get_task_by_id(doc: TasksDocument, task_id: str) -> Task | None:
    """按任务 ID 获取任务。

    参数：
        doc: 要查询的 TasksDocument
        task_id: 要获取的任务 ID

    返回：
        找到则返回 Task 对象，否则返回 None
    """
    return doc.all_tasks.get(task_id)


def validate_dependencies(doc: TasksDocument) -> tuple[bool, list[str]]:
    """校验所有任务依赖是否有效。

    检查项：
    - 所有引用的依赖任务 ID 都存在
    - 无循环依赖
    - 依赖位于更早或相同 wave

    参数：
        doc: 要校验的 TasksDocument

    返回：
        (is_valid, error_messages) 元组：
        - is_valid: 所有校验通过则为 True
        - error_messages: 校验错误信息列表（有效时为空）
    """
    errors: list[str] = []

    # 检查所有依赖是否存在
    for task in doc.all_tasks.values():
        for dep_id in task.dependencies:
            if dep_id not in doc.all_tasks:
                errors.append(
                    f"任务 {task.task_id} 依赖了不存在的任务 {dep_id}"
                )

    # 使用 DFS 检查循环依赖
    def has_cycle(task_id: str, visited: set[str], rec_stack: set[str]) -> bool:
        visited.add(task_id)
        rec_stack.add(task_id)

        task = doc.all_tasks.get(task_id)
        if task:
            for dep_id in task.dependencies:
                if dep_id not in visited:
                    if has_cycle(dep_id, visited, rec_stack):
                        return True
                elif dep_id in rec_stack:
                    return True

        rec_stack.remove(task_id)
        return False

    visited: set[str] = set()
    for task_id in doc.all_tasks:
        if task_id not in visited:
            if has_cycle(task_id, visited, set()):
                errors.append(f"检测到循环依赖，涉及任务 {task_id}")

    # 检查依赖是否位于更早或相同 wave
    for task in doc.all_tasks.values():
        for dep_id in task.dependencies:
            dep_task = doc.all_tasks.get(dep_id)
            if dep_task and dep_task.wave > task.wave:
                errors.append(
                    f"任务 {task.task_id}（波次 {task.wave}）依赖 {dep_id}（波次 {dep_task.wave}），"
                    "但依赖位于更晚的波次"
                )

    is_valid = len(errors) == 0
    return is_valid, errors


def update_task_status_yaml(
    content: str,
    task_id: str,
    new_status: str,
    log: dict | None = None,
) -> str:
    """更新 tasks.yaml 内容中的任务状态。

    参数：
        content: 原始 tasks.yaml 内容
        task_id: 要更新的任务 ID
        new_status: 要设置的新状态
        log: 可选的执行日志字典（键：completed_at、subagent_id、notes）

    返回：
        更新后的 tasks.yaml 内容

    异常：
        ValueError: 内容中找不到任务时抛出
    """
    data = yaml.safe_load(content)

    if "tasks" not in data or task_id not in data["tasks"]:
        raise ValueError(f"tasks.yaml 中未找到任务 {task_id}")

    # 更新状态
    data["tasks"][task_id]["status"] = new_status

    # 更新日志（允许失败/进行中也写入，便于 resume/debug）
    if log:
        data["tasks"][task_id]["log"] = log

    return yaml.dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )


def update_checklist_item_yaml(
    content: str,
    task_id: str,
    item_index: int,
    checked: bool,
) -> str:
    """更新 tasks.yaml 中某个检查清单项的勾选状态。

    参数：
        content: 原始 tasks.yaml 内容
        task_id: 包含该检查清单的任务 ID
        item_index: 检查清单项索引（从 0 开始）
        checked: 是否勾选该项（True 勾选，False 取消勾选）

    返回：
        更新后的 tasks.yaml 内容

    异常：
        ValueError: 找不到任务或检查清单项时抛出
    """
    data = yaml.safe_load(content)

    if "tasks" not in data or task_id not in data["tasks"]:
        raise ValueError(f"tasks.yaml 中未找到任务 {task_id}")

    task_data = data["tasks"][task_id]
    checklist = task_data.get("checklist", [])

    if item_index < 0 or item_index >= len(checklist):
        raise ValueError(
            f"检查清单项索引 {item_index} 超出范围（0-{len(checklist) - 1}）"
        )

    # 如果是字符串列表，转换为结构化格式
    if isinstance(checklist[item_index], str):
        checklist[item_index] = {
            "desc": checklist[item_index],
            "done": checked,
        }
    else:
        checklist[item_index]["done"] = checked

    task_data["checklist"] = checklist

    return yaml.dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
