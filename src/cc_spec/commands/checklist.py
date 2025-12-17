"""cc-spec 的 checklist 命令实现。

基于 checklist 评分验证任务完成情况；若未达到要求阈值，则生成失败报告。

v1.1: 新增通过 ID 指定变更的支持。
v1.3: 新增四维度打分机制 (功能/质量/测试/文档)。
v1.4: 移除 tasks.md 支持，仅使用 tasks.yaml。
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cc_spec.core.config import load_config
from cc_spec.core.id_manager import IDManager
from cc_spec.core.scoring import (
    ChecklistResult,
    calculate_checklist_result,
    calculate_score,
    extract_checklists_from_tasks_yaml,
    format_dimension_report,
    generate_failure_report,
    generate_failure_report_v13,
)
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
from cc_spec.utils.files import find_project_root, get_cc_spec_dir

console = Console()

# 默认通过阈值
DEFAULT_THRESHOLD = 80


def checklist_command(
    change_or_id: Optional[str] = typer.Argument(
        None,
        help="变更名称或 ID（例如 add-oauth 或 C-001）",
    ),
    threshold: int = typer.Option(
        DEFAULT_THRESHOLD,
        "--threshold",
        "-t",
        help="通过所需的最低百分比（0-100）",
        min=0,
        max=100,
    ),
    use_v13: bool = typer.Option(
        True,
        "--v13/--no-v13",
        help="使用 v1.3 四维度打分（默认开启）",
    ),
    write_report: bool = typer.Option(
        False,
        "--write-report",
        help="输出 checklist-result.md（默认关闭：结果写入 KB records）",
    ),
) -> None:
    """使用 checklist 评分验证任务完成情况。

    v1.1：现支持通过变更 ID（例如 C-001）。
    v1.3：支持四维度打分机制 (功能完整性/代码质量/测试覆盖/文档同步)。

    该命令会：
    1. 读取 tasks.yaml 并提取所有 checklist 项
    2. 根据完成项计算得分 (v1.3 支持四维度加权)
    3. 若得分 >= threshold：将阶段标记为完成，可继续 archive
    4. 若得分 < threshold：生成失败报告并回退到 apply 阶段

    示例：
        cc-spec checklist              # 检查当前激活的变更
        cc-spec checklist add-oauth    # 按名称检查
        cc-spec checklist C-001        # 按 ID 检查
        cc-spec checklist C-001 -t 90  # 自定义阈值
        cc-spec checklist --no-v13     # 使用旧版简单打分
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

    # 检查 tasks.yaml 是否存在
    tasks_path = change_dir / "tasks.yaml"
    if not tasks_path.exists():
        console.print(
            f"[red]错误：[/red] 在 {change_dir} 中未找到 tasks.yaml。"
            "请先运行 'cc-spec plan'。",
            style="red",
        )
        raise typer.Exit(1)

    console.print(f"[cyan]正在验收检查清单：[/cyan] [bold]{change}[/bold]")
    console.print(f"[dim]阈值：{threshold}%[/dim]")
    if use_v13:
        console.print("[dim]模式：v1.3 四维度打分[/dim]\n")
    else:
        console.print("[dim]模式：简单打分[/dim]\n")

    # 读取 tasks.yaml 并提取 checklist
    console.print("[cyan]正在读取 tasks.yaml...[/cyan]")
    tasks_content = tasks_path.read_text(encoding="utf-8")

    # 从 tasks.yaml 中提取所有 checklist
    task_checklists = extract_checklists_from_tasks_yaml(tasks_content)

    if not task_checklists:
        console.print(
            "[yellow]警告：[/yellow] tasks.yaml 中未找到检查清单项",
            style="yellow",
        )
        console.print("请先在 tasks.yaml 中补充检查清单项后再进行验收。\n")
        raise typer.Exit(1)

    console.print(
        f"[green]√[/green] 共找到 {len(task_checklists)} 个带检查清单的任务\n"
    )

    # 加载配置获取打分设置
    scoring_config = None
    config_path = cc_spec_root / "config.yaml"
    if config_path.exists():
        try:
            config = load_config(config_path)
            scoring_config = config.scoring
            # 使用配置中的阈值 (如果命令行未指定)
            if threshold == DEFAULT_THRESHOLD:
                threshold = config.get_pass_threshold()
        except Exception as e:
            console.print(f"[yellow]警告：[/yellow] 无法加载配置：{e}")

    status_path = change_dir / "status.yaml"

    if use_v13:
        # v1.3: 四维度打分
        checklist_result = calculate_checklist_result(
            task_checklists,
            scoring_config=scoring_config,
            threshold=threshold,
        )

        # 展示四维度结果
        _display_v13_results(checklist_result, threshold)

        # 处理通过/未通过
        if checklist_result.overall_passed:
            try_write_record(
                project_root,
                step=WorkflowStep.CHECKLIST,
                change_name=change,
                outputs={
                    "overall_score": checklist_result.overall_score,
                    "overall_passed": checklist_result.overall_passed,
                    "threshold": checklist_result.threshold,
                    "failed_tasks": checklist_result.failed_tasks,
                    "recommendations": checklist_result.recommendations[:20],
                    "write_report": write_report,
                    "report_md": format_dimension_report(checklist_result)[:8000],
                },
                notes="checklist.scored",
            )
            _handle_pass_v13(status_path, change_dir, change, checklist_result, write_report=write_report)
        else:
            try_write_record(
                project_root,
                step=WorkflowStep.CHECKLIST,
                change_name=change,
                outputs={
                    "overall_score": checklist_result.overall_score,
                    "overall_passed": checklist_result.overall_passed,
                    "threshold": checklist_result.threshold,
                    "failed_tasks": checklist_result.failed_tasks,
                    "recommendations": checklist_result.recommendations[:20],
                    "write_report": write_report,
                    "report_md": format_dimension_report(checklist_result)[:8000],
                },
                notes="checklist.scored",
            )
            _handle_fail_v13(
                status_path, change_dir, change, checklist_result, threshold, write_report=write_report
            )
    else:
        # v1.2 兼容: 简单打分
        all_results = []
        task_scores = []

        for task_id, items in task_checklists.items():
            result = calculate_score(items, threshold=threshold)
            all_results.append((task_id, result))
            task_scores.append(result)

        # 计算总体得分
        total_score_sum = sum(r.total_score for r in task_scores)
        max_score_sum = sum(r.max_score for r in task_scores)
        overall_percentage = (
            (total_score_sum / max_score_sum * 100) if max_score_sum > 0 else 0.0
        )
        overall_passed = overall_percentage >= threshold

        # 按任务展示结果
        _display_task_results(all_results, threshold)

        # 展示总体结果
        console.print()
        _display_overall_result(
            total_score_sum, max_score_sum, overall_percentage, threshold, overall_passed
        )

        # 处理通过/未通过
        if overall_passed:
            try_write_record(
                project_root,
                step=WorkflowStep.CHECKLIST,
                change_name=change,
                outputs={
                    "overall_score": overall_percentage,
                    "overall_passed": overall_passed,
                    "threshold": threshold,
                    "write_report": write_report,
                },
                notes="checklist.scored",
            )
            _handle_pass(status_path, change_dir, change, overall_percentage, write_report=write_report)
        else:
            try_write_record(
                project_root,
                step=WorkflowStep.CHECKLIST,
                change_name=change,
                outputs={
                    "overall_score": overall_percentage,
                    "overall_passed": overall_passed,
                    "threshold": threshold,
                    "failed_tasks": [task_id for task_id, result in all_results if not result.passed],
                    "write_report": write_report,
                },
                notes="checklist.scored",
            )
            _handle_fail(status_path, change_dir, change, all_results, threshold, write_report=write_report)


