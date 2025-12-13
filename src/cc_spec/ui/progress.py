"""终端 UI 的进度展示组件。"""

from __future__ import annotations

import time
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table


class ProgressTracker:
    """使用 Rich 进度条跟踪并展示进度。"""

    def __init__(self, console: Console | None = None):
        """初始化进度跟踪器。

        参数：
            console: Rich 控制台实例（未提供则新建）
        """
        self.console = console or Console()
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=self.console,
        )
        self._tasks: dict[str, TaskID] = {}
        self._live: Live | None = None

    def __enter__(self) -> ProgressTracker:
        """进入上下文管理器。"""
        self._progress.__enter__()
        return self

    def __exit__(self, *args: Any) -> None:
        """退出上下文管理器。"""
        self._progress.__exit__(*args)

    def add_task(
        self,
        task_id: str,
        description: str,
        total: int | None = None,
    ) -> None:
        """添加一个需要跟踪的新任务。

        参数：
            task_id: 任务唯一标识
            description: 展示的任务描述
            total: 总步数（不确定则为 None）
        """
        if task_id in self._tasks:
            return

        progress_task_id = self._progress.add_task(description, total=total)
        self._tasks[task_id] = progress_task_id

    def update_task(
        self,
        task_id: str,
        advance: int | None = None,
        completed: int | None = None,
        description: str | None = None,
    ) -> None:
        """更新任务进度。

        参数：
            task_id: 任务标识
            advance: 增量推进的步数
            completed: 已完成步数（绝对值）
            description: 新的描述（可选）
        """
        if task_id not in self._tasks:
            return

        progress_task_id = self._tasks[task_id]
        self._progress.update(
            progress_task_id,
            advance=advance,
            completed=completed,
            description=description,
        )

    def complete_task(self, task_id: str) -> None:
        """将任务标记为完成。

        参数：
            task_id: 任务标识
        """
        if task_id not in self._tasks:
            return

        progress_task_id = self._tasks[task_id]
        task = self._progress.tasks[progress_task_id]
        if task.total is not None:
            self._progress.update(progress_task_id, completed=task.total)

    def remove_task(self, task_id: str) -> None:
        """从展示中移除一个任务。

        参数：
            task_id: 任务标识
        """
        if task_id not in self._tasks:
            return

        progress_task_id = self._tasks[task_id]
        self._progress.remove_task(progress_task_id)
        del self._tasks[task_id]


def show_progress(
    console: Console,
    description: str,
    total: int,
    completed: int,
    show_percentage: bool = True,
    show_time: bool = True,
) -> None:
    """显示一个简单的进度条。

    参数：
        console: Rich 控制台实例
        description: 进度描述
        total: 总步数
        completed: 已完成步数
        show_percentage: 是否显示百分比
        show_time: 是否显示预计剩余时间
    """
    if total == 0:
        percentage = 0.0
    else:
        percentage = (completed / total) * 100

    # 构建进度展示
    bar_width = 40
    filled_width = int((completed / total) * bar_width) if total > 0 else 0
    bar = "#" * filled_width + "-" * (bar_width - filled_width)

    display_parts = [f"[cyan]{description}[/cyan]"]
    display_parts.append(f"[green]{bar}[/green]")

    if show_percentage:
        display_parts.append(f"[yellow]{percentage:.1f}%[/yellow]")

    display_parts.append(f"[dim]{completed}/{total}[/dim]")

    console.print(" ".join(display_parts))


class WaveProgressTracker:
    """以层级方式跟踪 Wave 执行进度。"""

    def __init__(
        self,
        console: Console | None = None,
        total_waves: int = 0,
        total_tasks: int = 0,
    ):
        """初始化 Wave 进度跟踪器。

        参数：
            console: Rich 控制台实例
            total_waves: Wave 总数
            total_tasks: 任务总数
        """
        self.console = console or Console()
        self.total_waves = total_waves
        self.total_tasks = total_tasks
        self.completed_waves = 0
        self.completed_tasks = 0
        self.current_wave: int | None = None
        self.wave_tasks: dict[int, dict[str, str]] = {}  # wave -> {task_id: status} 映射
        self.start_time = time.time()

    def start_wave(self, wave_num: int, tasks: list[str]) -> None:
        """开始一个新的 wave。

        参数：
            wave_num: Wave 编号
            tasks: 本 wave 中的任务 ID 列表
        """
        self.current_wave = wave_num
        self.wave_tasks[wave_num] = {task_id: "in_progress" for task_id in tasks}

    def update_task(self, wave_num: int, task_id: str, status: str) -> None:
        """更新任务状态。

        参数：
            wave_num: Wave 编号
            task_id: 任务标识
            status: 新状态（in_progress/completed/failed）
        """
        if wave_num in self.wave_tasks and task_id in self.wave_tasks[wave_num]:
            old_status = self.wave_tasks[wave_num][task_id]
            self.wave_tasks[wave_num][task_id] = status

            # 更新完成计数
            if old_status != "completed" and status == "completed":
                self.completed_tasks += 1

    def complete_wave(self, wave_num: int) -> None:
        """将 wave 标记为完成。

        参数：
            wave_num: Wave 编号
        """
        self.completed_waves += 1
        if self.current_wave == wave_num:
            self.current_wave = None

    def render(self) -> Table:
        """将当前进度渲染为表格。

        返回：
            包含进度信息的 Rich Table
        """
        table = Table(title="波次执行进度", border_style="cyan", show_header=False)
        table.add_column("项目", style="cyan", width=20)
        table.add_column("数值", style="white")

        # 总体进度
        wave_progress = f"{self.completed_waves}/{self.total_waves}"
        task_progress = f"{self.completed_tasks}/{self.total_tasks}"

        table.add_row("已完成波次", wave_progress)
        table.add_row("已完成任务", task_progress)

        # 当前 wave
        if self.current_wave is not None:
            table.add_row("当前波次", f"波次 {self.current_wave}")

            # 展示当前 wave 中的任务
            if self.current_wave in self.wave_tasks:
                tasks = self.wave_tasks[self.current_wave]
                for task_id, status in tasks.items():
                    status_name = {
                        "in_progress": "进行中",
                        "completed": "已完成",
                        "failed": "失败",
                    }.get(status, status)
                    icon = "√" if status == "completed" else ("×" if status == "failed" else "…")
                    table.add_row(f"  {task_id}", f"{icon} {status_name}")

        # 已耗时
        elapsed = time.time() - self.start_time
        elapsed_str = f"{int(elapsed // 60)}分 {int(elapsed % 60)}秒"
        table.add_row("已耗时", elapsed_str)

        # 预计剩余时间
        if self.completed_tasks > 0 and self.total_tasks > 0:
            avg_time_per_task = elapsed / self.completed_tasks
            remaining_tasks = self.total_tasks - self.completed_tasks
            estimated_remaining = avg_time_per_task * remaining_tasks
            remaining_str = f"{int(estimated_remaining // 60)}分 {int(estimated_remaining % 60)}秒"
            table.add_row("预计剩余", remaining_str)

        return table

    def display(self) -> None:
        """将进度输出到控制台。"""
        self.console.print(self.render())
