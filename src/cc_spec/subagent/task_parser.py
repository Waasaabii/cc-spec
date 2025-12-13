"""cc-spec 的 tasks.md 解析模块。

本模块用于解析 tasks.md 文件，提取任务信息，
并在规格驱动工作流中管理任务状态与检查清单。
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from cc_spec.core.scoring import CheckItem, parse_checklist


class TaskStatus(Enum):
    """工作流中的任务状态。"""

    IDLE = "idle"           # 🟦 任务尚未开始
    IN_PROGRESS = "in_progress"  # 🟨 正在执行中
    COMPLETED = "completed"   # 🟩 已成功完成
    FAILED = "failed"        # 🟥 执行失败
    TIMEOUT = "timeout"      # ⏱️ 执行超时


# 解析时使用的状态图标映射
STATUS_ICONS = {
    "🟦": TaskStatus.IDLE,
    "🟨": TaskStatus.IN_PROGRESS,
    "🟩": TaskStatus.COMPLETED,
    "🟥": TaskStatus.FAILED,
    "⏱️": TaskStatus.TIMEOUT,
}

# 用于更新时的反向映射
STATUS_TO_ICON = {v: k for k, v in STATUS_ICONS.items()}


@dataclass
class ExecutionLog:
    """任务的执行日志条目。

    属性：
        completed_at: 任务完成的 ISO 时间戳
        subagent_id: 执行该任务的 SubAgent ID
        notes: 可选的执行备注
    """

    completed_at: str | None = None
    subagent_id: str | None = None
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
        profile: SubAgent Profile 名称（v1.1）
    """

    task_id: str
    name: str
    wave: int
    status: TaskStatus
    dependencies: list[str] = field(default_factory=list)
    estimated_tokens: int = 0
    required_docs: list[str] = field(default_factory=list)
    code_entry_points: list[str] = field(default_factory=list)
    checklist_items: list[CheckItem] = field(default_factory=list)
    execution_log: ExecutionLog | None = None
    profile: str | None = None  # v1.1：SubAgent Profile 名称


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
    """解析后的完整 tasks.md 文档。

    属性：
        change_name: 该任务列表所属的变更名称
        waves: 包含任务的 Wave 列表
        all_tasks: 任务 ID 到 Task 对象的映射
    """

    change_name: str
    waves: list[Wave] = field(default_factory=list)
    all_tasks: dict[str, Task] = field(default_factory=dict)


def parse_tasks_md(content: str) -> TasksDocument:
    """解析 tasks.md 内容并提取所有任务信息。

    参数：
        content: tasks.md 的原始 Markdown 内容

    返回：
        包含所有解析结果的 TasksDocument 对象

    异常：
        ValueError: tasks.md 格式无效时抛出
    """
    # 从标题中提取变更名称：# Tasks - {change_name} / # 任务 - {change_name}
    title_match = re.search(r"^#\s+(?:Tasks|任务)\s*[-:：]\s+(.+)$", content, re.MULTILINE)
    if not title_match:
        raise ValueError("tasks.md 标题格式无效：需要 `# Tasks - {change-name}` 或 `# 任务 - {change-name}`")

    change_name = title_match.group(1).strip()

    # 解析概览表获取基础任务信息
    overview_tasks = _parse_overview_table(content)

    # 根据概览信息创建 Task 对象
    all_tasks: dict[str, Task] = {}
    waves_dict: dict[int, list[Task]] = {}

    for task_data in overview_tasks:
        task_id = task_data["task_id"]
        wave_num = task_data["wave"]
        status = task_data["status"]
        dependencies = task_data["dependencies"]
        estimated_tokens = task_data["estimated_tokens"]

        # 解析任务详情区块
        task_detail = _parse_task_detail(content, task_id)

        # 构建 Task 对象
        task = Task(
            task_id=task_id,
            name=task_detail.get("name", ""),
            wave=wave_num,
            status=status,
            dependencies=dependencies,
            estimated_tokens=estimated_tokens,
            required_docs=task_detail.get("required_docs", []),
            code_entry_points=task_detail.get("code_entry_points", []),
            checklist_items=task_detail.get("checklist_items", []),
            execution_log=task_detail.get("execution_log"),
            profile=task_detail.get("profile"),  # v1.1：SubAgent Profile（配置）
        )

        all_tasks[task_id] = task

        # 按 wave 分组
        if wave_num not in waves_dict:
            waves_dict[wave_num] = []
        waves_dict[wave_num].append(task)

    # 创建 Wave 对象
    waves = [Wave(wave_number=num, tasks=tasks) for num, tasks in sorted(waves_dict.items())]

    return TasksDocument(
        change_name=change_name,
        waves=waves,
        all_tasks=all_tasks,
    )


