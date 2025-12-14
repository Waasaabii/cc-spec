"""cc-spec 的 init 命令实现。"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.tree import Tree

from cc_spec.core.command_generator import get_generator
from cc_spec.core.config import AgentsConfig, Config, detect_agent, save_config
from cc_spec.ui.banner import show_banner
from cc_spec.ui.prompts import select_option
from cc_spec.utils.files import ensure_dir, get_cc_spec_dir, get_config_path

console = Console()

# AI 工具配置（与 docs/plan + core/command_generator.py 对齐）
# 首选工具放在前面：claude / cursor / gemini
AI_TOOLS_CONFIG = {
    # === 首选工具 ===
    "claude": {
        "name": "Claude Code (Anthropic Claude)",
        "folder": ".claude/",
        "requires_cli": True,
    },
    "cursor": {
        "name": "Cursor",
        "folder": ".cursor/",
        "requires_cli": False,
    },
    "gemini": {
        "name": "Gemini CLI (Google Gemini)",
        "folder": ".gemini/",
        "requires_cli": True,
    },
    # === 其他工具（17+ 命令生成器覆盖） ===
    "copilot": {
        "name": "GitHub Copilot",
        "folder": ".github/",
        "requires_cli": False,
    },
    "amazonq": {
        "name": "Amazon Q Developer",
        "folder": ".amazonq/",
        "requires_cli": True,
    },
    "windsurf": {
        "name": "Windsurf",
        "folder": ".windsurf/",
        "requires_cli": False,
    },
    "qwen": {
        "name": "Qwen Code",
        "folder": ".qwen/",
        "requires_cli": True,
    },
    "codeium": {
        "name": "Codeium",
        "folder": ".codeium/",
        "requires_cli": False,
    },
    "continue": {
        "name": "Continue.dev",
        "folder": ".continue/",
        "requires_cli": False,
    },
    # v1.2 新增
    "tabnine": {
        "name": "Tabnine",
        "folder": ".tabnine/",
        "requires_cli": False,
    },
    "aider": {
        "name": "Aider",
        "folder": ".aider/",
        "requires_cli": True,
    },
    "devin": {
        "name": "Devin",
        "folder": ".devin/",
        "requires_cli": True,
    },
    "replit": {
        "name": "Replit AI",
        "folder": ".replit/",
        "requires_cli": False,
    },
    "cody": {
        "name": "Sourcegraph Cody",
        "folder": ".cody/",
        "requires_cli": False,
    },
    "supermaven": {
        "name": "Supermaven",
        "folder": ".supermaven/",
        "requires_cli": False,
    },
    "kilo": {
        "name": "Kilo Code",
        "folder": ".kilo/",
        "requires_cli": False,
    },
    "auggie": {
        "name": "Auggie",
        "folder": ".auggie/",
        "requires_cli": True,
    },
    # 预留：Codex CLI（当前未实现命令生成器，仍可用于放置配置）
    "codex": {
        "name": "Codex CLI",
        "folder": ".codex/",
        "requires_cli": True,
    },
}

# 用于选择界面的简化显示
AI_TOOLS_DISPLAY = {key: config["name"] for key, config in AI_TOOLS_CONFIG.items()}


def init_command(
    project: Optional[str] = typer.Argument(
        None, help="项目名称（默认为当前目录名）"
    ),
    agent: Optional[str] = typer.Option(
        None, "--agent", "-a", help="AI工具类型（claude, cursor, gemini等）"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="强制覆盖已存在的.cc-spec目录"
    ),
) -> None:
    """
    在当前目录初始化cc-spec工作流。

    此命令将：
    1. 创建 .cc-spec/ 目录结构
    2. 下载/复制模板文件到 .cc-spec/templates/
    3. 生成包含检测到或指定的AI工具的 config.yaml
    4. 显示初始化成功消息

    示例：
        cc-spec init
        cc-spec init my-project
        cc-spec init --agent claude
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

    # 检测或选择AI工具（支持多选）
    selected_agents = []

    if agent is None:
        # 尝试自动检测
        detected_agent = detect_agent(project_root)

        if detected_agent != "unknown":
            # 检测到了，询问是否使用
            console.print(
                f"[cyan]检测到AI工具:[/cyan] [bold]{detected_agent}[/bold]"
            )
            console.print()

            # 提供选项：使用检测到的或手动选择
            choice = select_option(
                console=console,
                options={
                    "use_detected": f"使用检测到的工具: {detected_agent}",
                    "choose_more": "手动选择AI工具（支持多选）",
                },
                prompt_text="请选择",
                default="use_detected",
            )

            if choice == "use_detected":
                selected_agents = [detected_agent]
            else:
                # 手动多选
                console.print()
                console.print("[cyan]提示：可以选择多个AI工具，使用空格键选择，Enter确认[/cyan]")
                console.print()
                selected = select_option(
                    console=console,
                    options=AI_TOOLS_DISPLAY,
                    prompt_text="选择AI工具（支持多选）",
                    default="claude",
                    multi_select=True,
                )
                selected_agents = selected if isinstance(selected, list) else [selected]
        else:
            # 未检测到，显示多选界面
            console.print("[cyan]未检测到AI工具，请手动选择:[/cyan]")
            console.print("[cyan]提示：可以选择多个AI工具，使用空格键选择，Enter确认[/cyan]")
            console.print()
            selected = select_option(
                console=console,
                options=AI_TOOLS_DISPLAY,
                prompt_text="选择AI工具（支持多选）",
                default="claude",
                multi_select=True,
            )
            selected_agents = selected if isinstance(selected, list) else [selected]
    else:
        # 命令行指定了agent
        if agent in AI_TOOLS_CONFIG:
            selected_agents = [agent]
            console.print(f"[cyan]使用指定的AI工具:[/cyan] [bold]{agent}[/bold]")
        else:
            console.print(f"[red]错误：未知的AI工具 '{agent}'[/red]")
            console.print(f"[yellow]可用的工具：{', '.join(AI_TOOLS_CONFIG.keys())}[/yellow]")
            raise typer.Exit(1)

    # 确保至少选择了一个
    if not selected_agents:
        console.print("[red]错误：必须至少选择一个AI工具[/red]")
        raise typer.Exit(1)

    console.print()
    console.print(f"[green]已选择 {len(selected_agents)} 个AI工具:[/green] {', '.join(selected_agents)}")
    console.print()

    # 步骤1: 创建目录结构
    console.print("[cyan]正在创建目录结构...[/cyan]")

    templates_dir = cc_spec_dir / "templates"
    changes_dir = cc_spec_dir / "changes"
    specs_dir = cc_spec_dir / "specs"

    ensure_dir(templates_dir)
    ensure_dir(changes_dir)
    ensure_dir(specs_dir)

    console.print("[green]✓[/green] 已创建 .cc-spec/ 目录结构")

    # 步骤1.5: 为每个选择的AI工具创建文件夹
    console.print("[cyan]正在创建AI工具配置目录...[/cyan]")
    for agent_key in selected_agents:
        agent_config = AI_TOOLS_CONFIG[agent_key]
        # Codex CLI 的配置/Prompts 默认在用户目录 `~/.codex/`，不需要在项目内创建 `.codex/`
        if agent_key == "codex":
            console.print(
                f"[green]✓[/green] 已选择 codex（prompts 输出到用户目录 ~/.codex/prompts）"
            )
            continue

        agent_folder = project_root / agent_config["folder"]

        # 创建AI工具文件夹
        ensure_dir(agent_folder)

        # 创建基础README文件
        readme_path = agent_folder / "README.md"
        if not readme_path.exists():
            readme_content = f"""# {agent_config["name"]} 配置

此目录包含 {agent_config["name"]} 的配置文件。

## 注意事项

- 此目录可能包含认证令牌、凭证等敏感信息
- 请确保将敏感文件添加到 `.gitignore` 中
- 不要将包含密钥的文件提交到公共仓库

## 相关文档

- [cc-spec 文档](https://github.com/Waasaabii/cc-spec)
"""
            readme_path.write_text(readme_content, encoding="utf-8")

        console.print(f"[green]✓[/green] 已创建 {agent_config['folder']} ({agent_config['name']})")

    console.print()

    # 步骤2: 生成AI工具命令文件
    console.print("[cyan]正在为AI工具生成命令文件...[/cyan]")

    total_commands_generated = 0
    for agent_key in selected_agents:
        generator = get_generator(agent_key)
        if generator:
            try:
                created_files = generator.generate_all(project_root)
                total_commands_generated += len(created_files)

                cmd_dir = generator.get_command_dir(project_root)
                try:
                    cmd_dir_display = str(cmd_dir.relative_to(project_root))
                except ValueError:
                    cmd_dir_display = str(cmd_dir)

                console.print(
                    f"[green]✓[/green] 已为 {agent_key} 生成 {len(created_files)} 个命令文件"
                    f"（输出到 {cmd_dir_display}）"
                )
            except Exception as e:
                console.print(
                    f"[yellow]⚠[/yellow] 警告: 为 {agent_key} 生成命令文件失败: {e}"
                )
        else:
            console.print(
                f"[yellow]⚠[/yellow] {agent_key} 暂不支持自动生成命令文件"
            )

    if total_commands_generated > 0:
        console.print(f"[green]✓[/green] 总共生成了 {total_commands_generated} 个命令文件")
    console.print()

    # 步骤2.5: 生成AGENTS.md通用指令文件
    agents_md_path = project_root / "AGENTS.md"
    if not agents_md_path.exists():
        console.print("[cyan]正在生成 AGENTS.md...[/cyan]")
        try:
            agents_md_content = """# CC-Spec 工作流指南

本项目使用 **cc-spec** 进行规格驱动开发（Spec → Plan → Execute → Verify → Archive）。

## 快速入口

- 标准 7 步：`init → specify → clarify → plan → apply → checklist → archive`
- 超简单模式：`quick-delta`

## 在 AI 工具中调用（由 `cc-spec init` 生成命令文件）

| 工具 | 调用方式 | 示例 |
|------|----------|------|
| Claude Code | `/cc-spec:specify` | `/cc-spec:specify add-oauth` |
| Cursor | `/cc-spec-specify` | `/cc-spec-specify add-oauth` |
| Gemini CLI | `/cc-spec:specify` | `/cc-spec:specify add-oauth` |
| Codex CLI | `/prompts:cc-spec-specify` | `/prompts:cc-spec-specify add-oauth` |
| GitHub Copilot | 提示库选择 | 选择 `cc-spec-specify` |
| Amazon Q | `@cc-spec-specify` | `@cc-spec-specify add-oauth` |
| 其他工具 | 自然语言 | “帮我执行 cc-spec specify …” |

## CLI 命令速查

### init - 初始化项目
```bash
cc-spec init [project] [--agent <agent>] [--force]
```

### specify - 创建/编辑变更提案
```bash
cc-spec specify <change-name | C-XXX>
```

### clarify - 审查任务 / 标记返工（可选歧义检测）
```bash
cc-spec clarify [C-XXX | C-XXX:task-id | task-id] [--detect]
```

### plan - 生成执行计划（tasks.yaml）
```bash
cc-spec plan [change-name | C-XXX]
```

### apply - 执行任务（SubAgent 并发）
```bash
cc-spec apply [change-name | C-XXX]
```

### checklist - 验收打分（默认 ≥80 通过）
```bash
cc-spec checklist [change-name | C-XXX] [--threshold 80]
```

### archive - 归档已完成变更
```bash
cc-spec archive <change-name | C-XXX>
```

### list - 列出 changes/tasks/specs/archive
```bash
cc-spec list <changes | tasks | specs | archive>
```

### goto - 导航到变更或任务
```bash
cc-spec goto <C-XXX | C-XXX:task-id | change-name>
```

### update - 更新命令/模板/配置
```bash
cc-spec update [commands|subagent|agents|all] [--add-agent <agent> ...] [--templates]
```

### quick-delta - 一步记录并归档小变更
```bash
cc-spec quick-delta \"<description>\"
```

---

*本文件由 `cc-spec init` 生成，可按需自行补充项目约定。*
"""
            agents_md_path.write_text(agents_md_content, encoding="utf-8")
            console.print("[green]✓[/green] 已生成 AGENTS.md 通用指令文件")
        except Exception as e:
            console.print(
                f"[yellow]⚠[/yellow] 警告: 生成 AGENTS.md 失败: {e}"
            )
    else:
        console.print("[dim]AGENTS.md 已存在，跳过生成[/dim]")

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

    # v1.2: 使用 AgentsConfig 支持多工具配置
    primary_agent = selected_agents[0]

    config = Config(
        version="1.2",  # v1.2：更新后的版本号
        agent=primary_agent,  # 为了向后兼容保留
        agents=AgentsConfig(  # v1.2：多工具配置
            enabled=selected_agents,
            default=primary_agent,
        ),
        project_name=project_name,
    )

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

    # 显示配置建议
    console.print("[bold cyan]⚙️  建议配置:[/bold cyan]")
    console.print()
    console.print("  编辑 [cyan].cc-spec/config.yaml[/cyan] 可以调整以下配置：")
    console.print()
    console.print("  1. [yellow]subagent.max_concurrent[/yellow]: [green]10[/green]")
    console.print("     SubAgent 最大并发数（Claude Code 中最多支持 10 个并发）")
    console.print()
    console.print(f"  2. [yellow]agents.enabled[/yellow]: [green][{', '.join(selected_agents)}][/green]")
    console.print("     启用的 AI 工具列表")
    console.print()
    console.print(f"  3. [yellow]agents.default[/yellow]: [green]{primary_agent}[/green]")
    console.print("     默认使用的 AI 工具")
    console.print()
    console.print("  4. [yellow]checklist.threshold[/yellow]: [green]80[/green]")
    console.print("     检查清单通过阈值（满分 100 分）")
    console.print()

    # 构建AI工具列表显示
    agents_display = []
    for i, agent_key in enumerate(selected_agents):
        agent_name = AI_TOOLS_CONFIG[agent_key]["name"]
        agent_folder = AI_TOOLS_CONFIG[agent_key]["folder"]
        if i == 0:
            agents_display.append(f"  • {agent_name} ({agent_folder}) [green][主要][/green]")
        else:
            agents_display.append(f"  • {agent_name} ({agent_folder})")

    agents_text = "\n".join(agents_display)

    console.print(
        Panel(
            f"[cyan]项目名称:[/cyan] {project_name}\n"
            f"[cyan]AI工具:[/cyan]\n{agents_text}\n\n"
            f"[bold]下一步操作:[/bold]\n"
            f"  1. 运行 [cyan]cc-spec specify <变更名称>[/cyan] 创建新变更\n"
            f"  2. 编辑生成的 proposal.md 描述您的变更\n"
            f"  3. 运行 [cyan]cc-spec plan[/cyan] 生成执行计划",
            title="[bold green]快速开始[/bold green]",
            border_style="green",
        )
    )

    # 显示AI工具文件夹安全提示（类似spec-kit）
    if len(selected_agents) > 0:
        folders_list = [AI_TOOLS_CONFIG[key]["folder"] for key in selected_agents]
        folders_text = "、".join(folders_list)
        console.print()
        console.print(
            Panel(
                f"某些AI工具可能会在其文件夹中存储认证令牌、凭证或其他敏感信息。\n\n"
                f"建议将以下文件夹（或其中的敏感文件）添加到 [cyan].gitignore[/cyan]：\n"
                f"  {folders_text}\n\n"
                f"这样可以防止意外泄露凭证信息。",
                title="[yellow]安全提示[/yellow]",
                border_style="yellow",
                padding=(1, 2)
            )
        )
