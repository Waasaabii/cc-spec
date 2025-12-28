"""cc-spec 的 accept 命令实现。

端到端验收：执行自动化检查（lint/test/build/type-check），验证功能可用。

"""

from datetime import datetime
from pathlib import Path
from typing import Optional
import subprocess
import sys

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cc_spec.core.config import load_config
from cc_spec.core.id_manager import IDManager
from cc_spec.core.state import (
    Stage,
    StageInfo,
    TaskStatus,
    append_rework_event,
    load_state,
    update_state,
)
from cc_spec.ui.banner import show_banner
from cc_spec.utils.files import find_project_root, get_cc_spec_dir

console = Console()

# 默认检查命令映射
DEFAULT_CHECK_COMMANDS: dict[str, list[str]] = {
    "lint": ["uv", "run", "ruff", "check", "src/"],
    "test": ["uv", "run", "pytest"],
    "build": ["uv", "build"],
    "type-check": ["uv", "run", "mypy", "src/"],
}

# acceptance.md 模板
ACCEPTANCE_TEMPLATE = """# Acceptance Criteria - 验收标准

**变更**: {change_name}

## 功能验收

### 核心路径
- [ ] <核心功能1可正常使用>
- [ ] <核心功能2可正常使用>

### 失败路径
- [ ] <错误场景有合理提示>

## 集成验收

- [ ] 新增文件已被正确 import
- [ ] 功能已集成到入口（UI/CLI/API）
- [ ] 不依赖 mock 可运行

## 自动化检查

- [ ] lint 通过
- [ ] test 通过
- [ ] build 通过
- [ ] type-check 通过
"""