def _display_task_results(
    results: list[tuple[str, any]], threshold: int
) -> None:
    """展示每个任务的 checklist 验证结果。

    参数：
        results：(task_id, ScoreResult) 列表
        threshold：通过阈值百分比
    """
    console.print("[bold cyan]任务检查清单结果：[/bold cyan]\n")

    for task_id, result in results:
        # 确定状态颜色
        status_color = "green" if result.passed else "red"
        status_text = "通过" if result.passed else "未通过"

        # 创建任务面板
        content_lines = []
        content_lines.append(
            f"[cyan]得分：[/cyan] {result.total_score}/{result.max_score} "
            f"({result.percentage:.1f}%)"
        )
        content_lines.append(
            f"[cyan]状态：[/cyan] [{status_color}]{status_text}[/{status_color}]"
        )

        # 如有失败项则展示
        if result.failed_items:
            content_lines.append(
                f"\n[yellow]未通过项（{len(result.failed_items)}）：[/yellow]"
            )
            for item in result.failed_items[:3]:  # 仅显示前 3 项
                content_lines.append(f"  - {item.description}")
            if len(result.failed_items) > 3:
                content_lines.append(
                    f"  [dim]... 还有 {len(result.failed_items) - 3} 项[/dim]"
                )

        panel = Panel(
            "\n".join(content_lines),
            title=f"[bold]{task_id}[/bold]",
            border_style=status_color,
            padding=(0, 2),
        )
        console.print(panel)


