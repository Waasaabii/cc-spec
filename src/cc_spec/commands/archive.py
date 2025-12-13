"""cc-spec 的 archive 命令实现。

该命令会将一个已完成的变更归档，具体步骤：
1. 校验 checklist 阶段已完成
2. 展示将要合并的规格预览
3. 将 Delta specs 合并到主 specs/ 目录
4. 将变更目录按时间戳移动到 archive

v1.1：新增通过 ID 指定变更的支持。
"""

from datetime import datetime
from pathlib import Path
from typing import Optional
import shutil

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from cc_spec.core.delta import (
    DeltaSpec,
    generate_merge_preview,
    merge_delta,
    parse_delta,
    validate_delta,
)
from cc_spec.core.id_manager import IDManager
from cc_spec.core.state import (
    ChangeState,
    Stage,
    StageInfo,
    TaskStatus,
    get_current_change,
    load_state,
    update_state,
)
from cc_spec.utils.files import (
    ensure_dir,
    find_project_root,
    get_cc_spec_dir,
    get_changes_dir,
    get_specs_dir,
)

console = Console()


def archive_command(
    change_or_id: Optional[str] = typer.Argument(
        None,
        help="变更名称或 ID（例如 add-oauth 或 C-001）",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="跳过确认提示",
    ),
) -> None:
    """归档一个已完成的变更。

    v1.1：现支持通过变更 ID（例如 C-001）。

    该命令会执行以下步骤：
    1. 校验 checklist 阶段已完成
    2. 展示将要合并的规格预览
    3. 请求用户确认（除非使用 --force）
    4. 将 Delta specs 合并到主 specs/ 目录
    5. 将变更目录移动到 archive/YYYY-MM-DD-{name}/

    示例：
        cc-spec archive              # 归档当前激活的变更
        cc-spec archive add-oauth    # 按名称归档
        cc-spec archive C-001        # 按 ID 归档
        cc-spec archive C-001 -f     # 跳过确认
    """
    # 查找项目根目录
    project_root = find_project_root()
    if project_root is None:
        console.print(
            "[red]错误：[/red] 当前目录不是 cc-spec 项目，请先运行 'cc-spec init'。",
            style="red",
        )
        raise typer.Exit(1)

    cc_spec_root = get_cc_spec_dir(project_root)
    id_manager = IDManager(cc_spec_root)

    # 确定变更目录
    changes_dir = get_changes_dir(project_root)
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
                "请指定变更名称。",
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

    console.print(f"[cyan]正在归档变更：[/cyan] [bold]{change}[/bold]\n")

    # 加载并校验状态
    status_path = change_dir / "status.yaml"
    try:
        state = load_state(status_path)
    except Exception as e:
        console.print(
            f"[red]错误：[/red] 加载状态失败：{e}",
            style="red",
        )
        raise typer.Exit(1)

    # 校验 checklist 阶段已完成
    checklist_stage = state.stages.get(Stage.CHECKLIST)
    if not checklist_stage or checklist_stage.status != TaskStatus.COMPLETED:
        console.print(
            "[red]错误：[/red] 必须先完成 checklist 阶段才能归档。",
            style="red",
        )
        console.print(
            "\n[yellow]提示：[/yellow] 运行 [cyan]cc-spec checklist[/cyan] 完成验收。"
        )
        raise typer.Exit(1)

    console.print("[green]√[/green] checklist 阶段已完成\n")

    # 在 change/specs/ 目录中查找所有 Delta spec
    change_specs_dir = change_dir / "specs"
    if not change_specs_dir.exists():
        console.print(
            "[yellow]警告：[/yellow] 变更中未找到 specs/ 目录，无需合并。",
            style="yellow",
        )
        # 即使没有 specs 也允许归档
        delta_specs = []
    else:
        delta_specs = _find_delta_specs(change_specs_dir)

        if not delta_specs:
            console.print(
                "[yellow]警告：[/yellow] 未找到 Delta spec 文件，无需合并。",
                style="yellow",
            )

    # 展示合并预览
    if delta_specs:
        console.print("[bold cyan]合并预览：[/bold cyan]\n")

        specs_dir = get_specs_dir(project_root)

        for spec_file, delta_content in delta_specs:
            try:
                # 解析 Delta spec
                delta = parse_delta(delta_content)

                # 校验 Delta spec
                is_valid, errors = validate_delta(delta)
                    if not is_valid:
                        console.print(
                            f"[red]错误：[/red] Delta spec 校验失败："
                            f"{spec_file.relative_to(change_specs_dir)}：",
                            style="red",
                        )
                    for error in errors:
                        console.print(f"  - {error}", style="red")
                    raise typer.Exit(1)

                # 获取基础 spec 内容（如果存在）
                relative_path = spec_file.relative_to(change_specs_dir)
                base_spec_file = specs_dir / relative_path
                base_content = ""
                if base_spec_file.exists():
                    base_content = base_spec_file.read_text(encoding="utf-8")

                # 生成预览
                preview = generate_merge_preview(base_content, delta)

                # 在面板中显示预览
                panel = Panel(
                    preview,
                    title=f"[bold]{relative_path}[/bold]",
                    border_style="cyan",
                    padding=(1, 2),
                )
                console.print(panel)
                console.print()

            except Exception as e:
                console.print(
                    f"[red]错误：[/red] 解析 Delta spec 失败："
                    f"{spec_file.relative_to(change_specs_dir)}：{e}",
                    style="red",
                )
                raise typer.Exit(1)

    # 请求确认
    if not force:
        console.print("[bold]将执行以下操作：[/bold]")
        if delta_specs:
            console.print(
                f"  1. 合并 {len(delta_specs)} 个 Delta spec 到主 specs/ 目录"
            )
        console.print(
            f"  2. 将变更目录移动到 archive/{datetime.now().strftime('%Y-%m-%d')}-{change}/"
        )
        console.print()

        if not Confirm.ask("[bold]是否继续？[/bold]", default=False):
            console.print("[yellow]已取消归档。[/yellow]")
            raise typer.Exit(0)

    # 执行合并操作
    if delta_specs:
        console.print("\n[cyan]正在合并 Delta specs...[/cyan]")

        specs_dir = get_specs_dir(project_root)
        ensure_dir(specs_dir)

        for spec_file, delta_content in delta_specs:
            try:
                # 解析 Delta spec
                delta = parse_delta(delta_content)

                # 获取基础 spec 路径
                relative_path = spec_file.relative_to(change_specs_dir)
                base_spec_file = specs_dir / relative_path

                # 读取基础内容（新文件则为空）
                base_content = ""
                if base_spec_file.exists():
                    base_content = base_spec_file.read_text(encoding="utf-8")

                # 将 Delta 合并到基础 spec
                merged_content = merge_delta(base_content, delta)

                # 写入合并后的内容
                ensure_dir(base_spec_file.parent)
                base_spec_file.write_text(merged_content, encoding="utf-8")

                console.print(
                    f"[green]√[/green] 已合并 {relative_path}",
                )

            except Exception as e:
                console.print(
                    f"[red]错误：[/red] 合并失败："
                    f"{spec_file.relative_to(change_specs_dir)}：{e}",
                    style="red",
                )
                raise typer.Exit(1)

    # 将变更目录移动到 archive
    console.print("\n[cyan]正在将变更移动到归档...[/cyan]")

    archive_dir = changes_dir / "archive"
    ensure_dir(archive_dir)

    # 生成带时间戳的归档名称
    timestamp = datetime.now().strftime("%Y-%m-%d")
    archive_name = f"{timestamp}-{change}"
    archive_path = archive_dir / archive_name

    # 检查归档是否已存在
    if archive_path.exists():
        # 添加时间后缀以避免冲突
        time_suffix = datetime.now().strftime("%H%M%S")
        archive_name = f"{timestamp}-{change}-{time_suffix}"
        archive_path = archive_dir / archive_name
        console.print(
            f"[yellow]警告：[/yellow] 归档已存在，将使用 {archive_name}"
        )

    try:
        # 移动目录
        shutil.move(str(change_dir), str(archive_path))
        console.print(
            f"[green]√[/green] 已移动到 archive/{archive_name}/",
        )
    except Exception as e:
        console.print(
            f"[red]错误：[/red] 移动变更到归档失败：{e}",
            style="red",
        )
        raise typer.Exit(1)

    # 成功提示
    console.print(
        "\n[bold green]归档完成！[/bold green]",
        style="green",
    )

    if delta_specs:
        console.print(
            f"\n[dim]已合并 {len(delta_specs)} 个 spec 到 {specs_dir.relative_to(project_root)}[/dim]"
        )
    console.print(
        f"[dim]已归档到 {archive_path.relative_to(project_root)}[/dim]"
    )


def _find_delta_specs(specs_dir: Path) -> list[tuple[Path, str]]:
    """在 specs 目录中查找所有 Delta spec.md 文件。

    参数：
        specs_dir：要搜索的 specs 目录路径

    返回：
        (spec 文件路径, 内容) 的列表
    """
    delta_specs: list[tuple[Path, str]] = []

    # 递归查找所有 spec.md 文件
    for spec_file in specs_dir.rglob("spec.md"):
        try:
            content = spec_file.read_text(encoding="utf-8")

            # 检查是否为 Delta spec（标题包含 "# Delta:"）
            if "# Delta:" in content or "## ADDED Requirements" in content:
                delta_specs.append((spec_file, content))

        except Exception as e:
            console.print(
                f"[yellow]警告：[/yellow] 读取 {spec_file} 失败：{e}",
                style="yellow",
            )
            continue

    return delta_specs
