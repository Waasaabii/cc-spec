"""基于 Rich 的终端 UI 展示组件。"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

# 主题配置
THEME = {
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "info": "blue",
    "pending": "dim",
    "in_progress": "yellow",
    "completed": "green",
    "failed": "red",
    "timeout": "magenta",
}

# 状态图标
STATUS_ICONS = {
    "pending": "○",
    "in_progress": "…",
    "completed": "√",
    "failed": "×",
    "timeout": "!",
}

# 状态显示名称
STATUS_NAMES = {
    "pending": "待执行",
    "in_progress": "进行中",
    "completed": "已完成",
    "failed": "失败",
    "timeout": "超时",
}

# 阶段显示名称
STAGE_NAMES = {
    "specify": "编写规格",
    "clarify": "澄清",
    "plan": "计划",
    "apply": "执行",
    "checklist": "验收",
    "archive": "归档",
}


def show_status_panel(
    console: Console,
    change_name: str,
    current_stage: str,
    progress: dict[str, Any] | None = None,
) -> None:
    """显示状态面板，展示当前变更、阶段与进度。

    参数：
        console: Rich 控制台实例
        change_name: 当前变更名称
        current_stage: 当前阶段（specify/clarify/plan/apply/checklist/archive）
        progress: 可选的进度信息（waves_completed、waves_total 等）
    """
    content_lines = []
    content_lines.append(f"[cyan]变更：[/cyan] [bold]{change_name}[/bold]")
    content_lines.append(
        f"[cyan]阶段：[/cyan] [bold]{STAGE_NAMES.get(current_stage, current_stage)}[/bold]"
    )

    if progress:
        waves_completed = progress.get("waves_completed", 0)
        waves_total = progress.get("waves_total", 0)
        if waves_total > 0:
            percentage = int((waves_completed / waves_total) * 100)
            content_lines.append(
                f"[cyan]进度：[/cyan] {waves_completed}/{waves_total} 波次（{percentage}%）"
            )

        tasks_completed = progress.get("tasks_completed", 0)
        tasks_total = progress.get("tasks_total", 0)
        if tasks_total > 0:
            content_lines.append(f"[cyan]任务：[/cyan] {tasks_completed}/{tasks_total}")

    panel = Panel(
        "\n".join(content_lines),
        title="[bold]当前状态[/bold]",
        border_style="cyan",
        padding=(1, 2),
    )
    console.print(panel)


def show_task_table(
    console: Console,
    tasks: list[dict[str, Any]],
    show_wave: bool = True,
    show_dependencies: bool = True,
) -> None:
    """显示任务表格，包含状态、wave 与依赖信息。

    参数：
        console: Rich 控制台实例
        tasks: 任务字典列表，包含键：id、status、wave、dependencies、estimate
        show_wave: 是否显示 Wave 列
        show_dependencies: 是否显示依赖列
    """
    table = Table(title="任务概览", border_style="cyan", show_header=True)

    # 添加列
    if show_wave:
        table.add_column("波次", style="dim", width=6, justify="center")
    table.add_column("任务 ID", style="cyan", width=20)
    table.add_column("状态", width=12, justify="center")
    table.add_column("预估", style="dim", width=10, justify="right")
    if show_dependencies:
        table.add_column("依赖", style="dim", width=20)

    # 按 wave 与 ID 排序任务
    sorted_tasks = sorted(tasks, key=lambda t: (t.get("wave", 0), t.get("id", "")))

    # 添加行
    for task in sorted_tasks:
        task_id = task.get("id", "")
        status = task.get("status", "pending")
        wave = str(task.get("wave", 0))
        estimate = task.get("estimate", "")
        dependencies = task.get("dependencies", [])

        # 获取状态图标与颜色
        icon = STATUS_ICONS.get(status, "○")
        color = THEME.get(status, "white")
        status_name = STATUS_NAMES.get(status, status)

        # 组合带图标的状态展示
        status_display = f"{icon} [{color}]{status_name}[/{color}]"

        # 格式化依赖项
        deps_display = ", ".join(dependencies) if dependencies else "-"

        # 构建行数据
        row = []
        if show_wave:
            row.append(wave)
        row.extend([task_id, status_display, estimate])
        if show_dependencies:
            row.append(deps_display)

        table.add_row(*row)

    console.print(table)


def show_wave_tree(
    console: Console,
    waves: dict[int, list[dict[str, Any]]],
    current_wave: int | None = None,
) -> None:
    """显示 Wave 执行树，展示并行与串行关系。

    参数：
        console: Rich 控制台实例
        waves: wave 编号到任务列表的映射
        current_wave: 可选：需要高亮的当前 wave 编号
    """
    tree = Tree(
        "[bold cyan]波次执行计划[/bold cyan]",
        guide_style="grey50",
    )

    for wave_num in sorted(waves.keys()):
        tasks = waves[wave_num]

        # 高亮当前 wave
        if current_wave is not None and wave_num == current_wave:
            wave_label = f"[yellow]波次 {wave_num}[/yellow] [dim]（当前）[/dim]"
        elif current_wave is not None and wave_num < current_wave:
            wave_label = f"[green]波次 {wave_num}[/green] [dim]（已完成）[/dim]"
        else:
            wave_label = f"[white]波次 {wave_num}[/white]"

        # 多任务时添加并发提示
        if len(tasks) > 1:
            wave_label += " [dim]（可并发）[/dim]"

        wave_branch = tree.add(wave_label)

        # 在 wave 下添加任务
        for task in tasks:
            task_id = task.get("id", "")
            status = task.get("status", "pending")
            icon = STATUS_ICONS.get(status, "○")
            color = THEME.get(status, "white")

            task_label = f"{icon} [{color}]{task_id}[/{color}]"

            # 添加依赖信息
            dependencies = task.get("dependencies", [])
            if dependencies:
                task_label += f" [dim]（依赖：{', '.join(dependencies)}）[/dim]"

            wave_branch.add(task_label)

    console.print(tree)


def get_status_color(status: str) -> str:
    """获取指定状态对应的主题颜色。

    参数：
        status: 状态字符串（pending/in_progress/completed/failed/timeout）

    返回：
        该状态对应的颜色名称
    """
    return THEME.get(status, "white")


def get_status_icon(status: str) -> str:
    """获取指定状态对应的图标。

    参数：
        status: 状态字符串（pending/in_progress/completed/failed/timeout）

    返回：
        该状态对应的图标
    """
    return STATUS_ICONS.get(status, "○")