def accept_command(
    change_or_id: Optional[str] = typer.Argument(
        None,
        help="变更名称或 ID（例如 add-oauth 或 C-001）",
    ),
    skip_checks: bool = typer.Option(
        False,
        "--skip-checks",
        help="跳过自动化检查（仅生成 acceptance.md）",
    ),
    write_report: bool = typer.Option(
        True,
        "--write-report/--no-write-report",
        help="是否输出 acceptance-report.md（默认开启）",
    ),
) -> None:
    """端到端验收：执行自动化检查，验证功能可用。

    该命令会：
    1. 检查/创建 acceptance.md（验收标准）
    2. 执行自动化检查（lint/test/build/type-check）
    3. 生成 acceptance-report.md（验收结果）
    4. 通过 → 标记 accept 阶段完成，可继续 archive
    5. 不通过 → 记录 rework 事件，建议回退目标

    示例：
        cc-spec accept              # 验收当前激活的变更
        cc-spec accept add-oauth    # 按名称验收
        cc-spec accept C-001        # 按 ID 验收
        cc-spec accept --skip-checks  # 跳过检查，仅生成 acceptance.md
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

    # 加载配置
    config_path = cc_spec_root / "config.yaml"
    config = None
    check_commands = ["lint", "test", "build", "type-check"]
    if config_path.exists():
        try:
            config = load_config(config_path)
            check_commands = config.acceptance.commands
        except Exception as e:
            console.print(f"[yellow]警告：[/yellow] 无法加载配置：{e}")

    console.print(f"[cyan]正在验收变更：[/cyan] [bold]{change}[/bold]")

    # 检查/创建 acceptance.md
    acceptance_path = change_dir / "acceptance.md"
    if not acceptance_path.exists():
        console.print("[cyan]正在生成 acceptance.md...[/cyan]")
        acceptance_content = ACCEPTANCE_TEMPLATE.format(change_name=change)
        acceptance_path.write_text(acceptance_content, encoding="utf-8")
        console.print(f"[green]√[/green] 已生成：{acceptance_path.relative_to(Path.cwd())}")
    else:
        console.print(f"[dim]使用现有 acceptance.md[/dim]")

    if skip_checks:
        console.print("\n[yellow]跳过自动化检查[/yellow]")
        console.print("请手动验证 acceptance.md 中的验收标准。")
        return

    # 执行自动化检查
    console.print("\n[cyan]正在执行自动化检查...[/cyan]\n")

    check_results: list[dict] = []
    all_passed = True

    for check_name in check_commands:
        cmd = DEFAULT_CHECK_COMMANDS.get(check_name)
        if not cmd:
            console.print(f"[yellow]警告：[/yellow] 未知检查类型：{check_name}")
            continue

        console.print(f"[cyan]运行 {check_name}...[/cyan]")

        try:
            result = subprocess.run(
                cmd,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=300,  # 5 分钟超时
            )
            passed = result.returncode == 0
            check_results.append({
                "name": check_name,
                "passed": passed,
                "returncode": result.returncode,
                "stdout": result.stdout[:2000] if result.stdout else "",
                "stderr": result.stderr[:2000] if result.stderr else "",
            })

            if passed:
                console.print(f"  [green]√ {check_name} 通过[/green]")
            else:
                console.print(f"  [red]× {check_name} 失败[/red]")
                all_passed = False

        except subprocess.TimeoutExpired:
            check_results.append({
                "name": check_name,
                "passed": False,
                "returncode": -1,
                "stdout": "",
                "stderr": "超时（300秒）",
            })
            console.print(f"  [red]× {check_name} 超时[/red]")
            all_passed = False

        except FileNotFoundError:
            check_results.append({
                "name": check_name,
                "passed": False,
                "returncode": -1,
                "stdout": "",
                "stderr": f"命令未找到：{cmd[0]}",
            })
            console.print(f"  [yellow]! {check_name} 跳过（命令未找到）[/yellow]")

    # 展示结果
    console.print()
    _display_results(check_results, all_passed)

    status_path = change_dir / "status.yaml"

    # 生成验收报告
    if write_report:
        report_content = _generate_report(change, check_results, all_passed)
        report_path = change_dir / "acceptance-report.md"
        report_path.write_text(report_content, encoding="utf-8")
        console.print(f"\n[green]√[/green] 已生成：{report_path.relative_to(Path.cwd())}")

    # 处理通过/不通过
    if all_passed:
        _handle_pass(status_path, change_dir, change)
    else:
        _handle_fail(status_path, change_dir, change, check_results)


def _display_results(results: list[dict], all_passed: bool) -> None:
    """展示检查结果。"""
    table = Table(title="自动化检查结果", border_style="cyan")
    table.add_column("检查项", style="white")
    table.add_column("状态", justify="center")
    table.add_column("说明", style="dim")

    for result in results:
        status = "[green]√ 通过[/green]" if result["passed"] else "[red]× 失败[/red]"
        note = ""
        if not result["passed"] and result["stderr"]:
            note = result["stderr"][:50] + "..." if len(result["stderr"]) > 50 else result["stderr"]
        table.add_row(result["name"], status, note)

    console.print(table)

    # 总体结果
    status_color = "green" if all_passed else "red"
    status_text = "√ 验收通过" if all_passed else "× 验收未通过"

    panel = Panel(
        f"[{status_color}]{status_text}[/{status_color}]",
        title="[bold]验收结果[/bold]",
        border_style=status_color,
        padding=(0, 2),
    )
    console.print(panel)


def _generate_report(
    change_name: str,
    results: list[dict],
    all_passed: bool,
) -> str:
    """生成验收报告 Markdown。"""
    timestamp = datetime.now().isoformat()
    status = "通过" if all_passed else "未通过"

    lines = [
        "# Acceptance Report - 验收报告",
        "",
        f"**变更**: {change_name}",
        f"**验收时间**: {timestamp}",
        f"**结果**: {status}",
        "",
        "## 自动化检查",
        "",
        "| 检查项 | 状态 | 返回码 |",
        "|--------|------|--------|",
    ]

    for result in results:
        status_icon = "√" if result["passed"] else "×"
        lines.append(f"| {result['name']} | {status_icon} | {result['returncode']} |")

    lines.extend([
        "",
        "## 详细输出",
        "",
    ])

    for result in results:
        if not result["passed"]:
            lines.extend([
                f"### {result['name']}",
                "",
                "```",
                result["stderr"] or result["stdout"] or "（无输出）",
                "```",
                "",
            ])

    if all_passed:
        lines.extend([
            "## 下一步",
            "",
            "验收通过，可以运行 `cc-spec archive` 归档该变更。",
        ])
    else:
        lines.extend([
            "## 下一步",
            "",
            "验收未通过，请根据上述失败原因进行修复后重新运行 `cc-spec accept`。",
        ])

    return "\n".join(lines)


def _handle_pass(
    status_path: Path,
    change_dir: Path,
    change_name: str,
) -> None:
    """处理验收通过的情况。"""
    console.print("\n[bold green]验收通过！[/bold green]", style="green")

    # 更新状态为 accept 阶段（完成）
    try:
        state = load_state(status_path)

        state.current_stage = Stage.ACCEPT
        state.stages[Stage.ACCEPT] = StageInfo(
            status=TaskStatus.COMPLETED,
            started_at=datetime.now().isoformat(),
            completed_at=datetime.now().isoformat(),
        )

        update_state(status_path, state)
        console.print("[green]√[/green] 已将状态更新为 accept 阶段（完成）")

    except Exception as e:
        console.print(
            f"[yellow]警告：[/yellow] 无法更新状态：{e}",
            style="yellow",
        )

    # 展示下一步
    console.print("\n[bold]下一步：[/bold]")
    console.print("1. 查看验收报告")
    console.print("2. 运行 [cyan]cc-spec archive[/cyan] 归档该变更")

    console.print(f"\n[dim]变更：{change_name}[/dim]")


def _handle_fail(
    status_path: Path,
    change_dir: Path,
    change_name: str,
    results: list[dict],
) -> None:
    """处理验收未通过的情况。"""
    console.print(
        "\n[bold red]验收未通过！[/bold red]",
        style="red",
    )

    # 分析失败原因，建议回退目标
    failed_checks = [r["name"] for r in results if not r["passed"]]

    # 更新状态并记录 rework
    try:
        state = load_state(status_path)

        # 记录 rework 事件
        append_rework_event(
            state,
            from_stage="accept",
            to_stage="apply",
            reason=f"自动化检查失败：{', '.join(failed_checks)}",
        )

        # 回退到 apply 阶段
        state.current_stage = Stage.APPLY
        state.stages[Stage.ACCEPT] = StageInfo(
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
    console.print("\n[bold]失败原因：[/bold]")
    for check in failed_checks:
        console.print(f"  - {check}")

    console.print("\n[bold]建议操作：[/bold]")
    console.print("1. 查看 acceptance-report.md 了解详细错误")
    console.print("2. 修复相关问题")
    console.print("3. 重新运行 [cyan]cc-spec accept[/cyan]")

    console.print(f"\n[dim]变更：{change_name}[/dim]")
    console.print(f"[dim]未通过项：{len(failed_checks)} / {len(results)}[/dim]")
