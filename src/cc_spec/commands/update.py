"""cc-spec v0.1.5 的 update 命令。

v0.1.5：只面向 Claude Code 生成/更新 `/cc-spec:*` 命令文件；
Codex CLI 作为执行层由 cc-spec 调用，不再生成 Codex prompts。
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import typer
import yaml
from rich.console import Console

from cc_spec.core.command_generator import CC_SPEC_COMMANDS, get_generator
from cc_spec.core.config import Config, load_config
from cc_spec.ui.banner import show_banner
from cc_spec.utils.download import download_file, get_github_raw_url
from cc_spec.utils.files import find_project_root, get_cc_spec_dir

console = Console()

TEMPLATE_REPO = "anthropics/cc-spec"  # TODO：更新为实际仓库
TEMPLATE_BRANCH = "main"
TEMPLATE_PATH_PREFIX = "templates"

TEMPLATE_FILES = [
    "spec-template.md",
    "plan-template.md",
    "tasks-template.md",
    "checklist-template.md",
    "agent-file-template.md",
]


def update_command(
    target: str = typer.Argument(
        None,
        help="更新目标：commands、subagent、all",
    ),
    templates: bool = typer.Option(
        False,
        "--templates",
        "-t",
        help="将模板更新到最新版本",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="强制覆盖（不二次确认）",
    ),
) -> None:
    """更新配置、slash 命令或模板。"""
    show_banner(console)

    project_root = find_project_root()
    if project_root is None:
        console.print("[red]错误：[/red] 当前目录不是 cc-spec 项目，请先运行 `cc-spec init`。")
        raise typer.Exit(1)

    cc_spec_root = get_cc_spec_dir(project_root)
    config_path = cc_spec_root / "config.yaml"

    try:
        config = load_config(config_path)
    except FileNotFoundError:
        console.print("[red]错误：[/red] 未找到配置文件，请先运行 `cc-spec init`。")
        raise typer.Exit(1)

    updated = False

    if templates:
        _update_templates(cc_spec_root, force)
        updated = True

    target_lower = (target or "all").lower()

    if target_lower in ("commands", "all"):
        _update_slash_commands(project_root, config, force)
        updated = True

    if target_lower in ("subagent", "all"):
        _update_subagent_config(cc_spec_root, force)
        updated = True

    if updated:
        console.print("\n[green]√[/green] 更新完成。")
    else:
        console.print("[dim]Nothing to update.[/dim]")


def _update_slash_commands(project_root: Path, config: Config, force: bool) -> None:
    """更新 Claude Code slash 命令。"""
    _ = config  # 预留：后续可能从 config 读取命令策略
    _ = force

    console.print("[cyan]正在更新 Claude Code slash 命令...[/cyan]")

    generator = get_generator("claude")
    if not generator:
        console.print("[red]错误：[/red] 未找到 Claude 的命令生成器。")
        raise typer.Exit(1)

    updated_count = 0
    created_count = 0
    cmd_dir = generator.get_command_dir(project_root)

    for cmd_name, description in CC_SPEC_COMMANDS:
        before_exists = (cmd_dir / f"{cmd_name}.md").exists()
        path = generator.update_command(cmd_name, description, project_root)
        if not path:
            continue
        if before_exists:
            updated_count += 1
        else:
            created_count += 1

    console.print(
        f"  [green]√[/green] Claude 命令已生成/更新：created={created_count} updated={updated_count}"
    )


def _update_subagent_config(cc_spec_root: Path, force: bool) -> None:
    """更新 subagent 配置。"""
    _ = force
    console.print("[cyan]正在更新 subagent 配置...[/cyan]")

    config_path = cc_spec_root / "config.yaml"

    try:
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        data = {}

    subagent = data.get("subagent", {})
    updated = False

    if "common" not in subagent:
        subagent["common"] = {
            "model": "sonnet",
            "timeout": 300000,
            "permissionMode": "acceptEdits",
            "tools": "Read,Write,Edit,Glob,Grep,Bash",
        }
        updated = True
        console.print("  [green]+[/green] Added common configuration")

    if "profiles" not in subagent:
        subagent["profiles"] = {
            "quick": {
                "model": "haiku",
                "timeout": 60000,
                "description": "Quick tasks: simple modifications",
            },
            "heavy": {
                "model": "opus",
                "timeout": 600000,
                "description": "Heavy tasks: complex refactoring",
            },
            "explore": {
                "model": "sonnet",
                "timeout": 180000,
                "tools": "Read,Glob,Grep,WebFetch,WebSearch",
                "description": "Exploration tasks: code research",
            },
        }
        updated = True
        console.print("  [green]+[/green] Added profile configurations")

    if updated:
        data["subagent"] = subagent
        data["version"] = data.get("version", "1.3")

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

        console.print("  [green]√[/green] 已更新 subagent 配置")
    else:
        console.print("  [dim]Subagent configuration is already up to date[/dim]")


def _update_templates(cc_spec_root: Path, force: bool) -> None:
    """更新模板文件（在线下载；失败则使用内置模板兜底）。"""
    console.print("[cyan]正在更新模板文件...[/cyan]")

    templates_dir = cc_spec_root / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)

    bundled_templates_dir = Path(__file__).parent.parent / "templates"

    updated_count = 0
    skipped_count = 0

    for template_file in TEMPLATE_FILES:
        dest_path = templates_dir / template_file

        if dest_path.exists() and not force:
            skipped_count += 1
            continue

        url = get_github_raw_url(
            TEMPLATE_REPO,
            TEMPLATE_BRANCH,
            f"{TEMPLATE_PATH_PREFIX}/{template_file}",
        )

        downloaded = False
        try:
            downloaded = asyncio.run(download_file(url, dest_path))
        except Exception:
            downloaded = False

        if downloaded:
            console.print(f"  [green]√[/green] {template_file}（已下载）")
            updated_count += 1
            continue

        bundled_path = bundled_templates_dir / template_file
        if bundled_path.exists():
            shutil.copy2(bundled_path, dest_path)
            console.print(f"  [green]√[/green] {template_file}（来自内置模板）")
            updated_count += 1
        else:
            console.print(f"  [red]×[/red] {template_file}（不可用）")

    if updated_count > 0:
        console.print(f"\n[green]√[/green] 已更新 {updated_count} 个模板")
    if skipped_count > 0:
        console.print(f"[dim]已跳过 {skipped_count} 个模板[/dim]")