def _parse_overview_table(content: str) -> list[dict]:
    """解析概览表以提取基础任务信息。

    参数：
        content: 完整的 tasks.md 内容

    返回：
        包含 task_id、wave、status、dependencies、estimated_tokens 的字典列表
    """
    tasks: list[dict] = []

    # 找到概览表区块
    table_match = re.search(
        r"##\s+概览\s*\n\s*\|[^\n]+\|[^\n]+\n\s*\|[-:\s|]+\|\s*\n((?:\|[^\n]+\n?)+)",
        content,
        re.MULTILINE,
    )

    if not table_match:
        return tasks

    table_rows = table_match.group(1).strip().split("\n")

    for row in table_rows:
        # 解析表格行：| Wave | Task-ID | 预估 | 状态 | 依赖 |
        parts = [p.strip() for p in row.split("|")]
        if len(parts) < 6:
            continue

        # 提取各列值（split 后第一个元素为空，需要跳过）
        wave_str = parts[1]
        task_id = parts[2]
        estimated_str = parts[3]
        status_str = parts[4]
        dependencies_str = parts[5]

        # 解析 wave 编号
        try:
            wave_num = int(wave_str)
        except ValueError:
            continue

        # 解析预估 token 数（例如 "30k" -> 30000）
        estimated_tokens = 0
        if estimated_str:
            token_match = re.search(r"(\d+)k?", estimated_str.lower())
            if token_match:
                estimated_tokens = int(token_match.group(1))
                if "k" in estimated_str.lower():
                    estimated_tokens *= 1000

        # 根据图标解析状态
        status = TaskStatus.IDLE  # 默认
        for icon, status_enum in STATUS_ICONS.items():
            if icon in status_str:
                status = status_enum
                break

        # 解析依赖项
        dependencies: list[str] = []
        if dependencies_str and dependencies_str != "-" and "无" not in dependencies_str:
            # 以逗号分隔并清理空白
            dep_parts = [d.strip() for d in dependencies_str.split(",")]
            dependencies = [d for d in dep_parts if d and d != "-"]

        tasks.append({
            "task_id": task_id,
            "wave": wave_num,
            "status": status,
            "dependencies": dependencies,
            "estimated_tokens": estimated_tokens,
        })

    return tasks


