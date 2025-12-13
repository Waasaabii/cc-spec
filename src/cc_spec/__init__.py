"""cc-spec: 规格驱动的AI辅助开发工作流CLI工具。"""

import typer
from rich.console import Console

from cc_spec.commands import apply as apply_cmd
from cc_spec.commands import archive as archive_cmd
from cc_spec.commands import checklist as checklist_cmd
from cc_spec.commands import clarify as clarify_cmd
from cc_spec.commands import goto as goto_cmd
from cc_spec.commands import init as init_cmd
from cc_spec.commands import list as list_cmd
from cc_spec.commands import plan as plan_cmd
from cc_spec.commands import quick_delta as quick_delta_cmd
from cc_spec.commands import specify as specify_cmd
from cc_spec.commands import update as update_cmd

__version__ = "1.3.0"

app = typer.Typer(
    name="cc-spec",
    help="规格驱动的AI辅助开发工作流CLI工具",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="显示版本信息"),
) -> None:
    """cc-spec: 为AI编码助手设计的规格驱动开发工作流。"""
    if version:
        console.print(f"[bold]cc-spec[/bold] 版本 {__version__}")
        raise typer.Exit()


# 注册命令
app.command(name="init", help="在当前目录初始化cc-spec工作流")(
    init_cmd.init_command
)
app.command(name="specify", help="创建新的变更规格说明")(specify_cmd.specify)
app.command(name="clarify", help="审查任务并标记需要返工的内容")(
    clarify_cmd.clarify
)
app.command(name="plan", help="从提案生成执行计划")(
    plan_cmd.plan_command
)
app.command(name="apply", help="使用SubAgent并行执行任务")(
    apply_cmd.apply_command
)
app.command(name="checklist", help="使用检查清单评分验证任务完成情况")(
    checklist_cmd.checklist_command
)
app.command(name="archive", help="归档已完成的变更")(
    archive_cmd.archive_command
)
app.command(name="quick-delta", help="快速模式：一步创建并归档简单变更")(
    quick_delta_cmd.quick_delta_command
)
app.command(name="list", help="列出变更、任务、规格或归档")(
    list_cmd.list_command
)
app.command(name="goto", help="导航到特定变更或任务")(
    goto_cmd.goto_command
)
app.command(name="update", help="更新配置、命令或模板")(
    update_cmd.update_command
)


def main() -> None:
    """CLI 入口。"""
    app()


if __name__ == "__main__":
    main()
