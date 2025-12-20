"""用于审查并标记任务返工的 clarify 命令。


"""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cc_spec.core.ambiguity.detector import (
    AmbiguityMatch,
    AmbiguityType,
    detect,
    get_type_description,
)
from cc_spec.core.id_manager import IDManager
from cc_spec.core.state import (
    ChangeState,
    TaskStatus,
    get_current_change,
    load_state,
    update_state,
)
from cc_spec.rag.models import WorkflowStep
from cc_spec.rag.workflow import try_write_record
from cc_spec.ui.banner import show_banner
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
        console.print("[yellow]当前变更中未找到任务[/yellow]")
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
        "[dim]运行 [cyan]cc-spec clarify <task-id>[/cyan] 将任务标记为返工[/dim]"
    )


def show_ambiguity_report(matches: list[AmbiguityMatch], file_path: Path) -> None:
    """展示歧义检测报告。

    以表格形式展示检测到的歧义，按类型分组。

    参数：
        matches: 检测到的歧义匹配列表
        file_path: 被检测的文件路径
    """
    if not matches:
        console.print(
            Panel(
                "[green]✓ 未检测到歧义[/green]\n\n"
                f"文件：{file_path}",
                title="[bold]歧义检测结果[/bold]",
                border_style="green",
            )
        )
        return

    # 按类型分组统计
    type_counts: dict[AmbiguityType, int] = {}
    for match in matches:
        type_counts[match.type] = type_counts.get(match.type, 0) + 1

    # 显示摘要面板
    summary_lines = [f"文件：{file_path}", f"检测到 {len(matches)} 处歧义："]
    for amb_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        summary_lines.append(f"  • {amb_type.value}: {count} 处")

    console.print(
        Panel(
            "\n".join(summary_lines),
            title="[bold yellow]歧义检测摘要[/bold yellow]",
            border_style="yellow",
        )
    )
    console.print()

    # 显示详细表格
    table = Table(
        title="歧义详情",
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("行号", justify="right", style="dim", width=6)
    table.add_column("类型", width=15)
    table.add_column("关键词", width=12)
    table.add_column("内容", overflow="fold")

    for match in matches:
        # 高亮关键词
        content = match.original_line.strip()
        if len(content) > 80:
            content = content[:77] + "..."

        table.add_row(
            str(match.line_number),
            match.type.value,
            f"[yellow]{match.keyword}[/yellow]",
            content,
        )

    console.print(table)
    console.print()

    # 显示类型说明
    console.print("[dim]歧义类型说明：[/dim]")
    for amb_type in type_counts.keys():
        console.print(f"  [cyan]{amb_type.value}[/cyan]: {get_type_description(amb_type)}")
    console.print()

    # 显示建议
    console.print(
        "[dim]建议：请在 proposal.md 中补充以上歧义点的具体说明，"
        "或运行 [cyan]cc-spec clarify[/cyan] 标记需要返工的任务[/dim]"
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
        console.print(f"[red]错误：[/red] 未找到任务 '{task_id}'")
        raise typer.Exit(1)

    # 展示当前任务状态
    console.print()
    console.print(
        Panel(
            f"[cyan]任务 ID：[/cyan] {task.id}\n"
            f"[cyan]状态：[/cyan] {task.status.value}\n"
            f"[cyan]波次：[/cyan] {task.wave}",
            title="[bold]任务详情[/bold]",
            border_style="cyan",
        )
    )
    console.print()

    # 若 tasks.md 中有记录则展示执行历史
    tasks_md = change_dir / "tasks.md"
    if tasks_md.exists():
        console.print("[dim]正在检查 tasks.md 中的执行历史...[/dim]")
        console.print()

    # 确认返工
    if task.status == TaskStatus.PENDING:
        console.print(
            "[yellow]提示：[/yellow] 该任务已经是待执行状态（尚未开始）"
        )
        console.print()

    confirmed = confirm_action(
        console,
        f"将任务 '{task_id}' 标记为返工吗？\n\n"
        "这会把任务状态重置为 'pending'，并允许重新规划该任务。",
        default=False,
        warning=False,
    )

    if not confirmed:
        console.print("[dim]已取消操作[/dim]")
        raise typer.Exit(0)

    # 将任务状态更新为 pending
    for t in state.tasks:
        if t.id == task_id:
            t.status = TaskStatus.PENDING
            break

    # 保存更新后的状态
    update_state(state_path, state)

    console.print()
    console.print(f"[green]✓[/green] 已将任务 '{task_id}' 标记为返工")
    console.print()
    console.print(
        "[dim]你现在可以在 [cyan]tasks.md[/cyan] 中更新任务详情，并重新运行 "
        "[cyan]cc-spec apply[/cyan][/dim]"
    )

    # v0.1.5：写入 workflow record（尽力而为）
    try:
        project_root = change_dir.parent.parent.parent
    except Exception:
        project_root = Path.cwd()
    try_write_record(
        project_root,
        step=WorkflowStep.CLARIFY,
        change_name=state.change_name,
        task_id=task_id,
        outputs={"action": "rework", "new_status": TaskStatus.PENDING.value},
        notes="clarify.rework",
    )


@app.command()
def clarify(
    id_or_task: str = typer.Argument(
        None,
        help="变更/任务 ID（C-001、C-001:task-id）或任务 ID",
    ),
    change: str = typer.Option(
        None,
        "--change",
        "-c",
        help="变更名称或 ID（已弃用，建议使用位置参数）",
    ),
    detect_ambiguity: bool = typer.Option(
        False,
        "--detect",
        "-d",
        help="检测 proposal.md 中的歧义",
    ),
) -> None:
    """审查任务并将其标记为返工。

    
    - C-001：显示变更 C-001 的全部任务
    - C-001:02-MODEL：将指定任务标记为返工
    - 02-MODEL：在当前变更中将任务标记为返工（旧格式）

    不带参数时：展示当前变更中的全部任务。
    带参数时：将对应任务标记为返工（重置状态为 pending）。

    

    示例：
        cc-spec clarify                     # 显示所有任务
        cc-spec clarify --detect            # 检测当前变更的歧义
        cc-spec clarify -d C-001            # 检测指定变更的歧义
        cc-spec clarify C-001               # 显示变更 C-001 的任务
        cc-spec clarify C-001:02-MODEL      # 将任务 02-MODEL 标记为返工
        cc-spec clarify 02-MODEL            # 在当前变更中标记任务
        cc-spec clarify 02-MODEL -c C-001   # 旧用法：通过选项指定变更
    """
    # 显示启动 Banner
    show_banner(console)

    # 查找项目根目录
    project_root = find_project_root()
    if project_root is None:
        console.print(
            "[red]错误：[/red] 当前目录不是 cc-spec 项目。"
            "请先运行 [cyan]cc-spec init[/cyan]。"
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
            console.print(f"[red]错误：[/red] 未找到变更：{change_id}")
            raise typer.Exit(1)
        change_name = entry.name

    # 获取变更状态
    if change_name:
        change_dir = cc_spec_root / "changes" / change_name
        if not change_dir.exists():
            console.print(f"[red]错误：[/red] 未找到变更 '{change_name}'")
            raise typer.Exit(1)

        state_path = change_dir / "status.yaml"
        if not state_path.exists():
            console.print(
                f"[red]错误：[/red] 变更 '{change_name}' 缺少 status.yaml 文件"
            )
            raise typer.Exit(1)

        state = load_state(state_path)
    else:
        # 获取当前变更
        state = get_current_change(cc_spec_root)
        if state is None:
            console.print(
                "[yellow]未找到激活的变更。[/yellow]\n"
                "运行 [cyan]cc-spec specify <name>[/cyan] 创建新的变更。"
            )
            raise typer.Exit(1)

        change_dir = cc_spec_root / "changes" / state.change_name
        state_path = change_dir / "status.yaml"

    # 如果启用歧义检测模式
    if detect_ambiguity:
        proposal_path = change_dir / "proposal.md"
        if not proposal_path.exists():
            console.print(
                f"[red]错误：[/red] 变更 '{state.change_name}' 缺少 proposal.md 文件"
            )
            raise typer.Exit(1)

        # 读取 proposal.md 并检测歧义
        content = proposal_path.read_text(encoding="utf-8")
        matches = detect(content)
        show_ambiguity_report(matches, proposal_path)

        # v0.1.5：写入 workflow record（尽力而为）
        try_write_record(
            project_root,
            step=WorkflowStep.CLARIFY,
            change_name=state.change_name,
            inputs={"mode": "detect_ambiguity"},
            outputs={
                "proposal": str(proposal_path.relative_to(project_root)),
                "matches": len(matches),
            },
            notes="clarify.detect",
        )
        return

    # 执行对应操作
    if task_id is None:
        # 显示任务列表
        show_task_list(state)
    else:
        # 返工指定任务
        rework_task(state, task_id, state_path, change_dir)
