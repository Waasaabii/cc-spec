"""cc-spec 的 apply 命令实现。

该命令使用 SubAgent 并行执行 tasks.md 中的任务。
任务按 wave 分组：同一 wave 内任务并行执行，wave 之间按顺序串行执行。

v1.1: 新增通过 ID 指定变更的支持。
v1.2: 新增任务级配置的 Profile 支持。
v1.3: 新增锁机制防止并发冲突，新增 agent_id 追踪。
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from cc_spec.core.config import load_config
from cc_spec.core.id_manager import IDManager
from cc_spec.core.lock import LockManager
from cc_spec.core.state import (
    ChangeState,
    Stage,
    StageInfo,
    TaskStatus as StateTaskStatus,
    get_current_change,
    load_state,
    update_state,
)
from cc_spec.subagent.executor import ExecutionResult, SubAgentExecutor
from cc_spec.subagent.result_collector import ResultCollector
from cc_spec.subagent.task_parser import (
    TasksDocument,
    TaskStatus,
    parse_tasks_md,
)
from cc_spec.ui.progress import WaveProgressTracker
from cc_spec.utils.files import find_project_root, get_cc_spec_dir

console = Console()

# 默认设置
DEFAULT_MAX_CONCURRENT = 10
DEFAULT_TIMEOUT_MS = 300000  # 5 分钟


def apply_command(
    change_or_id: Optional[str] = typer.Argument(
        None,
        help="变更名称或 ID（例如 add-oauth 或 C-001）",
    ),
    max_concurrent: int = typer.Option(
        DEFAULT_MAX_CONCURRENT,
        "--max-concurrent",
        "-c",
        help="最大并发任务执行数",
        min=1,
        max=50,
    ),
    timeout: int = typer.Option(
        DEFAULT_TIMEOUT_MS,
        "--timeout",
        "-t",
        help="每个任务的超时时间（毫秒）",
        min=60000,
    ),
    resume: bool = typer.Option(
        False,
        "--resume",
        "-r",
        help="从上次失败/未完成的 Wave 继续执行",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="仅显示将执行的内容，不实际运行任务",
    ),
    use_lock: bool = typer.Option(
        True,
        "--lock/--no-lock",
        help="v1.3：使用锁机制防止并发执行冲突",
    ),
    force_unlock: Optional[str] = typer.Option(
        None,
        "--force-unlock",
        "-f",
        help="v1.3：执行前强制解锁指定任务（例如 --force-unlock 01-SETUP）",
    ),
    skip_locked: bool = typer.Option(
        False,
        "--skip-locked",
        help="v1.3：跳过被锁定的任务并继续执行其他任务",
    ),
) -> None:
    """使用 SubAgent 并行执行 tasks.md 中的任务。

    v1.1：现支持通过变更 ID（例如 C-001）。
    v1.3：支持锁机制防止并发执行冲突。

    该命令会：
    1. 读取 tasks.md 并解析 Wave 分组
    2. 在每个 Wave 内并发执行任务（受 max_concurrent 限制）
    3. 等待当前 Wave 全部完成后再开始下一 Wave
    4. 更新 tasks.md 中的任务状态并记录执行日志
    5. 遇到失败时停止执行并输出报告

    示例：
        cc-spec apply                   # 应用当前激活的变更
        cc-spec apply add-oauth         # 按名称应用
        cc-spec apply C-001             # 按 ID 应用
        cc-spec apply C-001 --dry-run   # 预览将要执行的内容
        cc-spec apply --no-lock         # 禁用锁机制
        cc-spec apply --force-unlock 01-SETUP  # 强制解锁指定任务
        cc-spec apply --skip-locked     # 跳过被锁任务继续执行
    """
    # 查找项目根目录
    project_root = find_project_root()
    if project_root is None:
        console.print(
            "[red]错误：[/red] 这不是 cc-spec 项目，请先运行 'cc-spec init'。",
            style="red",
        )
        raise typer.Exit(1)

    cc_spec_root = get_cc_spec_dir(project_root)
    id_manager = IDManager(cc_spec_root)

    # 确定变更目录
    changes_dir = cc_spec_root / "changes"
    change: str | None = None

    if change_or_id:
        if change_or_id.startswith("C-"):
            # ID 模式：解析为名称
            entry = id_manager.get_change_entry(change_or_id)
            if not entry:
                console.print(f"[red]错误：[/red] 未找到变更：{change_or_id}")
                raise typer.Exit(1)
            change = entry.name
        else:
            change = change_or_id

        change_dir = changes_dir / change
    else:
        # 查找当前激活的变更
        current_state = get_current_change(cc_spec_root)
        if not current_state:
            console.print(
                "[red]错误：[/red] 未找到当前激活的变更。"
                "请指定变更名称，或先运行 'cc-spec specify'。",
                style="red",
            )
            raise typer.Exit(1)

        change = current_state.change_name
        change_dir = changes_dir / change

    if not change_dir.exists():
        console.print(
            f"[red]错误：[/red] 未找到变更 '{change}'。",
            style="red",
        )
        raise typer.Exit(1)

    console.print(f"[cyan]正在执行变更：[/cyan] [bold]{change}[/bold]\n")

    # 检查 tasks.md 是否存在
    tasks_path = change_dir / "tasks.md"
    if not tasks_path.exists():
        console.print(
            f"[red]错误：[/red] 在 {change_dir} 中未找到 tasks.md。"
            "请先运行 'cc-spec plan'。",
            style="red",
        )
        raise typer.Exit(1)

    # 读取并解析 tasks.md
    console.print("[cyan]正在加载 tasks.md...[/cyan]")
    try:
        tasks_content = tasks_path.read_text(encoding="utf-8")
        doc = parse_tasks_md(tasks_content)
    except ValueError as e:
        console.print(
            f"[red]错误：[/red] 解析 tasks.md 失败：{e}",
            style="red",
        )
        raise typer.Exit(1)

    # 统计任务数据
    total_waves = len(doc.waves)
    total_tasks = len(doc.all_tasks)
    idle_tasks = sum(1 for t in doc.all_tasks.values() if t.status == TaskStatus.IDLE)
    completed_tasks = sum(
        1 for t in doc.all_tasks.values() if t.status == TaskStatus.COMPLETED
    )

    console.print(
        f"[green]√[/green] 在 {total_waves} 个波次中找到 {total_tasks} 个任务\n"
    )

    # 显示任务摘要
    _display_task_summary(doc)

    # 确定 resume 的起始 wave
    start_wave = 0
    if resume:
        start_wave = _find_resume_wave(doc)
        if start_wave > 0:
            console.print(
                f"\n[yellow]从波次 {start_wave} 继续执行[/yellow]"
            )

    # 演练模式（dry-run）
    if dry_run:
        console.print("\n[yellow]演练模式：不会执行任何任务[/yellow]\n")
        _display_execution_plan(doc, start_wave)
        console.print(
            "\n[dim]去掉 --dry-run 才会真正执行任务[/dim]"
        )
        raise typer.Exit(0)

    # 检查是否有需要执行的任务
    if idle_tasks == 0:
        console.print(
            "\n[yellow]没有待执行任务。[/yellow]",
            style="yellow",
        )

        if completed_tasks == total_tasks:
            console.print(
                "\n[green]所有任务都已完成！[/green]",
                style="green",
            )
            console.print(
                "\n[bold]下一步：[/bold] 运行 [cyan]cc-spec checklist[/cyan] "
                "验证任务完成情况。"
            )
        raise typer.Exit(0)

    # 确认执行
    console.print(
        f"\n[bold]准备执行 {idle_tasks} 个任务[/bold]"
    )
    console.print(f"[dim]最大并发：{max_concurrent}[/dim]")
    console.print(f"[dim]单任务超时：{timeout / 1000:.0f}s[/dim]\n")

    # 更新状态为 apply 阶段
    status_path = change_dir / "status.yaml"
    _update_apply_stage_started(status_path, total_waves)

    # v1.2：加载配置以支持 profile
    config = None
    config_path = cc_spec_root / "config.yaml"
    if config_path.exists():
        try:
            config = load_config(config_path)
        except Exception as e:
            console.print(f"[yellow]警告：[/yellow] 无法加载配置：{e}")

    # 执行任务
    console.print("[cyan]开始执行任务...[/cyan]\n")

    # v1.3: 处理 force_unlock 选项
    if force_unlock and use_lock:
        lock_manager = LockManager(cc_spec_root)
        lock_info = lock_manager.get_lock_info(force_unlock)
        if lock_info:
            console.print(
                f"[yellow]正在强制解锁任务：[/yellow] {force_unlock} "
                f"（锁持有者：{lock_info.agent_id}）"
            )
            lock_manager.release(force_unlock)  # 不检查 agent_id，强制释放
            console.print(f"[green]√[/green] 任务 {force_unlock} 已解锁\n")
        else:
            console.print(
                f"[dim]任务 {force_unlock} 未被锁定，跳过解锁[/dim]\n"
            )

    try:
        # 创建带配置的执行器（v1.2：profile 支持，v1.3：锁支持）
        executor = SubAgentExecutor(
            tasks_md_path=tasks_path,
            max_concurrent=max_concurrent,
            timeout_ms=timeout,
            config=config,  # v1.2：传入配置以支持 profile
            cc_spec_root=cc_spec_root if use_lock else None,  # v1.3：传入根目录以支持锁
        )

        # 创建结果收集器
        collector = ResultCollector()

        # 执行运行
        results = asyncio.run(
            _execute_with_progress(
                executor,
                collector,
                start_wave,
                total_waves,
                total_tasks,
                use_lock,  # v1.3：传入锁参数
                skip_locked,  # v1.3：传入跳过锁定任务参数
            )
        )

        # 显示结果
        _display_execution_results(collector)

        # 根据结果更新状态
        if collector.has_failures():
            _handle_execution_failure(status_path, change, collector)
        else:
            _handle_execution_success(status_path, change, collector, total_waves)

    except Exception as e:
        console.print(
            f"\n[red]错误：[/red] 执行失败：{e}",
            style="red",
        )
        raise typer.Exit(1)


async def _execute_with_progress(
    executor: SubAgentExecutor,
    collector: ResultCollector,
    start_wave: int,
    total_waves: int,
    total_tasks: int,
    use_lock: bool = True,  # v1.3：锁参数
    skip_locked: bool = False,  # v1.3：跳过被锁任务参数
) -> dict[int, list[ExecutionResult]]:
    """执行所有 wave，并展示进度。

    参数：
        executor：SubAgent 执行器实例
        collector：结果收集器实例
        start_wave：开始执行的 wave 编号
        total_waves：wave 总数
        total_tasks：任务总数
        use_lock：v1.3 - 是否使用锁机制
        skip_locked：v1.3 - 是否跳过被锁定的任务

    返回：
        一个字典：wave 编号 -> 结果列表
    """
    # 初始化进度跟踪器
    tracker = WaveProgressTracker(
        console=console,
        total_waves=total_waves,
        total_tasks=total_tasks,
    )

    # 开始执行
    collector.start_execution()
    all_results: dict[int, list[ExecutionResult]] = {}

    # 逐个执行 wave
    for wave in executor.doc.waves:
        if wave.wave_number < start_wave:
            # 跳过已完成的 wave
            tracker.completed_waves += 1
            continue

        # 获取该 wave 中待执行（idle）的任务
        idle_tasks = [t for t in wave.tasks if t.status == TaskStatus.IDLE]

        if not idle_tasks:
            # 该 wave 的任务已全部处理
            tracker.completed_waves += 1
            continue

        # 开始 wave
        task_ids = [t.task_id for t in idle_tasks]
        console.print(
            f"\n[bold cyan]波次 {wave.wave_number}[/bold cyan] - "
            f"正在执行 {len(idle_tasks)} 个任务...\n"
        )

        collector.start_wave(wave.wave_number)
        tracker.start_wave(wave.wave_number, task_ids)

        # 显示 wave 初始状态
        tracker.display()

        # 执行 wave (v1.3：支持锁机制)
        results = await executor.execute_wave(wave.wave_number, use_lock=use_lock, skip_locked=skip_locked)

        # 收集结果
        for result in results:
            collector.add_result(wave.wave_number, result)
            status = "completed" if result.success else "failed"
            tracker.update_task(wave.wave_number, result.task_id, status)

            # 显示任务结果 (v1.3：包含 agent_id)
            icon = "√" if result.success else "×"
            agent_info = f" [{result.agent_id}]" if result.agent_id else ""
            console.print(
                f"  {icon} [bold]{result.task_id}[/bold]{agent_info}: "
                f"{'已完成' if result.success else '失败'} "
                f"（{result.duration_seconds:.1f}秒）"
            )

        # 结束 wave
        collector.end_wave(wave.wave_number)
        tracker.complete_wave(wave.wave_number)
        all_results[wave.wave_number] = results

        # 检查失败项
        failed = [r for r in results if not r.success]
        if failed:
            console.print(
                f"\n[red]波次 {wave.wave_number} 有 {len(failed)} 个失败任务[/red]"
            )
            # 遇到失败则停止执行
            break

        console.print(
            f"\n[green]√ 波次 {wave.wave_number} 执行完成[/green]"
        )

    # 结束执行
    collector.end_execution()

    return all_results


def _display_task_summary(doc: TasksDocument) -> None:
    """显示任务摘要表。

    参数：
        doc：解析后的 TasksDocument
    """
    table = Table(title="任务摘要", border_style="cyan")
    table.add_column("波次", style="cyan", justify="center")
    table.add_column("任务 ID", style="white")
    table.add_column("状态", justify="center")
    table.add_column("依赖", style="dim")

    for wave in doc.waves:
        for i, task in enumerate(wave.tasks):
            # 获取状态图标
            status_icons = {
                TaskStatus.IDLE: "○ 待执行",
                TaskStatus.IN_PROGRESS: "… 进行中",
                TaskStatus.COMPLETED: "√ 已完成",
                TaskStatus.FAILED: "× 失败",
                TaskStatus.TIMEOUT: "! 超时",
            }
            status = status_icons.get(task.status, "? 未知")

            # 格式化依赖列表
            deps = ", ".join(task.dependencies) if task.dependencies else "-"

            # wave 编号仅在该 wave 的首个任务行显示
            wave_str = str(wave.wave_number) if i == 0 else ""

            table.add_row(wave_str, task.task_id, status, deps)

    console.print(table)


def _display_execution_plan(doc: TasksDocument, start_wave: int) -> None:
    """在演练（dry-run）模式下展示执行计划。

    参数：
        doc：解析后的 TasksDocument
        start_wave：开始执行的 wave 编号
    """
    console.print("[bold]执行计划：[/bold]\n")

    for wave in doc.waves:
        if wave.wave_number < start_wave:
            console.print(f"[dim]波次 {wave.wave_number} - 已跳过（已完成）[/dim]")
            continue

        # 获取待执行任务
        idle_tasks = [t for t in wave.tasks if t.status == TaskStatus.IDLE]

        if not idle_tasks:
            console.print(f"[dim]波次 {wave.wave_number} - 没有待执行任务[/dim]")
            continue

        console.print(f"[cyan]波次 {wave.wave_number}[/cyan] - {len(idle_tasks)} 个任务：")
        for task in idle_tasks:
            console.print(f"  - {task.task_id}: {task.name}")

        console.print()


def _find_resume_wave(doc: TasksDocument) -> int:
    """查找用于 resume 的第一个仍有待处理任务的 wave。

    参数：
        doc：解析后的 TasksDocument

    返回：
        起始 wave 编号（若无需 resume 则为 0）
    """
    for wave in doc.waves:
        # 检查该 wave 是否存在待执行/进行中任务
        for task in wave.tasks:
            if task.status in (TaskStatus.IDLE, TaskStatus.IN_PROGRESS, TaskStatus.FAILED):
                return wave.wave_number

    return 0


def _update_apply_stage_started(status_path: Path, total_waves: int) -> None:
    """更新状态，标记 apply 阶段已开始。

    参数：
        status_path：status.yaml 路径
        total_waves：wave 总数
    """
    try:
        state = load_state(status_path)

        state.current_stage = Stage.APPLY
        state.stages[Stage.APPLY] = StageInfo(
            status=StateTaskStatus.IN_PROGRESS,
            started_at=datetime.now().isoformat(),
            waves_completed=0,
            waves_total=total_waves,
        )

        update_state(status_path, state)

    except Exception as e:
        console.print(
            f"[yellow]警告：[/yellow] 无法更新状态：{e}",
            style="yellow",
        )


def _display_execution_results(collector: ResultCollector) -> None:
    """显示执行结果摘要。

    参数：
        collector：包含执行数据的结果收集器
    """
    summary = collector.get_summary()

    console.print("\n" + "=" * 60)
    console.print("[bold]执行摘要[/bold]")
    console.print("=" * 60 + "\n")

    # 构建摘要面板
    content_lines = [
        f"[cyan]波次数：[/cyan] {summary['total_waves']}",
        f"[cyan]任务数：[/cyan] {summary['total_tasks']}",
        f"[green]成功：[/green] {summary['successful_tasks']}",
        f"[red]失败：[/red] {summary['failed_tasks']}",
        f"[cyan]成功率：[/cyan] {summary['success_rate']:.1f}%",
        f"[cyan]总耗时：[/cyan] {summary['total_duration_seconds']:.1f} 秒",
    ]

    status_color = "green" if not collector.has_failures() else "red"
    panel = Panel(
        "\n".join(content_lines),
        title="[bold]执行结果[/bold]",
        border_style=status_color,
        padding=(1, 2),
    )
    console.print(panel)


def _handle_execution_success(
    status_path: Path,
    change_name: str,
    collector: ResultCollector,
    total_waves: int,
) -> None:
    """处理执行成功完成的情况。

    参数：
        status_path：status.yaml 路径
        change_name：变更名称
        collector：结果收集器
        total_waves：wave 总数
    """
    console.print(
        "\n[bold green]所有任务已成功完成！[/bold green]",
        style="green",
    )

    # 更新状态
    try:
        state = load_state(status_path)

        state.stages[Stage.APPLY] = StageInfo(
            status=StateTaskStatus.COMPLETED,
            started_at=state.stages.get(Stage.APPLY, StageInfo(status=StateTaskStatus.PENDING)).started_at,
            completed_at=datetime.now().isoformat(),
            waves_completed=total_waves,
            waves_total=total_waves,
        )

        update_state(status_path, state)
        console.print("[green]√[/green] 已将状态更新为 apply 阶段（完成）")

    except Exception as e:
        console.print(
            f"[yellow]警告：[/yellow] 无法更新状态：{e}",
            style="yellow",
        )

    # 展示下一步
    console.print("\n[bold]下一步：[/bold]")
    console.print("1. 查看执行结果")
    console.print("2. 运行 [cyan]cc-spec checklist[/cyan] 进行验收")

    console.print(f"\n[dim]变更：{change_name}[/dim]")


def _handle_execution_failure(
    status_path: Path,
    change_name: str,
    collector: ResultCollector,
) -> None:
    """处理执行失败的情况。

    参数：
        status_path：status.yaml 路径
        change_name：变更名称
        collector：结果收集器
    """
    console.print(
        "\n[bold red]执行失败！[/bold red]",
        style="red",
    )

    # 获取失败的 wave 与任务
    failed_waves = collector.get_failed_waves()

    console.print(f"\n[red]失败波次：{failed_waves}[/red]")

    # 显示详细的失败信息
    for wave_num in failed_waves:
        wave_result = collector.wave_results.get(wave_num)
        if wave_result:
            for result in wave_result.results:
                if not result.success:
                    console.print(
                        f"\n[red]任务 {result.task_id}：[/red] {result.error}"
                    )

    # 更新状态
    try:
        state = load_state(status_path)

        state.stages[Stage.APPLY] = StageInfo(
            status=StateTaskStatus.FAILED,
            started_at=state.stages.get(Stage.APPLY, StageInfo(status=StateTaskStatus.PENDING)).started_at,
            completed_at=datetime.now().isoformat(),
            waves_completed=len(collector.wave_results) - len(failed_waves),
            waves_total=state.stages.get(Stage.APPLY, StageInfo(status=StateTaskStatus.PENDING)).waves_total,
        )

        update_state(status_path, state)
        console.print("\n[yellow]![/yellow] 已将状态更新为 apply 阶段（失败）")

    except Exception as e:
        console.print(
            f"[yellow]警告：[/yellow] 无法更新状态：{e}",
            style="yellow",
        )

    # 展示下一步
    console.print("\n[bold]下一步：[/bold]")
    console.print("1. 查看上面失败的任务")
    console.print("2. 修复导致失败的问题")
    console.print(
        "3. 运行 [cyan]cc-spec clarify <task-id>[/cyan] 标记任务需要返工"
    )
    console.print(
        "4. 重新运行 [cyan]cc-spec apply --resume[/cyan] 继续执行"
    )

    console.print(f"\n[dim]变更：{change_name}[/dim]")

    raise typer.Exit(1)
