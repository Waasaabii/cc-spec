"""cc-spec 的 specify 命令实现。

该命令创建新的变更规格说明，步骤包括：
1. 校验变更名称格式
2. 创建变更目录结构
3. 基于模板生成 proposal.md
4. 使用默认状态初始化 status.yaml

v1.1：新增通过 ID 编辑既有变更的支持。
"""

import re
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from cc_spec.core.id_manager import IDManager, IDType
from cc_spec.core.state import ChangeState, Stage, StageInfo, TaskStatus, update_state
from cc_spec.core.templates import copy_template, get_template_path
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
        return False, "Change name cannot be empty"

    if not CHANGE_NAME_PATTERN.match(name):
        return False, (
            "Change name must start with a lowercase letter and "
            "contain only lowercase letters, numbers, and hyphens"
        )

    if len(name) > 64:
        return False, "Change name must be 64 characters or less"

    return True, ""


def specify(
    name_or_id: str = typer.Argument(..., help="Change name (e.g., add-oauth) or ID (e.g., C-001)"),
    template: str = typer.Option("default", "--template", "-t", help="Template type to use"),
) -> None:
    """创建新的变更规格说明，或编辑已有变更。

    v1.1：现支持使用 ID 编辑既有变更。

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
    # 查找项目根目录
    project_root = find_project_root()
    if project_root is None:
        console.print(
            "[red]✗[/red] Not in a cc-spec project. "
            "Run [bold]cc-spec init[/bold] first."
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
        console.print(f"[red]✗[/red] Change not found: {change_id}")
        raise typer.Exit(1)

    change_path = cc_spec_root / entry.path
    proposal_path = change_path / "proposal.md"

    if not proposal_path.exists():
        console.print(
            f"[red]✗[/red] Proposal file not found: {proposal_path}"
        )
        raise typer.Exit(1)

    # 显示提示信息
    console.print()
    console.print(f"[cyan]Editing change:[/cyan] [bold]{entry.name}[/bold] ({change_id})")
    console.print()
    console.print(Panel(
        f"[bold]Files:[/bold]\n"
        f"  • {proposal_path.relative_to(project_root)}\n\n"
        f"[bold]Next steps:[/bold]\n"
        f"  1. Edit [cyan]{proposal_path.relative_to(project_root)}[/cyan]\n"
        f"  2. Run [bold]cc-spec clarify {change_id}[/bold] to review\n"
        f"  3. Run [bold]cc-spec plan {change_id}[/bold] to generate tasks",
        title=f"[bold cyan]Change {change_id}[/bold cyan]",
        border_style="cyan",
    ))


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
        console.print(f"[red]✗[/red] Invalid change name: {error_msg}")
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
    try:
        # 尝试使用模板文件
        template_name = f"{template}-proposal.md" if template != "default" else "spec-template.md"
        copy_template(
            template_name,
            proposal_path,
            variables={
                "change_name": name,
                "project_name": project_root.name,
            },
        )
    except Exception:
        # 回退到默认模板内容
        proposal_path.write_text(DEFAULT_PROPOSAL_TEMPLATE, encoding="utf-8")

    # 初始化 status.yaml
    now = datetime.now().isoformat()
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

    # 使用 ID 管理器注册变更（v1.1）
    change_id = id_manager.register_change(name, change_dir)

    # 显示成功提示
    console.print()
    console.print(f"[green]✓[/green] Created change: [bold]{name}[/bold] (ID: {change_id})")
    console.print()
    console.print(Panel(
        f"[bold]Created files:[/bold]\n"
        f"  • {proposal_path.relative_to(project_root)}\n"
        f"  • {status_path.relative_to(project_root)}\n\n"
        f"[bold]Next steps:[/bold]\n"
        f"  1. Edit [cyan]{proposal_path.relative_to(project_root)}[/cyan] to describe:\n"
        f"     • Why: The motivation and problem\n"
        f"     • What Changes: Specific changes to make\n"
        f"     • Impact: Affected specs and expected code changes\n"
        f"  2. Run [bold]cc-spec clarify {change_id}[/bold] to review and refine the proposal\n"
        f"  3. Run [bold]cc-spec plan {change_id}[/bold] to generate execution tasks",
        title=f"[bold green]Change {change_id} Created[/bold green]",
        border_style="green",
    ))
