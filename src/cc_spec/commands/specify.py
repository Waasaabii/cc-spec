"""cc-spec 的 specify 命令实现。

该命令创建新的变更规格说明，步骤包括：
1. 校验变更名称格式
2. 创建变更目录结构
3. 基于模板生成 proposal.md
4. 使用默认状态初始化 status.yaml


"""

import re
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from cc_spec.core.id_manager import IDManager
from cc_spec.core.state import ChangeState, Stage, StageInfo, TaskStatus, update_state
from cc_spec.core.templates import copy_template
from cc_spec.rag.models import WorkflowStep
from cc_spec.rag.workflow import try_write_record
from cc_spec.ui.banner import show_banner
from cc_spec.utils.files import find_project_root, get_cc_spec_dir, get_changes_dir

console = Console()

# 变更名称校验正则：以小写字母开头，后续可包含小写字母、数字与连字符
CHANGE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")

# 默认 proposal 模板内容（当找不到模板文件时的兜底）
DEFAULT_PROPOSAL_TEMPLATE = """## Why
[Describe the motivation and problem statement]

## What Changes
[List the specific changes to be made]

## Impact
[Describe the impact and affected areas]
- Affected specs: [List spec files to be modified]
- Expected code: [Describe expected code changes]
"""


def validate_change_name(name: str) -> tuple[bool, str]:
    """校验变更名称格式。

    参数：
        name：要校验的变更名称

    返回：
        (is_valid, error_message)
    """
    if not name:
        return False, "变更名称不能为空"

    if not CHANGE_NAME_PATTERN.match(name):
        return False, (
            "变更名称必须以小写字母开头，并且只能包含小写字母、数字和连字符"
        )

    if len(name) > 64:
        return False, "变更名称长度不能超过 64 个字符"

    return True, ""


def specify(
    name_or_id: str = typer.Argument(
        ...,
        help="变更名称（例如 add-oauth）或 ID（例如 C-001）",
    ),
    template: str = typer.Option("default", "--template", "-t", help="要使用的模板类型"),
) -> None:
    """创建新的变更规格说明，或编辑已有变更。

    

    该命令会：
    1. 如果 name_or_id 是 ID（C-XXX），打开已有 proposal 进行编辑
    2. 如果 name_or_id 是名称，则创建新变更：
       - 校验变更名称格式
       - 创建 .cc-spec/changes/{name}/ 目录
       - 基于模板生成 proposal.md
       - 使用默认状态初始化 status.yaml
       - 为变更注册一个 ID

    示例：
        cc-spec specify add-oauth      # 创建新变更
        cc-spec specify C-001          # 编辑已有变更
    """
    # 显示启动 Banner
    show_banner(console)

    # 查找项目根目录
    project_root = find_project_root()
    if project_root is None:
        console.print(
            "[red]✗[/red] 当前目录不是 cc-spec 项目。"
            "请先运行 [bold]cc-spec init[/bold]。"
        )
        raise typer.Exit(1)

    cc_spec_root = get_cc_spec_dir(project_root)
    id_manager = IDManager(cc_spec_root)

    # 判断 name_or_id 是否为 ID（以 C- 开头）
    if name_or_id.startswith("C-"):
        # ID 模式：编辑已有变更
        _edit_existing_change(id_manager, cc_spec_root, project_root, name_or_id)
    else:
        # 名称模式：创建新变更
        _create_new_change(
            id_manager, project_root, cc_spec_root, name_or_id, template
        )


def _edit_existing_change(
    id_manager: IDManager,
    cc_spec_root: Path,
    project_root: Path,
    change_id: str,
) -> None:
    """通过 ID 编辑已有变更。

    参数：
        id_manager：ID 管理器实例
        cc_spec_root：.cc-spec 目录路径
        project_root：项目根目录路径
        change_id：变更 ID（例如 C-001）
    """
    entry = id_manager.get_change_entry(change_id)
    if not entry:
        console.print(f"[red]✗[/red] 未找到变更：{change_id}")
        raise typer.Exit(1)

    change_path = cc_spec_root / entry.path
    proposal_path = change_path / "proposal.md"

    if not proposal_path.exists():
        console.print(f"[red]✗[/red] 未找到提案文件：{proposal_path}")
        raise typer.Exit(1)

    # 显示提示信息
    console.print()
    console.print(f"[cyan]正在编辑变更：[/cyan] [bold]{entry.name}[/bold] ({change_id})")
    console.print()
    console.print(Panel(
        f"[bold]文件：[/bold]\n"
        f"  • {proposal_path.relative_to(project_root)}\n\n"
        f"[bold]下一步：[/bold]\n"
        f"  1. 编辑 [cyan]{proposal_path.relative_to(project_root)}[/cyan]\n"
        f"     包含 4 个章节：背景与目标、用户故事、技术决策、成功标准\n"
        f"  2. 运行 [bold]cc-spec clarify {change_id}[/bold] 进行审查\n"
        f"  3. 运行 [bold]cc-spec plan {change_id}[/bold] 生成任务",
        title=f"[bold cyan]变更 {change_id}[/bold cyan]",
        border_style="cyan",
    ))

    # v0.1.5：写入 workflow record（尽力而为）
    try_write_record(
        project_root,
        step=WorkflowStep.SPECIFY,
        change_name=entry.name,
        inputs={"mode": "edit", "change_id": change_id},
        outputs={"proposal": str(proposal_path.relative_to(project_root))},
        notes="specify.edit",
    )


