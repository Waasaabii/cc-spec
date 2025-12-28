"""cc-spec: 规格驱动的AI辅助开发工作流CLI工具。"""

import sys

import typer
from rich.console import Console

from cc_spec.commands import accept as accept_cmd
from cc_spec.commands import apply as apply_cmd
from cc_spec.commands import archive as archive_cmd
from cc_spec.commands import chat as chat_cmd
from cc_spec.commands import clarify as clarify_cmd
from cc_spec.commands import context as context_cmd
from cc_spec.commands import cx as cx_cmd
from cc_spec.commands import goto as goto_cmd
from cc_spec.commands import init as init_cmd
from cc_spec.commands import index as index_cmd
from cc_spec.commands import list as list_cmd
from cc_spec.commands import plan as plan_cmd
from cc_spec.commands import quick_delta as quick_delta_cmd
from cc_spec.commands import specify as specify_cmd
from cc_spec.commands import update as update_cmd
from cc_spec.ui.banner import show_banner
from cc_spec.version import (
    CONFIG_VERSION,
    PACKAGE_VERSION,
    TEMPLATE_VERSION,
)

__version__ = PACKAGE_VERSION

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
        show_banner(console)
        console.print(f"[bold]cc-spec[/bold] 版本 {__version__}")
        console.print(f"template {TEMPLATE_VERSION} | config {CONFIG_VERSION}")
        raise typer.Exit()
    # 如果没有子命令且不是帮助请求，显示 banner
    if ctx.invoked_subcommand is None and "--help" not in sys.argv and "-h" not in sys.argv:
        show_banner(console)


# 注册命令
app.command(name="init", help="在当前目录初始化cc-spec工作流")(init_cmd.init_command)
app.command(name="init-index", help="初始化项目多级索引（PROJECT_INDEX/FOLDER_INDEX）")(
    index_cmd.init_index_command
)
app.command(name="update-index", help="增量更新项目多级索引（可用于 hook 自动触发）")(
    index_cmd.update_index_command
)
app.command(name="check-index", help="检查项目多级索引是否齐全/一致")(
    index_cmd.check_index_command
)
app.command(name="specify", help="创建新的变更规格说明")(specify_cmd.specify)
app.command(name="clarify", help="审查任务并标记需要返工的内容")(clarify_cmd.clarify)
app.command(name="plan", help="从提案生成执行计划")(plan_cmd.plan_command)
app.command(name="apply", help="使用SubAgent并行执行任务")(apply_cmd.apply_command)
app.command(name="accept", help="端到端验收：执行自动化检查，验证功能可用")(
    accept_cmd.accept_command
)
app.command(name="archive", help="归档已完成的变更")(archive_cmd.archive_command)
app.command(name="quick-delta", help="快速模式：一步创建并归档简单变更")(
    quick_delta_cmd.quick_delta_command
)
app.command(name="list", help="列出变更、任务、规格或归档")(list_cmd.list_command)
app.command(name="goto", help="导航到特定变更或任务")(goto_cmd.goto_command)
app.command(name="update", help="更新配置、命令或模板")(update_cmd.update_command)
app.command(name="chat", help="与Codex进行多轮交互式对话")(chat_cmd.chat_command)
app.command(name="context", help="输出当前阶段上下文信息")(context_cmd.context_command)

# cx 命令：通过 tool 调用 Codex（子命令组）
app.add_typer(cx_cmd.app, name="cx", help="通过cc-spec-tool调用Codex")


def main() -> None:
    """CLI 入口。"""
    app()


if __name__ == "__main__":
    main()