def _parse_task_detail(content: str, task_id: str) -> dict:
    """解析任务详情区块，提取完整的任务信息。

    参数：
        content: 完整的 tasks.md 内容
        task_id: 要查找并解析的任务 ID

    返回：
        包含任务详情的字典（name、required_docs、code_entry_points、checklist_items、execution_log、profile）
    """
    result: dict = {
        "name": "",
        "required_docs": [],
        "code_entry_points": [],
        "checklist_items": [],
        "execution_log": None,
        "profile": None,  # v1.1：SubAgent Profile（配置）
    }

    # 用于匹配任务标题的模式：### XX-NAME - 描述 / ### Task: XX-NAME / ### 任务：XX-NAME
    # 捕获内容直到下一个 ### 或 ---
    pattern = re.compile(
        rf"^###\s+(?:(?:Task|任务)[:：]\s+)?{re.escape(task_id)}\s*-\s*(.+?)\s*\n"
        r"(.*?)(?=^###\s+|^---|\Z)",
        re.MULTILINE | re.DOTALL,
    )

    match = pattern.search(content)
    if not match:
        return result

    result["name"] = match.group(1).strip()
    section_content = match.group(2)

    # 解析必读文档
    docs_match = re.search(
        r"\*\*必读文档\*\*:?\s*\n((?:\s*-\s+.+\n?)+)",
        section_content,
        re.MULTILINE,
    )
    if docs_match:
        docs_text = docs_match.group(1)
        result["required_docs"] = [
            line.strip("- ").strip()
            for line in docs_text.split("\n")
            if line.strip().startswith("-")
        ]

    # 解析核心代码入口
    code_match = re.search(
        r"\*\*核心代码入口\*\*:?\s*\n((?:\s*-\s+.+\n?)+)",
        section_content,
        re.MULTILINE,
    )
    if code_match:
        code_text = code_match.group(1)
        result["code_entry_points"] = [
            line.strip("- ").strip()
            for line in code_text.split("\n")
            if line.strip().startswith("-")
        ]

    # 解析 Profile（v1.1）
    profile_match = re.search(
        r"\*\*(?:Profile|配置)\*\*[:：]?\s*(.+?)(?:\n|$)",
        section_content,
        re.MULTILINE,
    )
    if profile_match:
        profile = profile_match.group(1).strip()
        if profile and profile != "-" and profile.lower() not in {"default", "默认"}:
            result["profile"] = profile

    # 解析检查清单项
    checklist_match = re.search(
        r"\*\*(?:Checklist|检查清单)\*\*[:：]?\s*\n((?:\s*[-*]\s+\[[ xX\-]\].+\n?)+)",
        section_content,
        re.MULTILINE,
    )
    if checklist_match:
        checklist_content = checklist_match.group(1)
        result["checklist_items"] = parse_checklist(checklist_content)

    # 解析执行日志
    log_match = re.search(
        r"\*\*执行日志\*\*[:：]?\s*\n"
        r"(?:-\s+完成时间[:：]\s*(.+?)\s*\n)?"
        r"(?:-\s+SubAgent\s+(?:ID|标识)[:：]\s*(.+?)\s*\n)?",
        section_content,
        re.MULTILINE,
    )
    if log_match:
        completed_at = log_match.group(1).strip() if log_match.group(1) else None
        subagent_id = log_match.group(2).strip() if log_match.group(2) else None

        if completed_at or subagent_id:
            result["execution_log"] = ExecutionLog(
                completed_at=completed_at,
                subagent_id=subagent_id,
            )

    return result


