"""cc-spec v1.1 的 list 命令。

该模块提供 list 命令，用于展示变更、任务、规格与归档。
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from cc_spec.core.id_manager import IDManager
from cc_spec.core.state import ChangeState, Stage, TaskStatus, load_state
from cc_spec.ui.display import STATUS_ICONS, STAGE_NAMES, THEME
from cc_spec.utils.files import find_project_root, get_cc_spec_dir

console = Console()


def list_command(
    type_: str = typer.Argument(
        "changes",
        help="Type to list: changes, tasks, specs, archive",
        metavar="TYPE",
    ),
    change: str = typer.Option(
        None,
        "--change",
        "-c",
        help="Change ID for listing tasks (e.g., C-001)",
    ),
    status: str = typer.Option(
        None,
        "--status",
        "-s",
        help="Filter by status (pending, in_progress, completed, failed)",
    ),
    format_: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table, json, simple",
    ),
) -> None:
    """列出变更、任务、规格或归档记录。

    \b
    示例：
        cc-spec list changes              # 列出所有变更
        cc-spec list tasks                # 列出当前变更的任务
        cc-spec list tasks -c C-001       # 列出指定变更的任务
        cc-spec list specs                # 列出所有规格
        cc-spec list archive              # 列出归档的变更
        cc-spec list changes -s pending   # 按状态过滤
        cc-spec list changes -f json      # 以 JSON 输出
    """
    project_root = find_project_root()
    if project_root is None:
        console.print(
            "[red]Error:[/red] Not in a cc-spec project. "
            "Run 'cc-spec init' first."
        )
        raise typer.Exit(1)

    cc_spec_root = get_cc_spec_dir(project_root)
    id_manager = IDManager(cc_spec_root)

    type_lower = type_.lower()

    if type_lower == "changes":
        _list_changes(id_manager, cc_spec_root, status, format_)
    elif type_lower == "tasks":
        _list_tasks(id_manager, cc_spec_root, change, status, format_)
    elif type_lower == "specs":
        _list_specs(id_manager, format_)
    elif type_lower == "archive":
        _list_archive(id_manager, format_)
    else:
        console.print(
            f"[red]Error:[/red] Unknown type '{type_}'. "
            "Valid types: changes, tasks, specs, archive"
        )
        raise typer.Exit(1)


def _list_changes(
    id_manager: IDManager,
    cc_spec_root: Path,
    status_filter: str | None,
    format_: str,
) -> None:
    """列出所有变更及其状态。

    参数：
        id_manager：ID 管理器实例
        cc_spec_root：.cc-spec 目录路径
        status_filter：可选的状态过滤条件
        format_：输出格式（table/json/simple）
    """
    changes = id_manager.list_changes()

    if not changes:
        console.print("[dim]No changes found.[/dim]")
        return

    # 收集带状态的变更数据
    change_data: list[dict[str, Any]] = []

    for change_id, entry in sorted(changes.items()):
        change_path = cc_spec_root / entry.path
        status_file = change_path / "status.yaml"

        # 默认值
        stage = "unknown"
        task_status = "pending"
        created = entry.created[:10] if entry.created else "-"

        if status_file.exists():
            try:
                state = load_state(status_file)
                stage = state.current_stage.value
                # 根据阶段确定总体状态
                stage_info = state.stages.get(state.current_stage)
                if stage_info:
                    task_status = stage_info.status.value
            except (ValueError, FileNotFoundError):
                pass

        # 应用状态过滤
        if status_filter and task_status != status_filter:
            continue

        change_data.append({
            "id": change_id,
            "name": entry.name,
            "stage": stage,
            "created": created,
            "status": task_status,
        })

    if not change_data:
        console.print(f"[dim]No changes with status '{status_filter}'.[/dim]")
        return

    # 按格式输出
    if format_ == "json":
        console.print(json.dumps(change_data, indent=2, ensure_ascii=False))
    elif format_ == "simple":
        for item in change_data:
            icon = STATUS_ICONS.get(item["status"], "○")
            console.print(f"{icon} {item['id']} {item['name']} ({item['stage']})")
    else:
        _show_changes_table(change_data)


def _show_changes_table(changes: list[dict[str, Any]]) -> None:
    """以表格形式展示变更。

    参数：
        changes：变更数据字典列表
    """
    table = Table(
        title="Changes",
        border_style="cyan",
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("ID", style="cyan", width=8)
    table.add_column("Name", width=25)
    table.add_column("Stage", width=12, justify="center")
    table.add_column("Created", width=12, justify="center")
    table.add_column("Status", width=12, justify="center")

    for item in changes:
        status = item["status"]
        icon = STATUS_ICONS.get(status, "○")
        color = THEME.get(status, "white")
        stage_name = STAGE_NAMES.get(item["stage"], item["stage"])

        table.add_row(
            item["id"],
            item["name"],
            stage_name,
            item["created"],
            f"{icon} [{color}]{status}[/{color}]",
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(changes)} change(s)[/dim]")


def _list_tasks(
    id_manager: IDManager,
    cc_spec_root: Path,
    change_id: str | None,
    status_filter: str | None,
    format_: str,
) -> None:
    """列出某个变更的任务。

    参数：
        id_manager：ID 管理器实例
        cc_spec_root：.cc-spec 目录路径
        change_id：要列出任务的变更 ID（为 None 时使用当前变更）
        status_filter：可选的状态过滤条件
        format_：输出格式（table/json/simple）
    """
    # 确定要使用的变更
    if change_id:
        # 解析变更 ID
        parsed = id_manager.parse_id(change_id)
        if not parsed.change_id:
            console.print(f"[red]Error:[/red] Invalid change ID: {change_id}")
            raise typer.Exit(1)

        entry = id_manager.get_change_entry(parsed.change_id)
        if not entry:
            console.print(f"[red]Error:[/red] Change not found: {change_id}")
            raise typer.Exit(1)

        change_path = cc_spec_root / entry.path
        resolved_change_id = parsed.change_id
    else:
        # 查找当前变更
        changes = id_manager.list_changes()
        if not changes:
            console.print("[dim]No changes found.[/dim]")
            return

        # 获取最近的未归档变更
        changes_dir = cc_spec_root / "changes"
        latest_state: ChangeState | None = None
        latest_change_id: str | None = None
        latest_time = datetime.min

        for cid, entry in changes.items():
            change_path = changes_dir.parent / entry.path
            status_file = change_path / "status.yaml"

            if status_file.exists():
                try:
                    state = load_state(status_file)
                    if state.current_stage != Stage.ARCHIVE:
                        created = datetime.fromisoformat(state.created_at)
                        if created > latest_time:
                            latest_time = created
                            latest_state = state
                            latest_change_id = cid
                except (ValueError, FileNotFoundError):
                    continue

        if not latest_state or not latest_change_id:
            console.print("[dim]No active changes found.[/dim]")
            return

        resolved_change_id = latest_change_id
        change_path = cc_spec_root / "changes" / latest_state.change_name

    # 加载状态
    status_file = change_path / "status.yaml"
    if not status_file.exists():
        console.print(
            f"[red]Error:[/red] Status file not found for change: {resolved_change_id}"
        )
        raise typer.Exit(1)

    try:
        state = load_state(status_file)
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]Error:[/red] Failed to load state: {e}")
        raise typer.Exit(1)

    # 如果存在则从 tasks.md 加载任务
    tasks_file = change_path / "tasks.md"
    task_data: list[dict[str, Any]] = []

    if tasks_file.exists():
        # 解析 tasks.md 中的任务
        task_data = _parse_tasks_from_file(tasks_file, resolved_change_id)
    else:
        # 使用状态文件中的任务
        for task_info in state.tasks:
            task_data.append({
                "id": f"{resolved_change_id}:{task_info.id}",
                "wave": task_info.wave,
                "status": task_info.status.value,
                "estimate": "-",
                "dependencies": [],
            })

    # 应用状态过滤
    if status_filter:
        task_data = [t for t in task_data if t["status"] == status_filter]

    if not task_data:
        if status_filter:
            console.print(f"[dim]No tasks with status '{status_filter}'.[/dim]")
        else:
            console.print("[dim]No tasks found.[/dim]")
        return

    # 按格式输出
    if format_ == "json":
        console.print(json.dumps(task_data, indent=2, ensure_ascii=False))
    elif format_ == "simple":
        for task in task_data:
            icon = STATUS_ICONS.get(task["status"], "○")
            console.print(
                f"{icon} {task['id']} Wave:{task['wave']} {task['status']}"
            )
    else:
        _show_tasks_table(task_data, resolved_change_id, state)


def _parse_tasks_from_file(
    tasks_file: Path,
    change_id: str,
) -> list[dict[str, Any]]:
    """从 tasks.md 文件解析任务。

    参数：
        tasks_file：tasks.md 文件路径
        change_id：用于给任务 ID 加前缀的变更 ID

    返回：
        任务数据字典列表
    """
    tasks: list[dict[str, Any]] = []

    try:
        content = tasks_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return tasks

    import re

    # 匹配任务标题的模式
    task_pattern = re.compile(r"^###\s+Task:\s*(.+)", re.MULTILINE)

    # 查找所有任务
    for match in task_pattern.finditer(content):
        task_id = match.group(1).strip()
        task_start = match.end()

        # 找到当前任务的结束位置（下一个任务标题或文件末尾）
        next_match = task_pattern.search(content, task_start)
        task_end = next_match.start() if next_match else len(content)
        task_content = content[task_start:task_end]

        # 解析任务属性
        wave = 0
        status = "pending"
        estimate = "-"
        dependencies: list[str] = []

        # 解析 Wave
        wave_match = re.search(r"\*\*Wave\*\*:\s*(\d+)", task_content)
        if wave_match:
            wave = int(wave_match.group(1))

        # 解析状态
        status_match = re.search(r"\*\*状态\*\*:\s*([^\n]+)", task_content)
        if status_match:
            status_text = status_match.group(1).strip()
            if "完成" in status_text or "🟩" in status_text:
                status = "completed"
            elif "进行中" in status_text or "🟨" in status_text:
                status = "in_progress"
            elif "失败" in status_text or "🟥" in status_text:
                status = "failed"
            else:
                status = "pending"

        # 解析预估
        estimate_match = re.search(r"\*\*预估上下文\*\*:\s*~?(\d+[kK]?)", task_content)
        if estimate_match:
            estimate = estimate_match.group(1)

        # 解析依赖
        deps_match = re.search(r"\*\*依赖\*\*:\s*([^\n]+)", task_content)
        if deps_match:
            deps_text = deps_match.group(1).strip()
            if deps_text and deps_text != "-" and deps_text.lower() != "无":
                dependencies = [d.strip() for d in deps_text.split(",")]

        tasks.append({
            "id": f"{change_id}:{task_id}",
            "task_id": task_id,
            "wave": wave,
            "status": status,
            "estimate": estimate,
            "dependencies": dependencies,
        })

    return tasks


def _show_tasks_table(
    tasks: list[dict[str, Any]],
    change_id: str,
    state: ChangeState,
) -> None:
    """以表格形式展示任务。

    参数：
        tasks：任务数据字典列表
        change_id：变更 ID
        state：变更状态
    """
    # 按 wave 分组以便汇总
    waves: dict[int, list[dict[str, Any]]] = {}
    for task in tasks:
        wave = task["wave"]
        if wave not in waves:
            waves[wave] = []
        waves[wave].append(task)

    # 计算 wave 完成情况
    completed_waves = 0
    current_wave = 0
    for wave_num in sorted(waves.keys()):
        wave_tasks = waves[wave_num]
        if all(t["status"] == "completed" for t in wave_tasks):
            completed_waves += 1
        else:
            current_wave = wave_num
            break

    # 构建表格
    table = Table(
        title=f"Tasks for {change_id}",
        border_style="cyan",
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("ID", style="cyan", width=25)
    table.add_column("Wave", width=6, justify="center")
    table.add_column("Status", width=12, justify="center")
    table.add_column("Estimate", width=10, justify="right")
    table.add_column("Dependencies", width=20)

    # 按 wave 与任务 ID 排序
    sorted_tasks = sorted(tasks, key=lambda t: (t["wave"], t.get("task_id", "")))

    for task in sorted_tasks:
        status = task["status"]
        icon = STATUS_ICONS.get(status, "○")
        color = THEME.get(status, "white")

        deps = ", ".join(task["dependencies"]) if task["dependencies"] else "-"

        table.add_row(
            task["id"],
            str(task["wave"]),
            f"{icon} [{color}]{status}[/{color}]",
            task["estimate"],
            deps,
        )

    console.print(table)

    # 汇总
    total = len(tasks)
    completed = sum(1 for t in tasks if t["status"] == "completed")
    in_progress = sum(1 for t in tasks if t["status"] == "in_progress")

    console.print(
        f"\n[dim]Total: {total} task(s) "
        f"(Wave {completed_waves} completed, Wave {current_wave} in progress)"
        f"[/dim]"
    )
    console.print(
        f"[dim]Status: {completed} completed, {in_progress} in progress, "
        f"{total - completed - in_progress} pending[/dim]"
    )


def _list_specs(
    id_manager: IDManager,
    format_: str,
) -> None:
    """列出所有规格。

    参数：
        id_manager：ID 管理器实例
        format_：输出格式（table/json/simple）
    """
    specs = id_manager.list_specs()

    if not specs:
        console.print("[dim]No specs found.[/dim]")
        return

    spec_data = [
        {"id": spec_id, "path": entry.path}
        for spec_id, entry in sorted(specs.items())
    ]

    if format_ == "json":
        console.print(json.dumps(spec_data, indent=2, ensure_ascii=False))
    elif format_ == "simple":
        for item in spec_data:
            console.print(f"  {item['id']} → {item['path']}")
    else:
        table = Table(
            title="Specs",
            border_style="cyan",
            show_header=True,
            header_style="bold cyan",
        )

        table.add_column("ID", style="cyan", width=20)
        table.add_column("Path", width=40)

        for item in spec_data:
            table.add_row(item["id"], item["path"])

        console.print(table)
        console.print(f"\n[dim]Total: {len(spec_data)} spec(s)[/dim]")


def _list_archive(
    id_manager: IDManager,
    format_: str,
) -> None:
    """列出所有已归档的变更。

    参数：
        id_manager：ID 管理器实例
        format_：输出格式（table/json/simple）
    """
    archives = id_manager.list_archive()

    if not archives:
        console.print("[dim]No archived changes found.[/dim]")
        return

    archive_data = [
        {"id": archive_id, "name": entry.name, "path": entry.path}
        for archive_id, entry in sorted(archives.items())
    ]

    if format_ == "json":
        console.print(json.dumps(archive_data, indent=2, ensure_ascii=False))
    elif format_ == "simple":
        for item in archive_data:
            console.print(f"  🟩 {item['id']} {item['name']}")
    else:
        table = Table(
            title="Archived Changes",
            border_style="cyan",
            show_header=True,
            header_style="bold cyan",
        )

        table.add_column("ID", style="cyan", width=18)
        table.add_column("Name", width=25)
        table.add_column("Path", width=35)

        for item in archive_data:
            table.add_row(item["id"], item["name"], item["path"])

        console.print(table)
        console.print(f"\n[dim]Total: {len(archive_data)} archived change(s)[/dim]")
