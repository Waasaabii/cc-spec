"""cc-spec 终端启动 Banner 显示。"""

import sys
from pathlib import Path

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from cc_spec.version import UI_VERSION_INFO

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

# 喵娘装饰（基于 wu.jpg：粉发紫眼、蝴蝶结、圣诞帽、绿外套）
MASCOT_LINES = [
    "    ∧ ∧    ",
    "  (ᵒ̴̶̷ᴗᵒ̴̶̷)   ",
    "  /|♡ |\\  ",
    "  ╰───╯   ",
]

# Windows/GBK 等编码环境兼容：提供纯 ASCII 吉祥物，避免 UnicodeEncodeError
SAFE_MASCOT_LINES = [
    "    /\\_/\\    ",
    "   ( o_o )   ",
    "    > ^ <    ",
]

# 兼容旧代码
MASCOT = "\n".join(MASCOT_LINES)

TAGLINE = "规范驱动的 AI 辅助开发工作流 CLI 喵～"
VERSION_INFO = UI_VERSION_INFO


def _console_encoding(console: Console) -> str | None:
    try:
        encoding = getattr(console.file, "encoding", None)
        return str(encoding) if encoding else None
    except Exception:
        return None


def _can_encode(text: str, encoding: str | None) -> bool:
    if not encoding:
        return True
    try:
        text.encode(encoding)
        return True
    except Exception:
        return False


def _use_safe_unicode(console: Console) -> bool:
    """判断是否需要使用 ASCII 安全输出。

    在 Windows 传统终端（如 GBK）下，部分字符（emoji/组合字符）会触发 UnicodeEncodeError。
    """
    encoding = _console_encoding(console) or sys.stdout.encoding
    sample = "".join(MASCOT_LINES) + "✅❌✨💦ฅω"
    return not _can_encode(sample, encoding)


def show_banner(console: Console | None = None) -> None:
    """显示 cc-spec 启动 Banner。

    参数：
        console: Rich Console 实例，如果为 None 则创建新实例
    """
    if console is None:
        console = Console()

    # Banner 颜色渐变（粉色系，呼应喵娘的粉发）
    colors = ["bright_magenta", "magenta", "bright_cyan", "cyan", "bright_white", "white"]

    # 组合显示
    console.print()
    # 直接打印 banner（使用 BANNER_LINES 保留精确格式）
    for i, line in enumerate(BANNER_LINES):
        color = colors[i % len(colors)]
        console.print(f"[{color}]{line}[/{color}]")
    console.print()
    # 直接打印 mascot（使用 MASCOT_LINES 保留精确格式）
    mascot_lines = SAFE_MASCOT_LINES if _use_safe_unicode(console) else MASCOT_LINES
    for line in mascot_lines:
        console.print(f"[bright_magenta]{line}[/bright_magenta]")
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
        title=(
            "[bold magenta]cc-spec ready[/bold magenta]"
            if _use_safe_unicode(console)
            else "[bold magenta]ฅ'ω'ฅ 喵娘工程师准备就绪[/bold magenta]"
        ),
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

    if _use_safe_unicode(console):
        success_cat = r"""
 /\_/\ 
( ^_^ )
 /   \
"""
        message_text = f"OK: {message}"
    else:
        success_cat = r"""
    ∧＿∧
   (≧▽≦)  ✨
   /  つ
  しーＪ
"""
        message_text = f"✅ {message} 喵～"

    console.print()
    console.print(Align.center(Text(success_cat, style="bright_green")))
    console.print(Align.center(Text(message_text, style="bold green")))
    console.print()


def show_error_banner(console: Console | None = None, message: str = "发生错误") -> None:
    """显示错误 Banner。

    参数：
        console: Rich Console 实例
        message: 错误消息
    """
    if console is None:
        console = Console()

    if _use_safe_unicode(console):
        error_cat = r"""
 /\_/\ 
( >_< )
 /   \
"""
        message_text = f"ERROR: {message}"
    else:
        error_cat = r"""
    ∧＿∧
   (；ω；)  💦
   /  つ
  しーＪ
"""
        message_text = f"❌ {message} 喵..."

    console.print()
    console.print(Align.center(Text(error_cat, style="bright_red")))
    console.print(Align.center(Text(message_text, style="bold red")))
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
