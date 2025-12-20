"""cc-spec  goto 命令。

该模块提供 goto 命令，用于在变更与任务之间导航。


"""

import subprocess
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from cc_spec.core.id_manager import IDManager, IDType
from cc_spec.core.state import ChangeState, Stage, TaskStatus, load_state
from cc_spec.ui.banner import show_banner
from cc_spec.ui.display import STAGE_NAMES, STATUS_ICONS, THEME
from cc_spec.utils.files import find_project_root, get_cc_spec_dir

console = Console()


def goto_command(
    id_: str = typer.Argument(
        ...,
        help="变更 ID（例如 C-001）或任务 ID（例如 C-001:02-MODEL）",
        metavar="ID",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="强制导航，忽略状态检查",
    ),
    execute: bool = typer.Option(
        False,
        "--execute",
        "-x",
        help=",
    ),
) -> None:
    """导航到指定的变更或任务。

    

    \b
    示例：
        cc-spec goto C-001              # 跳转到变更 C-001
        cc-spec goto C-001:02-MODEL     # 跳转到 C-001 中的任务 02-MODEL
        cc-spec goto my-feature         # 按名称跳转到变更
        cc-spec goto C-001 --force      # 强制跳转
        cc-spec goto C-001 --execute    # 跳转并直接执行所选命令
    """
    # 显示启动 Banner
    show_banner(console)

    project_root = find_project_root()
    if project_root is None:
        console.print(
            "[red]错误：[/red] 当前目录不是 cc-spec 项目，请先运行 'cc-spec init'。"
        )
        raise typer.Exit(1)

    cc_spec_root = get_cc_spec_dir(project_root)
    id_manager = IDManager(cc_spec_root)

    try:
        parsed = id_manager.parse_id(id_)
    except ValueError as e:
        console.print(f"[red]错误：[/red] {e}")
        raise typer.Exit(1)

    if parsed.type == IDType.CHANGE:
        _goto_change(id_manager, cc_spec_root, parsed.change_id or id_, force, execute)
    elif parsed.type == IDType.TASK:
        if not parsed.change_id or not parsed.task_id:
            console.print(f"[red]错误：[/red] 任务 ID 格式无效：{id_}")
            raise typer.Exit(1)
        _goto_task(id_manager, cc_spec_root, parsed.change_id, parsed.task_id, force, execute)
    elif parsed.type == IDType.SPEC:
        console.print(
            "[yellow]提示：[/yellow] 规格（spec）不支持导航。"
            "请使用 'cc-spec list specs' 查看。"
        )
    elif parsed.type == IDType.ARCHIVE:
        console.print(
            "[yellow]提示：[/yellow] 归档为只读。"
            "请使用 'cc-spec list archive' 查看。"
        )
    else:
        console.print(f"[red]错误：[/red] 未知 ID 类型：{id_}")
        raise typer.Exit(1)


def _goto_change(
    id_manager: IDManager,
    cc_spec_root: Path,
    change_id: str,
    force: bool,
    execute: bool,
) -> None:
    """跳转到变更并展示上下文相关选项。

    参数：
        id_manager：ID 管理器实例
        cc_spec_root：.cc-spec 目录路径
        change_id：要跳转的变更 ID
        force：是否强制跳转
        execute：是否直接执行所选命令
    """
    # 解析变更
    entry = id_manager.get_change_entry(change_id)
    if not entry:
        # 尝试按名称查找
        result = id_manager.get_change_by_name(change_id)
        if result:
            change_id, entry = result
        else:
            console.print(f"[red]错误：[/red] 未找到变更：{change_id}")
            raise typer.Exit(1)

    change_path = cc_spec_root / entry.path
    status_file = change_path / "status.yaml"

    if not status_file.exists():
        console.print(
            f"[red]错误：[/red] 未找到变更的状态文件：{change_id}"
        )
        raise typer.Exit(1)

    try:
        state = load_state(status_file)
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]错误：[/red] 加载状态失败：{e}")
        raise typer.Exit(1)

    # 展示变更信息面板
    _show_change_panel(change_id, entry.name, state)

    # 展示阶段相关选项
    _show_stage_options(change_id, state, force, execute)


def _show_change_panel(
    change_id: str,
    change_name: str,
    state: ChangeState,
) -> None:
    """显示变更的信息面板。

    参数：
        change_id：变更 ID
        change_name：可读名称
        state：变更状态
    """
    stage = state.current_stage
    stage_name = STAGE_NAMES.get(stage.value, stage.value)

    # 获取状态信息
    stage_info = state.stages.get(stage)
    status = stage_info.status.value if stage_info else "pending"
    status_icon = STATUS_ICONS.get(status, "○")
    status_color = THEME.get(status, "white")

    # 构建内容
    lines = [
        f"[cyan]变更：[/cyan] [bold]{change_name}[/bold]",
        f"[cyan]ID：[/cyan] {change_id}",
        f"[cyan]阶段：[/cyan] [bold]{stage_name}[/bold]",
        f"[cyan]状态：[/cyan] {status_icon} [{status_color}]{status}[/{status_color}]",
    ]

    # 若处于 apply 阶段则添加任务进度
    if stage == Stage.APPLY and stage_info:
        waves_completed = stage_info.waves_completed or 0
        waves_total = stage_info.waves_total or 0
        if waves_total > 0:
            lines.append(f"[cyan]进度：[/cyan] 波次 {waves_completed}/{waves_total}")

    # 添加任务摘要
    if state.tasks:
        completed = sum(1 for t in state.tasks if t.status == TaskStatus.COMPLETED)
        total = len(state.tasks)
        lines.append(f"[cyan]任务：[/cyan] {completed}/{total} 已完成")

    panel = Panel(
        "\n".join(lines),
        title=f"[bold]{change_id}[/bold]",
        border_style="cyan",
        padding=(1, 2),
    )
    console.print(panel)


