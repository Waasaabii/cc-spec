"""用于审查并标记任务返工的 clarify 命令。

v1.1：新增支持通过 ID 指定变更与任务。
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from cc_spec.core.id_manager import IDManager, IDType
from cc_spec.core.state import (
    ChangeState,
    Stage,
    TaskStatus,
    get_current_change,
    load_state,
    update_state,
)
from cc_spec.ui.display import show_status_panel, show_task_table
from cc_spec.ui.prompts import confirm_action
from cc_spec.utils.files import find_project_root, get_cc_spec_dir

app = typer.Typer()
console = Console()


def find_cc_spec_root() -> Path | None:
    """在当前目录或其父目录中查找 .cc-spec 目录。

    返回：
        .cc-spec 目录路径；未找到则返回 None。
    """
    current = Path.cwd()
    while current != current.parent:
        cc_spec_dir = current / ".cc-spec"
        if cc_spec_dir.exists() and cc_spec_dir.is_dir():
            return cc_spec_dir
        current = current.parent
    return None


def find_change_dir(cc_spec_root: Path, change_name: str) -> Path | None:
    """根据名称查找变更目录。

    参数：
        cc_spec_root：.cc-spec 目录路径
        change_name：变更名称

    返回：
        变更目录路径；未找到则返回 None。
    """
    changes_dir = cc_spec_root / "changes"
    if not changes_dir.exists():
        return None

    change_dir = changes_dir / change_name
    if change_dir.exists() and change_dir.is_dir():
        return change_dir

    return None


def show_task_list(state: ChangeState) -> None:
    """展示当前状态下的任务列表。

    参数：
        state：当前变更状态
    """
    if not state.tasks:
        console.print("[yellow]No tasks found in current change[/yellow]")
        return

    # 构建用于展示的任务列表
    tasks_display = []
    for task in state.tasks:
        tasks_display.append(
            {
                "id": task.id,
                "status": task.status.value,
                "wave": task.wave,
                "dependencies": [],  # status.yaml 中不存储依赖
                "estimate": "",  # status.yaml 中不存储预估
            }
        )

    # 显示状态面板与任务表
    show_status_panel(
        console,
        change_name=state.change_name,
        current_stage=state.current_stage.value,
    )
    console.print()
    show_task_table(console, tasks_display, show_wave=True, show_dependencies=False)

    # 显示使用说明
    console.print()
    console.print(
        "[dim]Run [cyan]cc-spec clarify <task-id>[/cyan] to mark a task for rework[/dim]"
    )


def rework_task(
    state: ChangeState, task_id: str, state_path: Path, change_dir: Path
) -> None:
    """标记某个任务为返工。

    参数：
        state：当前变更状态
        task_id：要返工的任务 ID
        state_path：status.yaml 文件路径
        change_dir：变更目录路径
    """
    # 查找任务
    task = None
    for t in state.tasks:
        if t.id == task_id:
            task = t
            break

    if task is None:
        console.print(f"[red]Error:[/red] Task '{task_id}' not found")
        raise typer.Exit(1)

    # 展示当前任务状态
    console.print()
    console.print(
        Panel(
            f"[cyan]Task ID:[/cyan] {task.id}\n"
            f"[cyan]Status:[/cyan] {task.status.value}\n"
            f"[cyan]Wave:[/cyan] {task.wave}",
            title="[bold]Task Details[/bold]",
            border_style="cyan",
        )
    )
    console.print()

    # 若 tasks.md 中有记录则展示执行历史
    tasks_md = change_dir / "tasks.md"
    if tasks_md.exists():
        console.print("[dim]Checking tasks.md for execution history...[/dim]")
        console.print()

    # 确认返工
    if task.status == TaskStatus.PENDING:
        console.print(
            "[yellow]Note:[/yellow] This task is already pending (not started yet)"
        )
        console.print()

    confirmed = confirm_action(
        console,
        f"Mark task '{task_id}' for rework?\n\n"
        "This will reset the task status to 'pending' and allow it to be re-planned.",
        default=False,
        warning=False,
    )

    if not confirmed:
        console.print("[dim]Operation cancelled[/dim]")
        raise typer.Exit(0)

    # 将任务状态更新为 pending
    for t in state.tasks:
        if t.id == task_id:
            t.status = TaskStatus.PENDING
            break

    # 保存更新后的状态
    update_state(state_path, state)

    console.print()
    console.print(f"[green]✓[/green] Task '{task_id}' marked for rework")
    console.print()
    console.print(
        "[dim]You can now update the task details in [cyan]tasks.md[/cyan] "
        "and re-run [cyan]cc-spec apply[/cyan][/dim]"
    )


@app.command()
def clarify(
    id_or_task: str = typer.Argument(None, help="Change/Task ID (C-001, C-001:task-id) or task ID"),
    change: str = typer.Option(None, "--change", "-c", help="Change name or ID (deprecated, use positional arg)"),
) -> None:
    """审查任务并将其标记为返工。

    v1.1：现在支持以下 ID 格式：
    - C-001：显示变更 C-001 的全部任务
    - C-001:02-MODEL：将指定任务标记为返工
    - 02-MODEL：在当前变更中将任务标记为返工（旧格式）

    不带参数时：展示当前变更中的全部任务。
    带参数时：将对应任务标记为返工（重置状态为 pending）。

    示例：
        cc-spec clarify                     # 显示所有任务
        cc-spec clarify C-001               # 显示变更 C-001 的任务
        cc-spec clarify C-001:02-MODEL      # 将任务 02-MODEL 标记为返工
        cc-spec clarify 02-MODEL            # 在当前变更中标记任务
        cc-spec clarify 02-MODEL -c C-001   # 旧用法：通过选项指定变更
    """
    # 查找项目根目录
    project_root = find_project_root()
    if project_root is None:
        console.print(
            "[red]Error:[/red] Not in a cc-spec project. "
            "Run [cyan]cc-spec init[/cyan] first."
        )
        raise typer.Exit(1)

    cc_spec_root = get_cc_spec_dir(project_root)
    id_manager = IDManager(cc_spec_root)

    # 解析 id_or_task 以确定模式
    task_id: str | None = None
    change_id: str | None = None
    change_name: str | None = change

    if id_or_task:
        if id_or_task.startswith("C-"):
            if ":" in id_or_task:
                # 任务 ID 格式：C-001:02-MODEL
                parsed = id_manager.parse_id(id_or_task)
                change_id = parsed.change_id
                task_id = parsed.task_id
            else:
                # 变更 ID 格式：C-001
                change_id = id_or_task
        else:
            # 旧任务 ID 格式：02-MODEL
            task_id = id_or_task

    # 解析变更
    if change_id:
        entry = id_manager.get_change_entry(change_id)
        if not entry:
            console.print(f"[red]Error:[/red] Change not found: {change_id}")
            raise typer.Exit(1)
        change_name = entry.name

    # 获取变更状态
    if change_name:
        change_dir = cc_spec_root / "changes" / change_name
        if not change_dir.exists():
            console.print(f"[red]Error:[/red] Change '{change_name}' not found")
            raise typer.Exit(1)

        state_path = change_dir / "status.yaml"
        if not state_path.exists():
            console.print(
                f"[red]Error:[/red] Change '{change_name}' has no status.yaml file"
            )
            raise typer.Exit(1)

        state = load_state(state_path)
    else:
        # 获取当前变更
        state = get_current_change(cc_spec_root)
        if state is None:
            console.print(
                "[yellow]No active change found.[/yellow]\n"
                "Run [cyan]cc-spec specify <name>[/cyan] to create a new change."
            )
            raise typer.Exit(1)

        change_dir = cc_spec_root / "changes" / state.change_name
        state_path = change_dir / "status.yaml"

    # 执行对应操作
    if task_id is None:
        # 显示任务列表
        show_task_list(state)
    else:
        # 返工指定任务
        rework_task(state, task_id, state_path, change_dir)
