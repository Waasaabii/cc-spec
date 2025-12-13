"""cc-spec 的 plan 命令实现。

根据变更提案生成执行计划（tasks.md）与技术设计（design.md）。

v1.1：新增通过 ID 指定变更的支持。
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from cc_spec.core.id_manager import IDManager
from cc_spec.core.state import (
    ChangeState,
    Stage,
    StageInfo,
    TaskStatus,
    load_state,
    update_state,
)
from cc_spec.core.templates import copy_template, render_template
from cc_spec.ui.display import show_status_panel, show_task_table
from cc_spec.utils.files import find_project_root, get_cc_spec_dir

console = Console()


def plan_command(
    change_or_id: Optional[str] = typer.Argument(
        None,
        help="Change name or ID (e.g., add-oauth or C-001)",
    ),
) -> None:
    """生成执行计划（tasks.md）与技术设计（design.md）。

    v1.1：现支持通过变更 ID（例如 C-001）。

    该命令读取 proposal.md 并生成：
    1. tasks.md - 按 Wave 分组的任务拆解
    2. design.md - 技术决策与架构设计

    示例：
        cc-spec plan              # 为当前激活的变更生成计划
        cc-spec plan add-oauth    # 按名称生成
        cc-spec plan C-001        # 按 ID 生成
    """
    # 查找项目根目录
    project_root = find_project_root()
    if project_root is None:
        console.print(
            "[red]Error:[/red] Not a cc-spec project. Run 'cc-spec init' first.",
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
                console.print(f"[red]Error:[/red] Change not found: {change_or_id}")
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
                "[red]Error:[/red] No active change found. "
                "Please specify a change name or run 'cc-spec specify' first.",
                style="red",
            )
            raise typer.Exit(1)

        change = current_state.change_name
        change_dir = cc_spec_root / "changes" / change

    if not change_dir.exists():
        console.print(f"[red]Error:[/red] Change '{change}' not found.", style="red")
        raise typer.Exit(1)

    # 检查 proposal.md 是否存在
    proposal_path = change_dir / "proposal.md"
    if not proposal_path.exists():
        console.print(
            f"[red]Error:[/red] proposal.md not found in {change_dir}",
            style="red",
        )
        raise typer.Exit(1)

    console.print(f"[cyan]Planning change:[/cyan] [bold]{change}[/bold]")

    # 读取提案内容
    proposal_content = proposal_path.read_text(encoding="utf-8")
    console.print(f"[dim]Read proposal ({len(proposal_content)} characters)[/dim]")

    # 基于模板生成 tasks.md
    tasks_path = change_dir / "tasks.md"
    design_path = change_dir / "design.md"

    console.print("\n[cyan]Generating execution plan...[/cyan]")

    # 准备模板变量
    template_vars = {
        "change_name": change,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "timestamp": datetime.now().isoformat(),
    }

    # 生成 tasks.md
    try:
        # 尝试使用模板
        copy_template(
            "tasks-template.md",
            tasks_path,
            variables=template_vars,
        )
        console.print(f"[green]✓[/green] Generated tasks.md")
    except Exception as e:
        # 若模板不存在，则创建基础结构
        console.print(
            f"[yellow]Warning:[/yellow] Template not found, creating basic structure"
        )
        _create_basic_tasks_md(tasks_path, change, proposal_content)
        console.print(f"[green]✓[/green] Created basic tasks.md")

    # 生成 design.md
    try:
        copy_template(
            "plan-template.md",
            design_path,
            variables=template_vars,
        )
        console.print(f"[green]✓[/green] Generated design.md")
    except Exception as e:
        # 创建基础结构
        console.print(
            f"[yellow]Warning:[/yellow] Template not found, creating basic structure"
        )
        _create_basic_design_md(design_path, change, proposal_content)
        console.print(f"[green]✓[/green] Created basic design.md")

    # 校验依赖关系（目前为基础校验）
    console.print("\n[cyan]Validating task dependencies...[/cyan]")
    validation_result = _validate_tasks_dependencies(tasks_path)
    if validation_result["valid"]:
        console.print("[green]✓[/green] Dependencies are valid")
    else:
        console.print(
            f"[yellow]Warning:[/yellow] {validation_result['message']}",
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
        console.print("\n[green]✓[/green] Updated state to plan stage")

    except Exception as e:
        console.print(
            f"[yellow]Warning:[/yellow] Could not update state: {e}",
            style="yellow",
        )

    # 展示任务概览
    console.print("\n[bold cyan]Task Overview:[/bold cyan]")
    tasks_summary = _parse_tasks_summary(tasks_path)
    if tasks_summary:
        show_task_table(console, tasks_summary, show_wave=True, show_dependencies=True)

    # 展示下一步
    console.print(
        "\n[bold green]Plan generated successfully![/bold green]",
        style="green",
    )
    console.print("\n[bold]Next steps:[/bold]")
    console.print("1. Review and edit tasks.md to refine task breakdown")
    console.print("2. Review and edit design.md for technical decisions")
    console.print("3. Run [cyan]cc-spec apply[/cyan] to execute tasks")

    console.print(
        f"\n[dim]Files created:[/dim]\n"
        f"  - {tasks_path.relative_to(Path.cwd())}\n"
        f"  - {design_path.relative_to(Path.cwd())}"
    )


def _create_basic_tasks_md(
    tasks_path: Path, change_name: str, proposal_content: str
) -> None:
    """当模板不可用时创建基础 tasks.md 结构。"""
    content = f"""# Tasks - {change_name}