def _show_stage_options(
    change_id: str,
    state: ChangeState,
    force: bool,
    execute: bool,
) -> None:
    """根据当前阶段展示上下文相关选项。

    参数：
        change_id：变更 ID
        state：变更状态
        force：是否强制跳转
        execute：是否直接执行所选命令
    """
    stage = state.current_stage
    options: list[tuple[str, str, str]] = []  # (key, label, command)：(编号, 展示文案, 命令)

    if stage == Stage.SPECIFY:
        options = [
            ("1", "编辑提案", f"cc-spec specify {change_id}"),
            ("2", "继续澄清", f"cc-spec clarify {change_id}"),
            ("3", "查看提案文件", "proposal.md"),
        ]

    elif stage == Stage.CLARIFY:
        options = [
            ("1", "审查任务", f"cc-spec clarify {change_id}"),
            ("2", "继续计划", f"cc-spec plan {change_id}"),
            ("3", "列出任务", f"cc-spec list tasks -c {change_id}"),
        ]

    elif stage == Stage.PLAN:
        options = [
            ("1", "编辑计划", f"cc-spec plan {change_id}"),
            ("2", "继续执行", f"cc-spec apply {change_id}"),
            ("3", "查看 tasks.md", "tasks.md"),
        ]

    elif stage == Stage.APPLY:
        stage_info = state.stages.get(stage)
        status = stage_info.status.value if stage_info else "pending"

        if status == "completed":
            options = [
                ("1", "运行验收", f"cc-spec checklist {change_id}"),
                ("2", "列出任务", f"cc-spec list tasks -c {change_id}"),
            ]
        else:
            options = [
                ("1", "继续执行", f"cc-spec apply {change_id}"),
                ("2", "列出任务", f"cc-spec list tasks -c {change_id}"),
                ("3", "标记任务返工", f"cc-spec clarify {change_id}"),
            ]

    elif stage == Stage.CHECKLIST:
        stage_info = state.stages.get(stage)
        status = stage_info.status.value if stage_info else "pending"

        if status == "completed":
            options = [
                ("1", "归档变更", f"cc-spec archive {change_id}"),
                ("2", "重新验收", f"cc-spec checklist {change_id}"),
            ]
        else:
            options = [
                ("1", "运行验收", f"cc-spec checklist {change_id}"),
                ("2", "返工失败任务", f"cc-spec clarify {change_id}"),
            ]

    elif stage == Stage.ARCHIVE:
        console.print(
            "[yellow]该变更已归档。[/yellow]"
        )
        console.print(
            f"[dim]查看归档文件：changes/archive/{state.change_name}[/dim]"
        )
        return

    # 显示选项
    console.print("\n[bold]下一步：[/bold]")
    for key, label, cmd in options:
        console.print(f"  [{key}] {label} [dim]({cmd})[/dim]")
    console.print("  [q] 退出")

    # 交互式选择
    console.print()
    choice = Prompt.ask("请选择一个选项", choices=[o[0] for o in options] + ["q"])

    if choice == "q":
        return

    # 找到所选项
    for key, label, cmd in options:
        if key == choice:
            console.print(f"\n[cyan]执行：[/cyan] {cmd}")
            # 
            if execute:
                _execute_command(cmd)
            break


def _goto_task(
    id_manager: IDManager,
    cc_spec_root: Path,
    change_id: str,
    task_id: str,
    force: bool,
    execute: bool,
) -> None:
    """跳转到指定任务。

    参数：
        id_manager：ID 管理器实例
        cc_spec_root：.cc-spec 目录路径
        change_id：变更 ID
        task_id：变更内的任务 ID
        force：是否强制跳转
        execute：是否直接执行所选命令
    """
    # 解析变更
    entry = id_manager.get_change_entry(change_id)
    if not entry:
        console.print(f"[red]错误：[/red] 未找到变更：{change_id}")
        raise typer.Exit(1)

    change_path = cc_spec_root / entry.path
    status_file = change_path / "status.yaml"

    if not status_file.exists():
        console.print(
            f"[red]错误：[/red] 未找到变更的状态文件：{change_id}"
        )
        raise typer.Exit(1)

    try:
        state = load_state(status_file)
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]错误：[/red] 加载状态失败：{e}")
        raise typer.Exit(1)

    # 在状态中查找任务
    task_info = None
    for t in state.tasks:
        if t.id == task_id:
            task_info = t
            break

    # 展示任务信息
    _show_task_panel(change_id, task_id, task_info, change_path)

    # 展示任务相关选项
    _show_task_options(change_id, task_id, task_info, force, execute)