def _display_overall_result(
    total_score: int,
    max_score: int,
    percentage: float,
    threshold: int,
    passed: bool,
) -> None:
    """展示整体验证结果。

    参数：
        total_score：已获得的总分
        max_score：可获得的总分
        percentage：总体百分比得分
        threshold：通过阈值
        passed：是否通过验证
    """
    status_color = "green" if passed else "red"
    status_icon = "√" if passed else "×"
    status_text = "通过" if passed else "未通过"

    content_lines = [
        f"[cyan]总分：[/cyan] [bold]{total_score}/{max_score}[/bold]",
        f"[cyan]百分比：[/cyan] [bold]{percentage:.1f}%[/bold]",
        f"[cyan]阈值：[/cyan] {threshold}%",
        "",
        f"[{status_color}]状态：[/{status_color}] "
        f"[bold {status_color}]{status_icon} {status_text}[/bold {status_color}]",
    ]

    panel = Panel(
        "\n".join(content_lines),
        title="[bold]总体验收结果[/bold]",
        border_style=status_color,
        padding=(1, 2),
    )
    console.print(panel)


def _handle_pass(
    status_path: Path,
    change_dir: Path,
    change_name: str,
    percentage: float,
    *,
    write_report: bool = False,
) -> None:
    """处理 checklist 验证通过的情况。

    参数：
        status_path：status.yaml 路径
        change_dir：变更目录路径
        change_name：变更名称
        percentage：验证得分百分比
    """
    console.print("\n[bold green]验收通过！[/bold green]", style="green")

    # 更新状态为 checklist 阶段（完成）
    try:
        state = load_state(status_path)

        # 将阶段更新为 checklist 已完成
        state.current_stage = Stage.CHECKLIST
        state.stages[Stage.CHECKLIST] = StageInfo(
            status=TaskStatus.COMPLETED,
            started_at=datetime.now().isoformat(),
            completed_at=datetime.now().isoformat(),
        )

        update_state(status_path, state)
        console.print("[green]√[/green] 已将状态更新为 checklist 阶段（完成）")

    except Exception as e:
        console.print(
            f"[yellow]警告：[/yellow] 无法更新状态：{e}",
            style="yellow",
        )

    # 展示下一步
    console.print("\n[bold]下一步：[/bold]")
    console.print("1. 查看验收结果")
    console.print("2. 运行 [cyan]cc-spec archive[/cyan] 归档该变更")

    console.print(f"\n[dim]变更：{change_name}[/dim]")
    console.print(f"[dim]验收得分：{percentage:.1f}%[/dim]")


def _handle_fail(
    status_path: Path,
    change_dir: Path,
    change_name: str,
    results: list[tuple[str, any]],
    threshold: int,
    *,
    write_report: bool = False,
) -> None:
    """处理 checklist 验证未通过的情况。

    参数：
        status_path：status.yaml 路径
        change_dir：变更目录路径
        change_name：变更名称
        results：(task_id, ScoreResult) 列表
        threshold：通过阈值百分比
    """
    console.print(
        "\n[bold red]验收未通过！[/bold red]",
        style="red",
    )

    # 生成失败报告
    # 将所有结果合并为一个整体结果用于生成报告
    all_failed_items = []
    total_score = 0
    max_score = 0

    for task_id, result in results:
        for item in result.failed_items:
            # 为描述添加任务上下文
            item.description = f"[{task_id}] {item.description}"
            all_failed_items.append(item)
        total_score += result.total_score
        max_score += result.max_score

    percentage = (total_score / max_score * 100) if max_score > 0 else 0.0

    # 创建用于生成报告的合并结果
    from cc_spec.core.scoring import ScoreResult

    combined_result = ScoreResult(
        items=[],  # 报告中不使用
        total_score=total_score,
        max_score=max_score,
        percentage=percentage,
        passed=False,
        threshold=threshold,
        failed_items=all_failed_items,
    )

    report_content = generate_failure_report(combined_result)
    if write_report:
        report_path = change_dir / "checklist-result.md"
        report_path.write_text(report_content, encoding="utf-8")
        console.print(
            f"[green]√[/green] 已生成失败报告：{report_path.relative_to(Path.cwd())}"
        )
    else:
        console.print("[dim]失败报告已写入 KB records（如需文件输出使用 --write-report）[/dim]")

    # 将状态更新回 apply 阶段
    try:
        state = load_state(status_path)

        # 回退到 apply 阶段（标记为需要返工）
        state.current_stage = Stage.APPLY
        state.stages[Stage.CHECKLIST] = StageInfo(
            status=TaskStatus.FAILED,
            started_at=datetime.now().isoformat(),
            completed_at=datetime.now().isoformat(),
        )

        update_state(status_path, state)
        console.print("[yellow]![/yellow] 已将状态回退到 apply 阶段（需要返工）")

    except Exception as e:
        console.print(
            f"[yellow]警告：[/yellow] 无法更新状态：{e}",
            style="yellow",
        )

    # 展示下一步
    console.print("\n[bold]下一步：[/bold]")
    console.print("1. 查看失败原因（KB records 或 --write-report 输出文件）")
    console.print("2. 完成未通过的检查清单项")
    console.print("3. 运行 [cyan]cc-spec clarify <task-id>[/cyan] 标记指定任务返工")
    console.print("4. 修复后重新运行 [cyan]cc-spec checklist[/cyan] 进行验收")

    console.print(f"\n[dim]变更：{change_name}[/dim]")
    console.print(
        f"[dim]未通过项：{len(all_failed_items)} / {len([item for _, result in results for item in result.items])}[/dim]"
    )


