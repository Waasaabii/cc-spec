"""cc-spec chat: 与 Codex 进行多轮交互式对话。"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from cc_spec.codex.client import CodexClient
from cc_spec.codex.streaming import get_sse_client
from cc_spec.utils.files import find_project_root

console = Console()


def _is_interactive() -> bool:
    """检测是否为交互式终端。"""
    return sys.stdin.isatty()


def _load_project_context(project_root: Path) -> str:
    """加载项目默认上下文。"""
    context_parts: list[str] = []

    # 1. CLAUDE.md
    claude_md = project_root / "CLAUDE.md"
    if claude_md.exists():
        try:
            content = claude_md.read_text(encoding="utf-8")
            context_parts.append(f"# 项目说明 (CLAUDE.md)\n\n{content}")
        except Exception:
            pass

    # 2. .cc-spec/config.yaml 摘要
    config_yaml = project_root / ".cc-spec" / "config.yaml"
    if config_yaml.exists():
        try:
            content = config_yaml.read_text(encoding="utf-8")
            # 只取前 50 行作为摘要
            lines = content.splitlines()[:50]
            context_parts.append(f"# 项目配置 (.cc-spec/config.yaml)\n\n```yaml\n{chr(10).join(lines)}\n```")
        except Exception:
            pass

    # 3. README.md 摘要
    readme = project_root / "README.md"
    if readme.exists():
        try:
            content = readme.read_text(encoding="utf-8")
            # 只取前 100 行
            lines = content.splitlines()[:100]
            context_parts.append(f"# 项目说明 (README.md)\n\n{chr(10).join(lines)}")
        except Exception:
            pass

    if not context_parts:
        return ""

    return "\n\n---\n\n".join(context_parts)


def _build_prompt(user_message: str, context: str, is_first: bool) -> str:
    """构建发送给 Codex 的提示。

    Codex 会自动读取项目的 CLAUDE.md 文件获取项目上下文和语言偏好，
    所以这里只需要传递用户消息即可。
    """
    # 直接返回用户消息，让 Codex 自己读取 CLAUDE.md
    return user_message


def chat_command(
    workdir: Path = typer.Option(
        Path("."),
        "--workdir",
        "-d",
        help="工作目录",
    ),
    no_context: bool = typer.Option(
        False,
        "--no-context",
        help="不加载项目默认上下文",
    ),
    resume: str = typer.Option(
        "",
        "--resume",
        "-r",
        help="继续之前的会话（提供 session_id）",
    ),
    message: str = typer.Option(
        "",
        "--message",
        "-m",
        help="单次消息模式（发送一条消息后退出）",
    ),
    show_session: bool = typer.Option(
        False,
        "--show-session",
        "-s",
        help="显示 session_id（用于脚本调用）",
    ),
) -> None:
    """与 Codex 进行多轮交互式对话。

    自动加载项目上下文（CLAUDE.md、config.yaml、README.md），
    并保持会话连续性。

    交互模式：直接运行，使用 Ctrl+C 或输入 exit/quit 退出。
    单次模式：使用 -m 参数发送单条消息（适合脚本调用）。
    管道模式：通过管道输入多行消息，每行一轮对话。

    示例：
        cc-spec chat                                    # 交互模式
        cc-spec chat -m "你好" -s                       # 单次消息，显示 session_id
        cc-spec chat -m "继续" -r <session_id>          # 继续之前的会话
        echo "你好" | cc-spec chat                      # 管道单轮
        cat questions.txt | cc-spec chat               # 管道多轮（每行一轮）
    """
    # 解析项目根目录
    project_root = find_project_root(workdir) or workdir.resolve()

    # 加载上下文
    context = "" if no_context else _load_project_context(project_root)

    client = CodexClient()
    viewer = get_sse_client(project_root)
    session_id: str | None = resume if resume else None
    is_first = not resume  # 如果是继续会话，则不是第一轮

    interactive = _is_interactive()

    def _send_user_input(text: str) -> None:
        """发送用户输入到 Viewer。"""
        if viewer is None:
            return
        viewer.publish_event({
            "type": "codex.user_input",
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "session_id": session_id,
            "text": text,
        })

    def _process_message(user_input: str, max_retries: int = 2) -> bool:
        """处理单条消息，返回是否继续。支持自动重试。"""
        nonlocal session_id, is_first

        if not user_input.strip():
            return True
        if user_input.strip().lower() in ("exit", "quit", "q"):
            if interactive:
                console.print("[dim]再见！[/dim]")
            return False

        # 发送用户输入到 Viewer
        _send_user_input(user_input)

        # 构建提示
        prompt = _build_prompt(user_input, context, is_first)

        # 调用 Codex（支持重试）
        if interactive:
            console.print("[bold blue]Codex[/bold blue]: ", end="")
        else:
            print(f"[You] {user_input}", flush=True)

        result = None
        for attempt in range(max_retries + 1):
            try:
                if session_id:
                    result = client.resume(session_id, prompt, project_root)
                else:
                    result = client.execute(prompt, project_root)

                # 更新 session_id
                if result.session_id:
                    session_id = result.session_id

                # 成功或有明确结果，跳出重试
                if result.success or result.message:
                    break

            except Exception as e:
                if attempt < max_retries:
                    if interactive:
                        console.print(f"\n[yellow]连接中断，正在重试 ({attempt + 1}/{max_retries})...[/yellow]")
                    # 如果有 session_id，下次重试会自动继续
                    continue
                else:
                    if interactive:
                        console.print(f"\n[red]重试失败: {e}[/red]")
                    else:
                        print(f"[Error] 重试失败: {e}", flush=True)
                    return True

        # 显示结果
        if result and result.success:
            if interactive:
                console.print(f"[white]{result.message}[/white]")
            else:
                print(f"[Codex] {result.message}", flush=True)
        elif result:
            error_msg = result.message or "执行失败"
            if interactive:
                console.print(f"[red]错误: {error_msg}[/red]")
                if result.stderr:
                    console.print(f"[dim]{result.stderr[:500]}[/dim]")
            else:
                print(f"[Error] {error_msg}", flush=True)

        is_first = False
        return True

    # 单次消息模式（-m 参数）
    if message:
        _process_message(message)
        # 显示 session_id
        if show_session and session_id:
            print(f"[Session] {session_id}", flush=True)
        return

    # 交互模式
    if interactive:
        console.print(
            Panel(
                f"[bold]cc-spec chat[/bold] - Codex 多轮对话模式\n"
                f"项目: [cyan]{project_root.name}[/cyan]\n"
                f"上下文: [{'green' if context else 'yellow'}]{'已加载' if context else '未加载'}[/]\n"
                + (f"会话: [cyan]{session_id}[/cyan]\n" if session_id else "")
                + f"\n输入消息开始对话，[dim]exit[/dim] 或 [dim]Ctrl+C[/dim] 退出",
                title="[bold blue]Chat[/bold blue]",
                border_style="blue",
            )
        )

        while True:
            try:
                user_input = Prompt.ask("\n[bold green]You[/bold green]")
                if not _process_message(user_input):
                    break
            except KeyboardInterrupt:
                console.print("\n[dim]再见！[/dim]")
                break
            except EOFError:
                console.print("\n[dim]再见！[/dim]")
                break
            except Exception as e:
                console.print(f"[red]错误: {e}[/red]")
                continue

        # 显示 session_id（用于后续继续会话）
        if show_session and session_id:
            console.print(f"\n[dim]Session ID: {session_id}[/dim]")

    # 管道模式：从 stdin 读取多行输入
    else:
        for line in sys.stdin:
            user_input = line.rstrip("\n\r")
            try:
                if not _process_message(user_input):
                    break
            except Exception as e:
                print(f"[Error] {e}", flush=True)
                continue

        # 显示 session_id（用于后续继续会话）
        if show_session and session_id:
            print(f"[Session] {session_id}", flush=True)
