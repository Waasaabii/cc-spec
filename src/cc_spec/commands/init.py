"""cc-spec 的 init 命令实现（v0.1.5：Claude 编排 + Codex 执行）。"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.tree import Tree

from cc_spec.core.command_generator import CC_SPEC_COMMANDS, get_generator
from cc_spec.core.config import Config, save_config
from cc_spec.core.standards_renderer import (
    render_agents_md,
    render_skill_md,
    write_managed_file,
)
from cc_spec.ui.banner import show_banner
from cc_spec.utils.files import ensure_dir, get_cc_spec_dir, get_config_path

console = Console()

DEFAULT_CC_SPECIGNORE = """# cc-spec KB scanning ignore rules
#
# 说明：
# - 该文件用于控制 v0.1.5 知识库扫描范围
# - 语法为简化版 gitignore：支持注释、空行、目录（以 / 结尾）、以及 ! 反选
#
# 默认情况下 cc-spec 内置了一组常见忽略规则（.git/.venv/node_modules 等）。
# 你可以在此文件中添加/覆盖规则以调整扫描范围。

# VCS
.git/

# Virtual environments / dependencies (do NOT embed dependency source)
.venv/
venv/
ENV/
env/
node_modules/

# Build outputs
dist/
build/

# Caches
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/

# cc-spec runtime & derived artifacts (KB will manage these explicitly)
.cc-spec/runtime/
.cc-spec/vectordb/
.cc-spec/kb.events.jsonl
.cc-spec/kb.snapshot.jsonl
.cc-spec/kb.manifest.json
.cc-spec/kb.attribution.json
"""


def init_command(
    project: Optional[str] = typer.Argument(
        None, help="项目名称（默认为当前目录名）"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="强制覆盖已存在的 .cc-spec 目录"
    ),
    agent: Optional[str] = typer.Option(
        None,
        "--agent",
        "-a",
        help="(deprecated) v0.1.5 仅支持 claude",
        hidden=True,
    ),
) -> None:
    """
    在当前目录初始化cc-spec工作流。

    此命令将：
    1. 创建 .cc-spec/ 目录结构
    2. 下载/复制模板文件到 .cc-spec/templates/
    3. 为 Claude Code 生成 `/cc-spec:*` 命令文件（编排层）
    4. 生成 config.yaml
    4. 显示初始化成功消息

    示例：
        cc-spec init
        cc-spec init my-project
        cc-spec init --force  # 覆盖现有配置
    """
    # 显示启动 Banner
    show_banner(console)

    # 获取项目根目录（当前目录）
    project_root = Path.cwd()

    # 确定项目名称
    if project is None:
        project_name = project_root.name
    else:
        project_name = project

    # 检查 .cc-spec 是否已存在
    cc_spec_dir = get_cc_spec_dir(project_root)
    config_path = get_config_path(project_root)

    if cc_spec_dir.exists() and not force:
        console.print(
            Panel(
                "[yellow]目录 .cc-spec 已存在！[/yellow]\n\n"
                "使用 [cyan]--force[/cyan] 参数覆盖现有配置。",
                title="[bold yellow]警告[/bold yellow]",
                border_style="yellow",
            )
        )
        raise typer.Exit(1)

    if agent and agent.lower() != "claude":
        console.print("[red]错误：[/red] v0.1.5 仅支持 claude（Claude Code 负责编排）。")
        raise typer.Exit(1)

    # 步骤1: 创建目录结构
    console.print("[cyan]正在创建目录结构...[/cyan]")

    templates_dir = cc_spec_dir / "templates"
    changes_dir = cc_spec_dir / "changes"
    specs_dir = cc_spec_dir / "specs"
    archive_dir = cc_spec_dir / "archive"

    ensure_dir(templates_dir)
    ensure_dir(changes_dir)
    ensure_dir(specs_dir)
    ensure_dir(archive_dir)

    console.print("[green]✓[/green] 已创建 .cc-spec/ 目录结构")

    # 步骤2: 为 Claude Code 生成命令文件
    console.print("[cyan]正在为 Claude Code 生成命令文件...[/cyan]")

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

    try:
        cmd_dir_display = str(cmd_dir.relative_to(project_root))
    except ValueError:
        cmd_dir_display = str(cmd_dir)

    console.print(
        f"[green]✓[/green] Claude 命令已生成/更新：created={created_count} updated={updated_count}"
        f"（输出到 {cmd_dir_display}）"
    )
    console.print()

    # 步骤2.5: 生成/更新 AGENTS.md 与 SKILL.md（规范产出物）
    console.print("[cyan]正在生成/更新 AGENTS.md 与 SKILL.md...[/cyan]")
    try:
        agents_md_path = project_root / "AGENTS.md"
        skill_md_path = project_root / ".claude" / "skills" / "cc-spec-standards" / "SKILL.md"

        agents_md_content = render_agents_md()
        skill_md_content = render_skill_md()

        write_managed_file(agents_md_path, agents_md_content)
        write_managed_file(skill_md_path, skill_md_content)

        console.print("[green]?[/green] 已生成/更新 AGENTS.md 与 SKILL.md")
    except Exception as e:
        console.print(f"[yellow]?[/yellow] 警告: 生成规范产出物失败: {e}")

    console.print()

    # 步骤2.6: 生成 .cc-specignore（KB 扫描规则）
    ignore_path = project_root / ".cc-specignore"
    if not ignore_path.exists():
        console.print("[cyan]正在生成 .cc-specignore...[/cyan]")
        try:
            ignore_path.write_text(DEFAULT_CC_SPECIGNORE.strip() + "\n", encoding="utf-8")
            console.print("[green]✓[/green] 已生成 .cc-specignore（KB 扫描规则）")
        except Exception as e:
            console.print(f"[yellow]⚠[/yellow] 警告: 生成 .cc-specignore 失败: {e}")
    else:
        console.print("[dim].cc-specignore 已存在，跳过生成[/dim]")

    console.print()

    # 步骤3: 复制bundled模板
    console.print("[cyan]正在复制模板文件...[/cyan]")

    try:
        # 获取内置模板目录
        bundled_templates_dir = Path(__file__).parent.parent / "templates"

        if bundled_templates_dir.exists():
            import shutil

            # 复制所有模板文件（根目录）
            template_files = list(bundled_templates_dir.glob("*.md"))
            for template_file in template_files:
                dest_file = templates_dir / template_file.name
                shutil.copy2(template_file, dest_file)

            # 复制 checklists 子目录（如果存在）
            bundled_checklists_dir = bundled_templates_dir / "checklists"
            if bundled_checklists_dir.exists():
                dest_checklists_dir = templates_dir / "checklists"
                dest_checklists_dir.mkdir(exist_ok=True)

                checklist_files = list(bundled_checklists_dir.glob("*.md"))
                for checklist_file in checklist_files:
                    dest_file = dest_checklists_dir / checklist_file.name
                    shutil.copy2(checklist_file, dest_file)

                console.print(f"[green]✓[/green] 已复制 {len(template_files)} 个模板文件和 {len(checklist_files)} 个检查清单到 .cc-spec/templates/")
            else:
                console.print(f"[green]✓[/green] 已复制 {len(template_files)} 个模板文件到 .cc-spec/templates/")
        else:
            console.print(
                "[yellow]⚠[/yellow] 警告: 未找到bundled模板文件"
            )
    except Exception as e:
        console.print(
            f"[yellow]⚠[/yellow] 警告: 复制模板失败: {e}"
        )

    # 步骤4: 生成 config.yaml
    console.print("[cyan]正在生成 config.yaml...[/cyan]")

    config = Config(project_name=project_name)

    try:
        save_config(config, config_path)
        console.print("[green]✓[/green] 已生成 .cc-spec/config.yaml")
    except Exception as e:
        console.print(f"[red]错误:[/red] 保存配置失败: {e}")
        raise typer.Exit(1)

    # 步骤5: 显示成功消息
    console.print()

    console.print(
        Panel(
            "[bold green]✅ cc-spec 初始化完成！[/bold green]",
            border_style="green",
        )
    )

    console.print()

    # 显示目录结构
    console.print("[bold cyan]📁 目录结构:[/bold cyan]")
    console.print()

    tree = Tree("📁 [bold].cc-spec/[/bold]", guide_style="dim")
    tree.add("[cyan]config.yaml[/cyan]         # 配置文件")
    tree.add("[cyan]templates/[/cyan]          # 公共模板")
    tree.add("[cyan]changes/[/cyan]            # 活跃变更")
    tree.add("[cyan]specs/[/cyan]              # 规格说明")
    tree.add("[cyan]archive/[/cyan]            # 已归档变更")

    console.print(tree)
    console.print()

    console.print(
        Panel(
            f"[cyan]项目名称:[/cyan] {project_name}\n"
            f"[cyan]编排工具:[/cyan] Claude Code\n"
            f"[cyan]执行工具:[/cyan] Codex CLI（由 cc-spec 调用）\n\n"
            f"[bold]下一步操作:[/bold]\n"
            f"  1. （已完成）终端执行 [cyan]cc-spec init[/cyan]\n"
            f"  2. 在 Claude Code 中执行 [cyan]/cc-spec:init[/cyan] 构建/更新 KB（先 scan 再入库）\n"
            f"  3. 在 Claude Code 中执行 [cyan]/cc-spec:specify <变更名称>[/cyan] 创建变更规格\n"
            f"  4. 继续执行 [cyan]/cc-spec:clarify --detail[/cyan] CC↔CX 讨论\n"
            f"  5. 继续执行 [cyan]/cc-spec:clarify --review[/cyan] 用户审查\n"
            f"  6. 继续执行 [cyan]/cc-spec:plan[/cyan]\n"
            f"  7. 继续执行 [cyan]/cc-spec:apply[/cyan]\n"
            f"  8. 继续执行 [cyan]/cc-spec:accept[/cyan] 端到端验收\n"
            f"  9. 继续执行 [cyan]/cc-spec:archive[/cyan]",
            title="[bold green]快速开始[/bold green]",
            border_style="green",
        )
    )