# ============================================================================
# v1.3 新增: 四维度打分相关函数
# ============================================================================

def _display_v13_results(result: ChecklistResult, threshold: int) -> None:
    """展示 v1.3 四维度打分结果。

    参数：
        result: ChecklistResult 打分结果
        threshold: 通过阈值百分比
    """
    from cc_spec.core.config import Dimension

    console.print("[bold cyan]四维度打分结果:[/bold cyan]\n")

    # 创建任务得分表格
    table = Table(title="任务得分", border_style="cyan")
    table.add_column("任务 ID", style="white")
    table.add_column("总分", justify="center")
    table.add_column("功能", justify="center")
    table.add_column("质量", justify="center")
    table.add_column("测试", justify="center")
    table.add_column("文档", justify="center")
    table.add_column("状态", justify="center")

    for task_score in result.task_scores:
        func = task_score.dimension_scores.get(Dimension.FUNCTIONALITY)
        qual = task_score.dimension_scores.get(Dimension.CODE_QUALITY)
        test = task_score.dimension_scores.get(Dimension.TEST_COVERAGE)
        doc = task_score.dimension_scores.get(Dimension.DOCUMENTATION)

        func_str = f"{func.percentage:.0f}%" if func and func.max_score > 0 else "-"
        qual_str = f"{qual.percentage:.0f}%" if qual and qual.max_score > 0 else "-"
        test_str = f"{test.percentage:.0f}%" if test and test.max_score > 0 else "-"
        doc_str = f"{doc.percentage:.0f}%" if doc and doc.max_score > 0 else "-"

        status = "[green]√ 通过[/green]" if task_score.passed else "[red]× 未通过[/red]"

        table.add_row(
            task_score.task_id,
            f"{task_score.total_score:.0f}%",
            func_str,
            qual_str,
            test_str,
            doc_str,
            status,
        )

    console.print(table)

    # 展示维度汇总
    console.print("\n[bold cyan]维度汇总:[/bold cyan]\n")

    dim_names = {
        Dimension.FUNCTIONALITY: "功能完整性",
        Dimension.CODE_QUALITY: "代码质量",
        Dimension.TEST_COVERAGE: "测试覆盖",
        Dimension.DOCUMENTATION: "文档同步",
    }

    for dim in Dimension:
        summary = result.dimension_summary.get(dim)
        if summary and summary.max_score > 0:
            name = dim_names.get(dim, dim.value)
            status = "[green]√[/green]" if summary.percentage >= threshold else "[red]×[/red]"
            console.print(
                f"  {status} {name}: {summary.percentage:.1f}% (权重: {summary.weight}%)"
            )

    # 展示整体结果
    console.print()
    status_color = "green" if result.overall_passed else "red"
    status_text = "√ 通过" if result.overall_passed else "× 未通过"

    panel = Panel(
        f"[cyan]整体得分:[/cyan] [bold]{result.overall_score:.1f}%[/bold]\n"
        f"[cyan]阈值:[/cyan] {threshold}%\n"
        f"[{status_color}]状态:[/{status_color}] [bold {status_color}]{status_text}[/bold {status_color}]",
        title="[bold]整体验证结果[/bold]",
        border_style=status_color,
        padding=(1, 2),
    )
    console.print(panel)

    # 展示改进建议
    if result.recommendations:
        console.print("\n[bold yellow]改进建议:[/bold yellow]")
        for rec in result.recommendations:
            console.print(f"  - {rec}")


