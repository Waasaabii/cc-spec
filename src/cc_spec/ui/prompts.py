"""终端 UI 的交互提示组件。"""

from __future__ import annotations

from typing import Any

import readchar
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table


def confirm_action(
    console: Console,
    message: str,
    default: bool = False,
    warning: bool = False,
) -> bool:
    """提示用户确认一个操作。

    参数：
        console: Rich 控制台实例
        message: 要展示的确认提示消息
        default: 默认选择（True=是，False=否）
        warning: 是否以警告样式展示（危险操作）

    返回：
        用户确认则返回 True，否则返回 False
    """
    # 根据 warning 标志选择样式
    if warning:
        style = "yellow"
        border_style = "yellow"
        prefix = "[bold yellow]警告[/bold yellow]"
    else:
        style = "cyan"
        border_style = "cyan"
        prefix = "[bold cyan]确认[/bold cyan]"

    # 构建提示文本
    default_hint = "[Y/n]" if default else "[y/N]"
    prompt_text = f"{prefix}\n\n{message}\n\n[dim]继续？ {default_hint}[/dim]"

    panel = Panel(
        prompt_text,
        border_style=border_style,
        padding=(1, 2),
    )

    console.print(panel)

    # 获取用户输入
    while True:
        try:
            key = readchar.readkey()

            # 处理常见按键
            if key.lower() == "y":
                console.print("[green]√ 已确认[/green]")
                return True
            elif key.lower() == "n":
                console.print("[yellow]× 已取消[/yellow]")
                return False
            elif key in (readchar.key.ENTER, "\r", "\n"):
                if default:
                    console.print("[green]√ 已确认（默认）[/green]")
                else:
                    console.print("[yellow]× 已取消（默认）[/yellow]")
                return default
            elif key in (readchar.key.ESC, readchar.key.CTRL_C):
                console.print("[yellow]× 已取消[/yellow]")
                return False

        except KeyboardInterrupt:
            console.print("[yellow]× 已取消[/yellow]")
            return False


def select_option(
    console: Console,
    options: dict[str, str] | list[str],
    prompt_text: str = "请选择一个选项",
    default: str | None = None,
    multi_select: bool = False,
) -> str | list[str]:
    """使用方向键进行交互式选项选择。

    参数：
        console: Rich 控制台实例
        options: 可选项（dict：key->description 或字符串列表）
        prompt_text: 显示在选项上方的提示文本
        default: 默认选项 key/value
        multi_select: 是否允许多选

    返回：
        选中的选项 key（若 multi_select=True 则返回 key 列表）
    """
    # 将 options 统一成 dict
    if isinstance(options, list):
        options_dict = {opt: opt for opt in options}
    else:
        options_dict = options

    option_keys = list(options_dict.keys())

    # 查找默认选项索引
    if default and default in option_keys:
        selected_index = option_keys.index(default)
    else:
        selected_index = 0

    # 多选模式下跟踪已选项
    selected_items: set[str] = set()

    def create_selection_panel() -> Panel:
        """创建选择面板并高亮当前选中项。"""
        table = Table.grid(padding=(0, 2))
        table.add_column(style="cyan", justify="left", width=3)
        if multi_select:
            table.add_column(style="cyan", justify="left", width=3)
        table.add_column(style="white", justify="left")

        for i, key in enumerate(option_keys):
            # 光标指示
            cursor = ">" if i == selected_index else " "

            # 多选复选框
            if multi_select:
                checkbox = "[x]" if key in selected_items else "[ ]"
                if i == selected_index:
                    row_text = f"[cyan]{key}[/cyan] [dim]({options_dict[key]})[/dim]"
                else:
                    row_text = f"{key} [dim]({options_dict[key]})[/dim]"
                table.add_row(cursor, checkbox, row_text)
            else:
                if i == selected_index:
                    row_text = f"[cyan]{key}[/cyan] [dim]({options_dict[key]})[/dim]"
                else:
                    row_text = f"{key} [dim]({options_dict[key]})[/dim]"
                table.add_row(cursor, row_text)

        # 添加操作说明
        table.add_row("", "")
        if multi_select:
            table.add_row(
                "",
                "",
                "[dim]使用↑/↓移动，空格选择，回车确认，Esc 取消[/dim]",
            )
        else:
            table.add_row(
                "",
                "[dim]使用↑/↓移动，回车选择，Esc 取消[/dim]",
            )

        return Panel(
            table,
            title=f"[bold]{prompt_text}[/bold]",
            border_style="cyan",
            padding=(1, 2),
        )

    console.print()

    selected_key: str | None = None

    def run_selection_loop() -> None:
        """运行交互式选择循环。"""
        nonlocal selected_key, selected_index

        with Live(
            create_selection_panel(), console=console, transient=True, auto_refresh=False
        ) as live:
            while True:
                try:
                    key = readchar.readkey()

                    # 导航
                    if key == readchar.key.UP or key == readchar.key.CTRL_P:
                        selected_index = (selected_index - 1) % len(option_keys)
                    elif key == readchar.key.DOWN or key == readchar.key.CTRL_N:
                        selected_index = (selected_index + 1) % len(option_keys)

                    # 选择
                    elif key in (readchar.key.ENTER, "\r", "\n"):
                        if multi_select:
                            # 确认多选结果
                            break
                        else:
                            # 单选
                            selected_key = option_keys[selected_index]
                            break

                    elif key == " " and multi_select:
                        # 在多选模式下切换选中状态
                        current_key = option_keys[selected_index]
                        if current_key in selected_items:
                            selected_items.remove(current_key)
                        else:
                            selected_items.add(current_key)

                    # 取消
                    elif key in (readchar.key.ESC, readchar.key.CTRL_C):
                        console.print("\n[yellow]已取消选择[/yellow]")
                        raise KeyboardInterrupt

                    # 更新显示
                    live.update(create_selection_panel(), refresh=True)

                except KeyboardInterrupt:
                    console.print("\n[yellow]已取消选择[/yellow]")
                    raise

    try:
        run_selection_loop()
    except KeyboardInterrupt:
        # 用户取消
        if multi_select:
            return []
        return ""

    # 返回结果
    if multi_select:
        if not selected_items:
            console.print("\n[yellow]未选择任何项[/yellow]")
            return []
        selected_list = sorted(selected_items, key=lambda k: option_keys.index(k))
        console.print(f"\n[green]已选择：[/green] {', '.join(selected_list)}")
        return selected_list
    else:
        if selected_key is None:
            console.print("\n[red]选择失败[/red]")
            return ""
        console.print(f"\n[green]已选择：[/green] {selected_key}")
        return selected_key


def get_text_input(
    console: Console,
    prompt: str,
    default: str | None = None,
    required: bool = True,
) -> str:
    """获取用户的文本输入。

    参数：
        console: Rich 控制台实例
        prompt: 提示信息
        default: 默认值
        required: 是否为必填（不能为空）

    返回：
        用户输入的字符串
    """
    # 显示提示
    if default:
        prompt_text = f"[cyan]{prompt}[/cyan] [dim](默认：{default})[/dim]："
    else:
        prompt_text = f"[cyan]{prompt}[/cyan]："

    console.print(prompt_text, end="")

    # 获取输入
    try:
        user_input = input().strip()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]输入已取消[/yellow]")
        return ""

    # 处理空输入
    if not user_input:
        if default:
            return default
        elif required:
            console.print("[red]错误：[/red] 输入不能为空")
            return get_text_input(console, prompt, default, required)
        else:
            return ""

    return user_input
