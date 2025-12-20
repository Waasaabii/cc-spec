"""cc-spec 的 plan 命令实现。

根据变更提案生成执行计划（tasks.yaml）。

v1.1：新增通过 ID 指定变更的支持。
v1.2：移除 design.md 生成，技术决策已整合到 proposal.md。
v1.3：只生成 tasks.yaml（移除 tasks.md 支持）。
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import typer
import yaml
from rich.console import Console

from cc_spec.core.id_manager import IDManager
from cc_spec.core.state import (
    Stage,
    StageInfo,
    TaskStatus,
    load_state,
    update_state,
)
from cc_spec.rag.models import WorkflowStep
from cc_spec.rag.workflow import try_write_record
from cc_spec.ui.banner import show_banner
from cc_spec.ui.display import show_task_table
from cc_spec.utils.files import find_project_root, get_cc_spec_dir

console = Console()


def plan_command(
    change_or_id: Optional[str] = typer.Argument(
        None,
        help="变更名称或 ID（例如 add-oauth 或 C-001）",
    ),
) -> None:
    """生成执行计划（tasks.yaml）。

    v1.1：现支持通过变更 ID（例如 C-001）。
    v1.2：移除 design.md 生成，技术决策已整合到 proposal.md。
    v1.3：只生成 tasks.yaml（移除 tasks.md 支持）。

    该命令读取 proposal.md 并生成 tasks.yaml - 紧凑的结构化任务文件（供 SubAgent 使用）。

    示例：
        cc-spec plan              # 为当前激活的变更生成计划
        cc-spec plan add-oauth    # 按名称生成
        cc-spec plan C-001        # 按 ID 生成
    """
    # 显示启动 Banner
    show_banner(console)

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

        change_dir = cc_spec_root / "changes" / change
    else:
        # 查找当前激活的变更
        from cc_spec.core.state import get_current_change

        current_state = get_current_change(cc_spec_root)
        if not current_state:
            console.print(
                "[red]错误：[/red] 未找到当前激活的变更。"
                "请指定变更名称，或先运行 'cc-spec specify'。",
                style="red",
            )
            raise typer.Exit(1)

        change = current_state.change_name
        change_dir = cc_spec_root / "changes" / change

    if not change_dir.exists():
        console.print(f"[red]错误：[/red] 未找到变更 '{change}'。", style="red")
        raise typer.Exit(1)

    # 检查 proposal.md 是否存在
    proposal_path = change_dir / "proposal.md"
    if not proposal_path.exists():
        console.print(
            f"[red]错误：[/red] 在 {change_dir} 中未找到 proposal.md",
            style="red",
        )
        raise typer.Exit(1)

    console.print(f"[cyan]正在规划变更：[/cyan] [bold]{change}[/bold]")

    # 读取提案内容
    proposal_content = proposal_path.read_text(encoding="utf-8")
    console.print(f"[dim]已读取 proposal（{len(proposal_content)} 个字符）[/dim]")

    tasks_yaml_path = change_dir / "tasks.yaml"

    console.print("\n[cyan]正在生成执行计划...[/cyan]")

    # 生成 tasks.yaml
    try:
        _create_basic_tasks_yaml(tasks_yaml_path, change)
        console.print("[green]√[/green] 已生成 tasks.yaml")
    except Exception as e:
        console.print(
            f"[red]错误：[/red] 无法生成 tasks.yaml：{e}",
            style="red",
        )
        raise typer.Exit(1)

    # 校验依赖关系
    console.print("\n[cyan]正在校验任务依赖...[/cyan]")
    validation_result = _validate_tasks_yaml_dependencies(tasks_yaml_path)
    if validation_result["valid"]:
        console.print("[green]√[/green] 依赖关系校验通过")
    else:
        console.print(
            f"[yellow]警告：[/yellow] {validation_result['message']}",
            style="yellow",
        )

    # 更新状态到 plan 阶段
    status_path = change_dir / "status.yaml"
    try:
        state = load_state(status_path)

        # 将阶段更新为 plan
        state.current_stage = Stage.PLAN
        state.stages[Stage.PLAN] = StageInfo(
            status=TaskStatus.COMPLETED,
            started_at=datetime.now().isoformat(),
            completed_at=datetime.now().isoformat(),
        )

        update_state(status_path, state)
        console.print("\n[green]√[/green] 已将状态更新到 plan 阶段")

    except Exception as e:
        console.print(
            f"[yellow]警告：[/yellow] 无法更新状态：{e}",
            style="yellow",
        )

    # 展示任务概览
    console.print("\n[bold cyan]任务概览：[/bold cyan]")
    tasks_summary = _parse_tasks_yaml_summary(tasks_yaml_path)
    if tasks_summary:
        show_task_table(console, tasks_summary, show_wave=True, show_dependencies=True)
    else:
        console.print("[dim]（无任务可展示）[/dim]")

    # 展示下一步
    console.print(
        "\n[bold green]计划生成成功！[/bold green]",
        style="green",
    )
    console.print("\n[bold]下一步：[/bold]")
    console.print("1. 查看并编辑 tasks.yaml，完善任务拆解")
    console.print("2. 运行 [cyan]cc-spec apply[/cyan] 执行任务")

    # 显示生成的文件
    try:
        rel_path = tasks_yaml_path.relative_to(Path.cwd())
    except ValueError:
        rel_path = tasks_yaml_path
    console.print(f"\n[dim]已生成文件：[/dim]\n  - {rel_path}")

    # v0.1.5：写入 workflow record（尽力而为）
    try_write_record(
        project_root,
        step=WorkflowStep.PLAN,
        change_name=change,
        inputs={"proposal_chars": len(proposal_content)},
        outputs={
            "tasks_yaml": str(tasks_yaml_path.relative_to(project_root)),
            "dependency_validation": validation_result,
        },
        notes="plan.generated",
    )


def _create_basic_tasks_yaml(tasks_yaml_path: Path, change_name: str) -> None:
    """创建基础 tasks.yaml 结构。"""
    data = {
        "version": "1.6",
        "change": change_name,
        "tasks": {
            "01-SETUP": {
                "wave": 0,
                "name": "初始化与准备",
                "tokens": "30k",
                "deps": [],
                "docs": [f".cc-spec/changes/{change_name}/proposal.md"],
                "code": [],
                "checklist": [
                    "分析需求",
                    "设计方案",
                    "实现功能",
                    "编写测试",
                ],
            }
        },
    }

    yaml_content = yaml.dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    tasks_yaml_path.write_text(yaml_content, encoding="utf-8")


def _validate_tasks_yaml_dependencies(tasks_yaml_path: Path) -> dict[str, Any]:
    """校验 tasks.yaml 中的任务依赖关系。

    返回：
        包含键：valid（bool）、message（str）、tasks（list）的字典
    """
    try:
        content = tasks_yaml_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)

        if not data or "tasks" not in data:
            return {
                "valid": True,
                "message": "tasks.yaml 中未找到任何任务",
                "tasks": [],
            }

        tasks = data["tasks"]
        task_ids = set(tasks.keys())
        invalid_deps = []

        for task_id, task_data in tasks.items():
            deps = task_data.get("deps", [])
            for dep in deps:
                if dep not in task_ids:
                    invalid_deps.append((task_id, dep))

        if invalid_deps:
            dep_str = "，".join(f"{t} 依赖 {d}" for t, d in invalid_deps)
            return {
                "valid": False,
                "message": f"无效依赖：{dep_str}",
                "tasks": list(task_ids),
            }

        return {
            "valid": True,
            "message": f"共找到 {len(task_ids)} 个任务，依赖关系均有效",
            "tasks": list(task_ids),
        }

    except Exception as e:
        return {"valid": False, "message": f"解析任务失败：{e}", "tasks": []}


def _parse_tasks_yaml_summary(tasks_yaml_path: Path) -> list[dict[str, Any]]:
    """解析 tasks.yaml，提取用于展示的任务摘要。

    返回：
        任务字典列表，包含键：id、wave、status、estimate、dependencies
    """
    try:
        content = tasks_yaml_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)

        if not data or "tasks" not in data:
            return []

        tasks = []
        for task_id, task_data in data["tasks"].items():
            tasks.append(
                {
                    "id": task_id,
                    "wave": task_data.get("wave", 0),
                    "status": task_data.get("status", "pending"),
                    "estimate": task_data.get("tokens", "N/A"),
                    "dependencies": task_data.get("deps", []),
                }
            )

        # 按 wave 排序
        tasks.sort(key=lambda x: (x["wave"], x["id"]))
        return tasks

    except Exception as e:
        console.print(f"[yellow]警告：[/yellow] 无法解析任务：{e}")
        return []