# 工具函数

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
    """获取所有待执行任务（status=IDLE）。

    参数：
        doc: 要查询的 TasksDocument

    返回：
        状态为 IDLE 的任务列表
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


# 更新函数

def update_task_status(
    content: str,
    task_id: str,
    new_status: TaskStatus,
    log: dict | None = None,
) -> str:
    """更新 tasks.md 内容中的任务状态。

    会同时更新概览表，以及（若存在）任务详情区块。

    参数：
        content: 原始 tasks.md 内容
        task_id: 要更新的任务 ID
        new_status: 要设置的新状态
        log: 可选的执行日志字典（键：completed_at、subagent_id、notes）

    返回：
        更新后的 tasks.md 内容

    异常：
        ValueError: 内容中找不到任务时抛出
    """
    new_icon = STATUS_TO_ICON.get(new_status, "🟦")

    # 更新概览表
    # 匹配该任务的表格行
    table_pattern = re.compile(
        rf"(\|\s*\d+\s*\|\s*{re.escape(task_id)}\s*\|[^|]*\|)\s*([🟦🟨🟩🟥⏱️])\s*([^|]*\|[^|]*\|)",
        re.MULTILINE,
    )

    match = table_pattern.search(content)
    if not match:
        raise ValueError(f"概览表中未找到任务 {task_id}")

    # 替换表格中的状态图标
    replacement = rf"\g<1> {new_icon} \g<3>"
    content = table_pattern.sub(replacement, content, count=1)

    # 若提供 log，则在任务详情中更新执行日志
    if log and new_status == TaskStatus.COMPLETED:
        # 查找任务详情区块
        detail_pattern = re.compile(
            rf"(^###\s+(?:(?:Task|任务)[:：]\s+)?{re.escape(task_id)}\s*-\s*.+?$.*?)(\*\*执行日志\*\*[:：]?\s*\n(?:.*?)(?=\n\n|^###|^---|\Z))",
            re.MULTILINE | re.DOTALL,
        )

        detail_match = detail_pattern.search(content)
        if detail_match:
            # 替换已有执行日志
            completed_at = log.get("completed_at", datetime.now().isoformat())
            subagent_id = log.get("subagent_id", "")

            log_text = f"**执行日志**:\n- 完成时间: {completed_at}\n- SubAgent 标识: {subagent_id}\n"

            content = detail_pattern.sub(rf"\g<1>{log_text}", content, count=1)
        else:
            # 若不存在执行日志则新增
            section_pattern = re.compile(
                rf"(^###\s+(?:(?:Task|任务)[:：]\s+)?{re.escape(task_id)}\s*-\s*.+?$.*?)(\n\n|^###|^---|\Z)",
                re.MULTILINE | re.DOTALL,
            )

            section_match = section_pattern.search(content)
            if section_match:
                completed_at = log.get("completed_at", datetime.now().isoformat())
                subagent_id = log.get("subagent_id", "")

                log_text = f"\n**执行日志**:\n- 完成时间: {completed_at}\n- SubAgent 标识: {subagent_id}\n\n"

                content = section_pattern.sub(rf"\g<1>{log_text}\g<2>", content, count=1)

    return content


def update_checklist_item(
    content: str,
    task_id: str,
    item_index: int,
    checked: bool,
) -> str:
    """更新 tasks.md 中某个检查清单项的勾选状态。

    参数：
        content: 原始 tasks.md 内容
        task_id: 包含该检查清单的任务 ID
        item_index: 检查清单项索引（从 0 开始）
        checked: 是否勾选该项（True 勾选，False 取消勾选）

    返回：
        更新后的 tasks.md 内容

    异常：
        ValueError: 找不到任务或检查清单项时抛出
    """
    # 查找任务详情区块
    detail_pattern = re.compile(
        rf"^###\s+(?:(?:Task|任务)[:：]\s+)?{re.escape(task_id)}\s*-\s*.+?$.*?(?=^###|^---|\Z)",
        re.MULTILINE | re.DOTALL,
    )

    match = detail_pattern.search(content)
    if not match:
        raise ValueError(f"在内容中未找到任务 {task_id}")

    section_content = match.group(0)

    # 查找 Checklist 区块
    checklist_pattern = re.compile(
        r"(\*\*(?:Checklist|检查清单)\*\*[:：]?\s*\n)((?:\s*[-*]\s+\[[ xX\-]\].+\n?)+)",
        re.MULTILINE,
    )

    checklist_match = checklist_pattern.search(section_content)
    if not checklist_match:
        raise ValueError(f"未找到任务 {task_id} 的检查清单")

    checklist_header = checklist_match.group(1)
    checklist_content = checklist_match.group(2)

    # 解析检查清单项
    item_pattern = re.compile(r"^(\s*[-*]\s+)\[([ xX\-])\](.+)$", re.MULTILINE)
    items = list(item_pattern.finditer(checklist_content))

    if item_index < 0 or item_index >= len(items):
        raise ValueError(
            f"检查清单项索引 {item_index} 超出范围（0-{len(items) - 1}）"
        )

    # 更新指定条目
    target_item = items[item_index]
    new_checkbox = "x" if checked else " "

    new_item = f"{target_item.group(1)}[{new_checkbox}]{target_item.group(3)}"

    # 在 checklist 内容中替换
    updated_checklist = checklist_content[: target_item.start()] + new_item + checklist_content[target_item.end():]

    # 在区块内容中替换
    updated_section = section_content[: checklist_match.start()] + checklist_header + updated_checklist + section_content[checklist_match.end():]

    # 在完整内容中替换
    updated_content = content[: match.start()] + updated_section + content[match.end():]

    return updated_content