def _show_task_panel(
    change_id: str,
    task_id: str,
    task_info: Any,
    change_path: Path,
) -> None:
    """显示任务的信息面板。

    参数：
        change_id：变更 ID
        task_id：任务 ID
        task_info：来自状态文件的任务信息（可能为 None）
        change_path：变更目录路径
    """
    full_id = f"{change_id}:{task_id}"

    if task_info:
        status = task_info.status.value
        wave = task_info.wave
    else:
        status = "unknown"
        wave = "?"

    status_icon = STATUS_ICONS.get(status, "○")
    status_color = THEME.get(status, "white")
    status_text = "未知" if status == "unknown" else status

    lines = [
        f"[cyan]任务：[/cyan] [bold]{task_id}[/bold]",
        f"[cyan]完整 ID：[/cyan] {full_id}",
        f"[cyan]波次：[/cyan] {wave}",
        f"[cyan]状态：[/cyan] {status_icon} [{status_color}]{status_text}[/{status_color}]",
    ]

    # 尝试从 tasks.md 读取补充信息
    tasks_file = change_path / "tasks.md"
    if tasks_file.exists():
        try:
            content = tasks_file.read_text(encoding="utf-8")
            # 查找任务段落
            import re
            pattern = rf"###\s+(?:Task|任务)[:：]\s*{re.escape(task_id)}.*?\n(.*?)(?=###\s+(?:Task|任务)[:：]|$)"
            match = re.search(pattern, content, re.DOTALL)
            if match:
                task_section = match.group(1)
                # 提取预估信息
                est_match = re.search(r"\*\*预估上下文\*\*:\s*~?(\d+[kK]?)", task_section)
                if est_match:
                    lines.append(f"[cyan]预估：[/cyan] {est_match.group(1)} token")
        except (OSError, UnicodeDecodeError):
            pass

    panel = Panel(
        "\n".join(lines),
        title=f"[bold]{full_id}[/bold]",
        border_style="cyan",
        padding=(1, 2),
    )
    console.print(panel)


def _show_task_options(
    change_id: str,
    task_id: str,
    task_info: Any,
    force: bool,
    execute: bool,
) -> None:
    """展示任务相关选项。

    参数：
        change_id：变更 ID
        task_id：任务 ID
        task_info：来自状态文件的任务信息
        force：是否强制跳转
        execute：是否直接执行所选命令
    """
    status = task_info.status.value if task_info else "unknown"
    full_id = f"{change_id}:{task_id}"
    options: list[tuple[str, str, str]] = []

    if status == "pending":
        options = [
            ("1", "开始执行", f"cc-spec apply {change_id}"),
            ("2", "查看任务详情", "tasks.md"),
        ]
    elif status == "in_progress":
        options = [
            ("1", "继续执行", f"cc-spec apply {change_id}"),
            ("2", "查看任务详情", "tasks.md"),
        ]
    elif status == "completed":
        options = [
            ("1", "运行验收", f"cc-spec checklist {change_id}"),
            ("2", "标记返工", f"cc-spec clarify {full_id}"),
        ]
    elif status == "failed":
        options = [
            ("1", "标记返工", f"cc-spec clarify {full_id}"),
            ("2", "重试执行", f"cc-spec apply {change_id}"),
            ("3", "查看执行日志", "execution-log.md"),
        ]
    else:
        options = [
            ("1", "查看变更", f"cc-spec goto {change_id}"),
            ("2", "列出任务", f"cc-spec list tasks -c {change_id}"),
        ]

    # 显示选项
    console.print("\n[bold]下一步：[/bold]")
    for key, label, cmd in options:
        console.print(f"  [{key}] {label} [dim]({cmd})[/dim]")
    console.print("  [q] 退出")

    # 交互式选择
    console.print()
    choice = Prompt.ask("请选择一个选项", choices=[o[0] for o in options] + ["q"])

    if choice == "q":
        return

    # 找到所选项
    for key, label, cmd in options:
        if key == choice:
            console.print(f"\n[cyan]执行：[/cyan] {cmd}")
            # 
            if execute:
                _execute_command(cmd)
            break


def _execute_command(cmd: str) -> None:
    """执行一个 cc-spec 命令。

    

    参数：
        cmd：要执行的命令字符串（例如 "cc-spec apply C-001"）
    """
    # 跳过非命令项（例如文件名）
    if not cmd.startswith("cc-spec"):
        console.print(f"[yellow]提示：[/yellow] '{cmd}' 是文件路径，不是命令")
        return

    console.print("\n[cyan]正在执行...[/cyan]")
    console.print()

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=False,  # 直接显示输出
            text=True,
        )
        if result.returncode != 0:
            console.print(
                f"\n[yellow]命令退出码：{result.returncode}[/yellow]"
            )
    except subprocess.SubprocessError as e:
        console.print(f"\n[red]执行命令出错：[/red] {e}")