def _create_new_change(
    id_manager: IDManager,
    project_root: Path,
    cc_spec_root: Path,
    name: str,
    template: str,
) -> None:
    """使用给定名称创建新变更。

    参数：
        id_manager：ID 管理器实例
        project_root：项目根目录路径
        cc_spec_root：.cc-spec 目录路径
        name：变更名称
        template：模板类型
    """
    # 校验变更名称
    is_valid, error_msg = validate_change_name(name)
    if not is_valid:
        console.print(f"[red]✗[/red] 变更名称不合法：{error_msg}")
        raise typer.Exit(1)

    # 获取 changes 目录
    changes_dir = get_changes_dir(project_root)
    change_dir = changes_dir / name

    # 检查变更是否已存在
    if change_dir.exists():
        # 尝试查找已有 ID
        existing = id_manager.get_change_by_name(name)
        if existing:
            existing_id, _ = existing
            console.print(
                f"[red]✗[/red] Change [bold]{name}[/bold] already exists "
                f"(ID: {existing_id})\n"
                f"  Use [cyan]cc-spec specify {existing_id}[/cyan] to edit."
            )
        else:
            console.print(
                f"[red]✗[/red] Change [bold]{name}[/bold] already exists at:\n"
                f"  {change_dir}"
            )
        raise typer.Exit(1)

    # 创建变更目录
    change_dir.mkdir(parents=True, exist_ok=True)

    # 基于模板生成 proposal.md
    proposal_path = change_dir / "proposal.md"
    now = datetime.now().isoformat()
    try:
        # 尝试使用模板文件
        template_name = (
            f"{template}-proposal.md" if template != "default" else "spec-template.md"
        )
        copy_template(
            template_name,
            proposal_path,
            variables={
                "change_name": name,
                "project_name": project_root.name,
                "timestamp": now,
            },
        )
    except Exception:
        # 回退到默认模板内容
        proposal_path.write_text(DEFAULT_PROPOSAL_TEMPLATE, encoding="utf-8")

    # 初始化 status.yaml
    state = ChangeState(
        change_name=name,
        created_at=now,
        current_stage=Stage.SPECIFY,
    )

    # 将 specify 阶段标记为 in_progress
    state.stages[Stage.SPECIFY] = StageInfo(
        status=TaskStatus.IN_PROGRESS,
        started_at=now,
    )

    status_path = change_dir / "status.yaml"
    update_state(status_path, state)

    # 使用 ID 管理器注册变更
    change_id = id_manager.register_change(name, change_dir)

    # 显示成功提示
    console.print()
    console.print(f"[green]✓[/green] 已创建变更：[bold]{name}[/bold]（ID：{change_id}）")
    console.print()
    console.print(Panel(
        f"[bold]已创建文件：[/bold]\n"
        f"  • {proposal_path.relative_to(project_root)}\n"
        f"  • {status_path.relative_to(project_root)}\n\n"
        f"[bold]下一步：[/bold]\n"
        f"  1. 编辑 [cyan]{proposal_path.relative_to(project_root)}[/cyan] 补充说明：\n"
        f"     • 背景与目标：问题陈述、业务价值、技术约束\n"
        f"     • 用户故事：按优先级描述用户场景和验收标准\n"
        f"     • 技术决策：架构设计、模块划分、接口设计\n"
        f"     • 成功标准：功能、质量、性能、用户体验标准\n"
        f"  2. 运行 [bold]cc-spec clarify {change_id}[/bold] 审查并完善提案\n"
        f"  3. 运行 [bold]cc-spec plan {change_id}[/bold] 生成执行任务",
        title=f"[bold green]已创建变更 {change_id}[/bold green]",
        border_style="green",
    ))

    # v0.1.5：写入 workflow record（尽力而为）
    try_write_record(
        project_root,
        step=WorkflowStep.SPECIFY,
        change_name=name,
        inputs={"mode": "create", "template": template},
        outputs={
            "change_id": change_id,
            "proposal": str(proposal_path.relative_to(project_root)),
            "status": str(status_path.relative_to(project_root)),
        },
        notes="specify.create",
    )
