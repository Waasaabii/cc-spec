"""cc-spec 终端启动 Banner 显示。"""

from pathlib import Path

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# CC-SPEC ASCII Art Banner (列表形式保留精确格式)
BANNER_LINES = [
    " ██████╗ ██████╗       ███████╗██████╗ ███████╗ ██████╗",
    "██╔════╝██╔════╝       ██╔════╝██╔══██╗██╔════╝██╔════╝",
    "██║     ██║     █████╗ ███████╗██████╔╝█████╗  ██║     ",
    "██║     ██║     ╚════╝ ╚════██║██╔═══╝ ██╔══╝  ██║     ",
    "╚██████╗╚██████╗       ███████║██║     ███████╗╚██████╗",
    " ╚═════╝ ╚═════╝       ╚══════╝╚═╝     ╚══════╝ ╚═════╝",
]

# 兼容旧代码
BANNER = "\n".join(BANNER_LINES)

# 喵娘装饰
MASCOT = """
  ∧＿∧
 (｡･ω･｡)
 |  つ♡
 しーＪ
"""

TAGLINE = "规范驱动的 AI 辅助开发工作流 CLI 喵～"
VERSION_INFO = "v0.1.4 - 四源融合 + 单一真相源"


def show_banner(console: Console | None = None) -> None:
    """显示 cc-spec 启动 Banner。

    参数：
        console: Rich Console 实例，如果为 None 则创建新实例
    """
    if console is None:
        console = Console()

    # Banner 颜色渐变（粉色系，呼应喵娘的粉发）
    colors = ["bright_magenta", "magenta", "bright_cyan", "cyan", "bright_white", "white"]

    # 吉祥物颜色（紫色眼睛风格）
    mascot_text = Text(MASCOT.strip(), style="bright_magenta")

    # 组合显示
    console.print()
    # 直接打印 banner（使用 BANNER_LINES 保留精确格式）
    for i, line in enumerate(BANNER_LINES):
        color = colors[i % len(colors)]
        console.print(f"[{color}]{line}[/{color}]")
    console.print()
    console.print(Align.center(mascot_text))
    console.print(Align.center(Text(TAGLINE, style="italic bright_yellow")))
    console.print(Align.center(Text(VERSION_INFO, style="dim")))
    console.print()


def show_welcome_panel(console: Console | None = None, project_name: str = "") -> None:
    """显示欢迎面板。

    参数：
        console: Rich Console 实例
        project_name: 项目名称
    """
    if console is None:
        console = Console()

    welcome_lines = [
        "[cyan]欢迎使用 cc-spec 喵～[/cyan]",
        "",
        f"[green]项目:[/green] {project_name}" if project_name else "",
        "",
        "[dim]使用 [cyan]cc-spec --help[/cyan] 查看可用命令[/dim]",
    ]

    # 过滤空行
    welcome_lines = [line for line in welcome_lines if line or line == ""]

    panel = Panel(
        "\n".join(welcome_lines),
        title="[bold magenta]ฅ'ω'ฅ 喵娘工程师准备就绪[/bold magenta]",
        border_style="magenta",
        padding=(1, 2),
    )

    console.print(panel)


def show_success_banner(console: Console | None = None, message: str = "操作完成") -> None:
    """显示成功 Banner。

    参数：
        console: Rich Console 实例
        message: 成功消息
    """
    if console is None:
        console = Console()

    success_cat = r"""
    ∧＿∧
   (≧▽≦)  ✨
   /  つ
  しーＪ
"""

    console.print()
    console.print(Align.center(Text(success_cat, style="bright_green")))
    console.print(Align.center(Text(f"✅ {message} 喵～", style="bold green")))
    console.print()


def show_error_banner(console: Console | None = None, message: str = "发生错误") -> None:
    """显示错误 Banner。

    参数：
        console: Rich Console 实例
        message: 错误消息
    """
    if console is None:
        console = Console()

    error_cat = r"""
    ∧＿∧
   (；ω；)  💦
   /  つ
  しーＪ
"""

    console.print()
    console.print(Align.center(Text(error_cat, style="bright_red")))
    console.print(Align.center(Text(f"❌ {message} 喵...", style="bold red")))
    console.print()


# 导出公共函数
__all__ = [
    "show_banner",
    "show_welcome_panel",
    "show_success_banner",
    "show_error_banner",
    "BANNER",
    "BANNER_LINES",
    "MASCOT",
    "TAGLINE",
]