def _handle_pass_v13(
    status_path: Path,
    change_dir: Path,
    change_name: str,
    result: ChecklistResult,
    *,
    write_report: bool = False,
) -> None:
    """处理 v1.3 checklist 验证通过的情况。

    参数：
        status_path: status.yaml 路径
        change_dir: 变更目录路径
        change_name: 变更名称
        result: ChecklistResult 打分结果
    """
    console.print("\n[bold green]验证通过！[/bold green]", style="green")

    # 打分报告：默认写入 KB records；如需文件输出使用 --write-report
    report_content = format_dimension_report(result)
    if write_report:
        report_path = change_dir / "checklist-result.md"
        report_path.write_text(report_content, encoding="utf-8")
        console.print(
            f"[green]√[/green] 生成打分报告: {report_path.relative_to(Path.cwd())}"
        )
    else:
        console.print("[dim]打分报告已写入 KB records（如需文件输出使用 --write-report）[/dim]")

    # 更新状态为 checklist 阶段（完成）
    try:
        state = load_state(status_path)

        state.current_stage = Stage.CHECKLIST
        state.stages[Stage.CHECKLIST] = StageInfo(
            status=TaskStatus.COMPLETED,
            started_at=datetime.now().isoformat(),
            completed_at=datetime.now().isoformat(),
        )

        update_state(status_path, state)
        console.print("[green]√[/green] 状态已更新到 checklist 阶段（完成）")

    except Exception as e:
        console.print(
            f"[yellow]警告：[/yellow] 无法更新状态：{e}",
            style="yellow",
        )

    # 展示下一步
    console.print("\n[bold]下一步:[/bold]")
    console.print("1. 查看打分结果（KB records 或 --write-report 输出文件）")
    console.print("2. 运行 [cyan]cc-spec archive[/cyan] 归档该变更")

    console.print(f"\n[dim]变更：{change_name}[/dim]")
    console.print(f"[dim]验证得分: {result.overall_score:.1f}%[/dim]")


def _handle_fail_v13(
    status_path: Path,
    change_dir: Path,
    change_name: str,
    result: ChecklistResult,
    threshold: int,
    *,
    write_report: bool = False,
) -> None:
    """处理 v1.3 checklist 验证未通过的情况。

    参数：
        status_path: status.yaml 路径
        change_dir: 变更目录路径
        change_name: 变更名称
        result: ChecklistResult 打分结果
        threshold: 通过阈值百分比
    """
    console.print(
        "\n[bold red]验证未通过！[/bold red]",
        style="red",
    )

    # 生成增强版失败报告
    report_content = generate_failure_report_v13(result)

    if write_report:
        report_path = change_dir / "checklist-result.md"
        report_path.write_text(report_content, encoding="utf-8")
        console.print(
            f"[green]√[/green] 生成失败报告: {report_path.relative_to(Path.cwd())}"
        )
    else:
        console.print("[dim]失败报告已写入 KB records（如需文件输出使用 --write-report）[/dim]")

    # 将状态更新回 apply 阶段
    try:
        state = load_state(status_path)

        state.current_stage = Stage.APPLY
        state.stages[Stage.CHECKLIST] = StageInfo(
            status=TaskStatus.FAILED,
            started_at=datetime.now().isoformat(),
            completed_at=datetime.now().isoformat(),
        )

        update_state(status_path, state)
        console.print("[yellow]![/yellow] 状态已回退到 apply 阶段（需要返工）")

    except Exception as e:
        console.print(
            f"[yellow]警告：[/yellow] 无法更新状态：{e}",
            style="yellow",
        )

    # 展示下一步
    console.print("\n[bold]下一步:[/bold]")
    console.print("1. 查看失败原因（KB records 或 --write-report 输出文件）")
    console.print("2. 完成未通过的检查项")
    console.print("3. 运行 [cyan]cc-spec clarify <task-id>[/cyan] 标记任务返工")
    console.print("4. 修复后重新运行 [cyan]cc-spec checklist[/cyan]")

    console.print(f"\n[dim]变更：{change_name}[/dim]")
    console.print(f"[dim]未通过任务: {len(result.failed_tasks)}[/dim]")
