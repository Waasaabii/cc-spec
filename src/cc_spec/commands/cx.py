"""cc-spec cx: 通过 tool 调用 Codex 执行任务。

用法:
    cc-spec cx "任务描述"
    cc-spec cx --session <session_id> "继续任务"
    cc-spec cx --list                     # 列出当前会话
    cc-spec cx --pause <session_id>       # 暂停会话
    cc-spec cx --kill <session_id>        # 终止会话
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from cc_spec.codex import ToolClient, get_tool_client

app = typer.Typer(help="通过 cc-spec-tool 调用 Codex")
console = Console()


def _get_project_path() -> Path:
    """获取当前项目路径。"""
    return Path.cwd()


@app.command("run")
def run_codex(
    prompt: str = typer.Argument(..., help="任务描述"),
    session: Optional[str] = typer.Option(
        None, "--session", "-s", help="会话 ID（用于 resume）"
    ),
    timeout: Optional[int] = typer.Option(
        None, "--timeout", "-t", help="超时时间（秒）"
    ),
) -> None:
    """执行 Codex 任务。"""
    project_path = _get_project_path()

    try:
        client = get_tool_client()
    except SystemExit as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]项目:[/cyan] {project_path}")
    console.print(f"[cyan]任务:[/cyan] {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
    if session:
        console.print(f"[cyan]会话:[/cyan] {session}")
    console.print()

    timeout_ms = timeout * 1000 if timeout else None

    with console.status("[bold green]执行中...[/bold green]"):
        result = client.run_codex(
            project_path=project_path,
            prompt=prompt,
            session_id=session,
            timeout_ms=timeout_ms,
        )

    if result.success:
        console.print(f"[green]✓ 任务完成[/green] ({result.duration_seconds:.1f}s)")
        if result.message:
            console.print(f"[dim]{result.message}[/dim]")
    else:
        console.print(f"[red]✗ 任务失败[/red] (exit_code={result.exit_code})")
        if result.message:
            console.print(f"[red]{result.message}[/red]")
        raise typer.Exit(result.exit_code or 1)

    if result.session_id:
        console.print(f"\n[dim]session_id: {result.session_id}[/dim]")


@app.command("list")
def list_sessions() -> None:
    """列出当前项目的 Codex 会话。"""
    project_path = _get_project_path()

    try:
        client = get_tool_client()
    except SystemExit as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    sessions = client.get_sessions(project_path)

    if not sessions:
        console.print("[dim]没有活跃的会话[/dim]")
        return

    table = Table(title="Codex 会话")
    table.add_column("Session ID", style="cyan")
    table.add_column("状态", style="green")
    table.add_column("任务摘要")
    table.add_column("PID", style="dim")

    for sid, info in sessions.items():
        state = info.get("state", "unknown")
        state_style = {
            "running": "green",
            "done": "blue",
            "failed": "red",
            "idle": "yellow",
        }.get(state, "dim")

        table.add_row(
            sid,
            f"[{state_style}]{state}[/{state_style}]",
            info.get("task_summary", "")[:50],
            str(info.get("pid", "-")),
        )

    console.print(table)


@app.command("pause")
def pause_session(
    session_id: str = typer.Argument(..., help="会话 ID"),
) -> None:
    """暂停指定会话。"""
    project_path = _get_project_path()

    try:
        client = get_tool_client()
    except SystemExit as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    if client.pause_session(project_path, session_id):
        console.print(f"[green]✓ 会话 {session_id} 已暂停[/green]")
    else:
        console.print(f"[red]✗ 暂停失败[/red]")
        raise typer.Exit(1)


@app.command("kill")
def kill_session(
    session_id: str = typer.Argument(..., help="会话 ID"),
) -> None:
    """终止指定会话。"""
    project_path = _get_project_path()

    try:
        client = get_tool_client()
    except SystemExit as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    if client.kill_session(project_path, session_id):
        console.print(f"[green]✓ 会话 {session_id} 已终止[/green]")
    else:
        console.print(f"[red]✗ 终止失败[/red]")
        raise typer.Exit(1)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    prompt: Optional[str] = typer.Argument(None, help="任务描述（直接执行时使用）"),
    session: Optional[str] = typer.Option(
        None, "--session", "-s", help="会话 ID（用于 resume）"
    ),
    timeout: Optional[int] = typer.Option(
        None, "--timeout", "-t", help="超时时间（秒）"
    ),
) -> None:
    """通过 cc-spec-tool 调用 Codex。

    示例:
        cc-spec cx "实现一个简单的计算器"
        cc-spec cx run "任务描述"
        cc-spec cx list
        cc-spec cx pause <session_id>
        cc-spec cx kill <session_id>
    """
    # 如果有子命令，不执行默认行为
    if ctx.invoked_subcommand is not None:
        return

    # 如果没有 prompt，显示帮助
    if prompt is None:
        console.print(ctx.get_help())
        return

    # 直接执行 run 命令
    run_codex(prompt=prompt, session=session, timeout=timeout)


if __name__ == "__main__":
    app()