> Generated from proposal on {datetime.now().strftime("%Y-%m-%d")}

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟦 空闲 | - |

## 任务详情

### Task: 01-SETUP
**预估上下文**: ~30k tokens
**状态**: 🟦 空闲
**依赖**: 无

**必读文档**:
- .cc-spec/changes/{change_name}/proposal.md
- .cc-spec/changes/{change_name}/design.md

**核心代码入口**:
- (TODO: 根据需求填写)

**Checklist**:
- [ ] 分析需求
- [ ] 设计方案
- [ ] 实现功能
- [ ] 编写测试

**执行日志**:
_(SubAgent 执行时填写)_

---

## 说明

此文件是从模板自动生成的基础结构。请根据实际需求：

1. 添加更多任务到概览表格
2. 为每个任务编写详细的 Checklist
3. 指定必读文档和代码入口
4. 设置任务依赖关系和 Wave 分组
5. 预估每个任务的上下文消耗

## Wave 说明

- Wave 表示任务的执行批次
- 同一 Wave 内的任务可以并发执行
- 不同 Wave 之间按顺序执行
- 任务只能依赖前面 Wave 的任务
"""
    tasks_path.write_text(content, encoding="utf-8")


def _create_basic_design_md(
    design_path: Path, change_name: str, proposal_content: str
) -> None:
    """当模板不可用时创建基础 design.md 结构。"""
    content = f"""# Design - {change_name}

> Technical design and architecture decisions

## 概述

本文档记录了 `{change_name}` 变更的技术设计决策。

## 架构设计

### 模块划分

(TODO: 描述模块结构)

### 数据流

(TODO: 描述数据流向)

### 接口设计

(TODO: 描述 API 接口)

## 技术选型

### 依赖库

(TODO: 列出新增或升级的依赖)

### 技术栈

(TODO: 描述使用的技术)

## 实施方案

### 阶段划分

参考 tasks.md 中的 Wave 划分。

### 风险控制

(TODO: 识别风险点和应对措施)

## 测试策略

### 单元测试

(TODO: 测试范围)

### 集成测试

(TODO: 测试场景)

## 迁移方案

(如果涉及数据迁移或向后兼容)

## 参考资料

- proposal.md - 需求规格
- tasks.md - 任务拆分
"""
    design_path.write_text(content, encoding="utf-8")


def _validate_tasks_dependencies(tasks_path: Path) -> dict:
    """校验 tasks.md 中的任务依赖关系。

    返回：
        包含键：valid（bool）、message（str）、tasks（list）的字典
    """
    try:
        content = tasks_path.read_text(encoding="utf-8")

        # 从概览表解析任务 ID
        import re

        table_pattern = r"\| (\d+) \| ([A-Z0-9-]+) \|.*\| ([^|]+) \|"
        matches = re.findall(table_pattern, content)

        if not matches:
            return {
                "valid": True,
                "message": "No tasks found in overview table",
                "tasks": [],
            }

        task_ids = set()
        dependencies = {}

        for wave, task_id, deps in matches:
            task_ids.add(task_id)
            # 解析依赖（格式："01-TASK, 02-OTHER" 或 "-"）
            deps_clean = deps.strip()
            if deps_clean != "-":
                dep_list = [d.strip() for d in deps_clean.split(",")]
                dependencies[task_id] = dep_list

        # 校验依赖是否存在
        invalid_deps = []
        for task_id, deps in dependencies.items():
            for dep in deps:
                if dep not in task_ids:
                    invalid_deps.append((task_id, dep))

        if invalid_deps:
            dep_str = ", ".join(f"{t} depends on {d}" for t, d in invalid_deps)
            return {
                "valid": False,
                "message": f"Invalid dependencies: {dep_str}",
                "tasks": list(task_ids),
            }

        return {
            "valid": True,
            "message": f"Found {len(task_ids)} tasks, all dependencies valid",
            "tasks": list(task_ids),
        }

    except Exception as e:
        return {"valid": False, "message": f"Error parsing tasks: {e}", "tasks": []}


def _parse_tasks_summary(tasks_path: Path) -> list[dict]:
    """解析 tasks.md，提取用于展示的任务摘要。

    返回：
        任务字典列表，包含键：id、wave、status、estimate、dependencies
    """
    try:
        content = tasks_path.read_text(encoding="utf-8")

        import re

        # 解析概览表
        # 格式：| Wave | Task-ID | 预估 | 状态 | 依赖 |
        table_pattern = r"\| (\d+) \| ([A-Z0-9-]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|"
        matches = re.findall(table_pattern, content)

        tasks = []
        for wave, task_id, estimate, status_icon, deps in matches:
            # 将状态图标映射到状态名称
            status_map = {
                "🟦": "pending",
                "🟨": "in_progress",
                "🟩": "completed",
                "🟥": "failed",
                "⏰": "timeout",
            }

            # 提取状态图标（通常为首字符）
            status = "pending"
            for icon, status_name in status_map.items():
                if icon in status_icon:
                    status = status_name
                    break

            # 解析依赖
            deps_clean = deps.strip()
            dep_list = (
                [d.strip() for d in deps_clean.split(",")]
                if deps_clean != "-"
                else []
            )

            tasks.append(
                {
                    "id": task_id,
                    "wave": int(wave),
                    "status": status,
                    "estimate": estimate.strip(),
                    "dependencies": dep_list,
                }
            )

        return tasks

    except Exception as e:
        console.print(f"[yellow]Warning:[/yellow] Could not parse tasks: {e}")
        return []
