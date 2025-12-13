"""cc-spec v1.2 的 update 命令。

该模块提供 update 命令，用于管理配置、slash 命令与模板。

v1.2：新增在线下载模板并提供本地兜底。
"""

import asyncio
import shutil
from pathlib import Path

import typer
import yaml
from rich.console import Console

from cc_spec.core.config import Config, load_config
from cc_spec.utils.download import download_file, get_github_raw_url
from cc_spec.utils.files import find_project_root, get_cc_spec_dir

console = Console()

# 可用 AI 工具/agent 列表（v1.2：与 command_generator.py 同步）
AVAILABLE_AGENTS = [
    # 原始 9 个工具
    "claude",
    "cursor",
    "gemini",
    "copilot",
    "amazonq",
    "windsurf",
    "qwen",
    "codeium",
    "continue",
    # v1.2：新增 8 个工具
    "tabnine",
    "aider",
    "devin",
    "replit",
    "cody",
    "supermaven",
    "kilo",
    "auggie",
]

# 受管理区块标记
MANAGED_START = "<!-- CC-SPEC:START -->"
MANAGED_END = "<!-- CC-SPEC:END -->"

# v1.2：模板配置
TEMPLATE_REPO = "anthropics/cc-spec"  # TODO：更新为实际仓库
TEMPLATE_BRANCH = "main"
TEMPLATE_PATH_PREFIX = "templates"

# 需要下载/更新的模板文件
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
        help="更新目标：commands、subagent、agents、all",
    ),
    add_agent: list[str] = typer.Option(
        None,
        "--add-agent",
        "-a",
        help="添加 AI 工具（可多次使用）",
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
    """更新配置、slash 命令或模板。

    \b
    示例：
        cc-spec update                                   # 全量更新（commands、subagent）
        cc-spec update commands                          # 仅更新 slash 命令
        cc-spec update subagent                          # 仅更新 subagent 配置
        cc-spec update --add-agent gemini                # 添加 Gemini 支持
        cc-spec update --templates                       # 更新模板
        cc-spec update --add-agent gemini --add-agent amazonq  # 添加多个工具
    """
    project_root = find_project_root()
    if project_root is None:
        console.print(
            "[red]错误：[/red] 当前目录不是 cc-spec 项目，请先运行 'cc-spec init'。"
        )
        raise typer.Exit(1)

    cc_spec_root = get_cc_spec_dir(project_root)
    config_path = cc_spec_root / "config.yaml"

    try:
        config = load_config(config_path)
    except FileNotFoundError:
        console.print(
            "[red]错误：[/red] 未找到配置文件，请先运行 'cc-spec init'。"
        )
        raise typer.Exit(1)

    updated = False

    # 处理 --add-agent 选项
    if add_agent:
        for agent in add_agent:
            result = _add_agent(project_root, cc_spec_root, config, agent, force)
            if result:
                updated = True

    # 处理 --templates 选项
    if templates:
        _update_templates(cc_spec_root, force)
        updated = True

    # 根据 target 执行更新
    target_lower = (target or "all").lower()

    if target_lower in ("commands", "all"):
        _update_slash_commands(project_root, cc_spec_root, config, force)
        updated = True

    if target_lower in ("subagent", "all"):
        _update_subagent_config(cc_spec_root, config, force)
        updated = True

    if target_lower == "agents":
        _show_agents(config)
        return

    if updated:
        console.print("\n[green]√[/green] 更新完成。")
    else:
        console.print("[dim]Nothing to update.[/dim]")


def _add_agent(
    project_root: Path,
    cc_spec_root: Path,
    config: Config,
    agent: str,
    force: bool,
) -> bool:
    """向项目添加一个 AI 工具。

    参数：
        project_root：项目根目录
        cc_spec_root：.cc-spec 目录
        config：当前配置
        agent：要添加的 agent 名称
        force：是否强制覆盖

    返回：
        如果成功添加则返回 True，否则返回 False
    """
    agent_lower = agent.lower()

    if agent_lower not in AVAILABLE_AGENTS:
        console.print(
            f"[yellow]警告：[/yellow] '{agent}' 不是已识别的 agent。"
            f"可选：{', '.join(AVAILABLE_AGENTS)}"
        )
        if not force:
            return False

    # 检查是否已启用
    # 注意：需要扩展 Config 来跟踪已启用的 agents
    # 目前先只生成命令文件

    console.print(f"[cyan]正在添加 agent：[/cyan] {agent}")

    # 为该 agent 生成 slash 命令目录
    agent_dir = _get_agent_command_dir(project_root, agent_lower)
    if agent_dir:
        agent_dir.mkdir(parents=True, exist_ok=True)
        _generate_agent_commands(agent_dir, agent_lower)
        console.print(f"  [green]√[/green] 已创建 {agent_dir.relative_to(project_root)}")
        return True

    return False


def _get_agent_command_dir(project_root: Path, agent: str) -> Path | None:
    """获取某个 agent 的命令目录路径。

    参数：
        project_root：项目根目录
        agent：agent 名称

    返回：
        命令目录路径；未知 agent 则返回 None
    """
    agent_dirs = {
        "claude": project_root / ".claude" / "commands" / "speckit",
        "cursor": project_root / ".cursor" / "commands",
        "gemini": project_root / ".gemini" / "commands" / "speckit",
        "copilot": project_root / ".github" / "copilot" / "commands",
        "amazonq": project_root / ".amazonq" / "commands",
        "windsurf": project_root / ".windsurf" / "commands",
        "qwen": project_root / ".qwen" / "commands",
        "codeium": project_root / ".codeium" / "commands",
        "continue": project_root / ".continue" / "commands",
    }

    return agent_dirs.get(agent)


def _generate_agent_commands(agent_dir: Path, agent: str) -> None:
    """为某个 agent 生成 slash 命令文件。

    参数：
        agent_dir：命令文件生成目录
        agent：agent 名称
    """
    # 定义要生成的命令
    commands = [
        ("specify", "创建或编辑变更规格"),
        ("clarify", "审查任务并标记返工"),
        ("plan", "根据提案生成执行计划"),
        ("apply", "使用 SubAgent 执行任务"),
        ("checklist", "验收任务完成情况"),
        ("archive", "归档已完成的变更"),
        ("quick-delta", "快速模式：处理简单变更"),
        ("list", "列出变更、任务、规格或归档"),
        ("goto", "导航到变更或任务"),
        ("update", "更新配置与模板"),
    ]

    # 根据 agent 确定文件格式
    use_toml = agent in ("gemini",)

    for cmd_name, description in commands:
        if use_toml:
            _write_toml_command(agent_dir, cmd_name, description)
        else:
            _write_md_command(agent_dir, cmd_name, description)


def _write_md_command(cmd_dir: Path, cmd_name: str, description: str) -> None:
    """写入 Markdown 格式的 slash 命令文件。

    参数：
        cmd_dir：写入目录
        cmd_name：命令名称
        description：命令描述
    """
    file_path = cmd_dir / f"{cmd_name}.md"

    content = f"""---
description: {description}
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

{MANAGED_START}
## 工作流：cc-spec {cmd_name}

用户需求：$ARGUMENTS

**执行步骤**：
1. 解析用户参数
2. 运行 `cc-spec {cmd_name} $ARGUMENTS`
3. 展示结果并给出下一步建议

**命令参考**：
```
cc-spec {cmd_name} --help
```
{MANAGED_END}
"""

    # 仅在文件不存在或包含受管理区块时更新
    if file_path.exists():
        existing = file_path.read_text(encoding="utf-8")
        if MANAGED_START in existing:
            # 只更新受管理区块
            content = _update_managed_block(existing, content)
        else:
            # 不覆盖未包含受管理区块的用户文件
            return

    file_path.write_text(content, encoding="utf-8")


def _write_toml_command(cmd_dir: Path, cmd_name: str, description: str) -> None:
    """写入 TOML 格式的 slash 命令文件。

    参数：
        cmd_dir：写入目录
        cmd_name：命令名称
        description：命令描述
    """
    file_path = cmd_dir / f"{cmd_name}.toml"

    content = f'''description = "{description}"

[prompt]
content = """
{MANAGED_START}
## 工作流：cc-spec {cmd_name}

用户需求：{{{{args}}}}

**执行步骤**：
1. 解析用户参数
2. 运行 `cc-spec {cmd_name} {{{{args}}}}`
3. 展示结果并给出下一步建议
{MANAGED_END}
"""
'''

    # 仅在文件不存在或包含受管理区块时更新
    if file_path.exists():
        existing = file_path.read_text(encoding="utf-8")
        if MANAGED_START in existing:
            content = _update_managed_block(existing, content)
        else:
            return

    file_path.write_text(content, encoding="utf-8")


def _update_managed_block(existing: str, new_content: str) -> str:
    """仅更新现有内容中的受管理区块。

    参数：
        existing：现有文件内容
        new_content：包含受管理区块的新内容

    返回：
        保留用户区块后的更新内容
    """
    import re

    # 提取新的受管理区块
    new_match = re.search(
        rf"{re.escape(MANAGED_START)}.*?{re.escape(MANAGED_END)}",
        new_content,
        re.DOTALL,
    )
    if not new_match:
        return existing

    new_block = new_match.group(0)

    # 替换现有内容中的受管理区块
    updated = re.sub(
        rf"{re.escape(MANAGED_START)}.*?{re.escape(MANAGED_END)}",
        new_block,
        existing,
        flags=re.DOTALL,
    )

    return updated


def _update_templates(cc_spec_root: Path, force: bool) -> None:
    """将模板更新到最新版本。

    v1.2：支持在线下载并提供本地兜底。

    参数：
        cc_spec_root：.cc-spec 目录
        force：是否强制覆盖
    """
    templates_dir = cc_spec_root / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)

    console.print("[cyan]正在更新模板...[/cyan]")

    # 获取内置模板目录（本地兜底）
    bundled_templates_dir = Path(__file__).parent.parent / "templates"

    updated_count = 0
    skipped_count = 0

    for template_file in TEMPLATE_FILES:
        dest_path = templates_dir / template_file

        # 如果文件已存在且未设置 force，则按策略跳过覆盖
        if dest_path.exists() and not force:
            # 通过与内置模板对比判断文件是否被修改
            bundled_path = bundled_templates_dir / template_file
            if bundled_path.exists():
                bundled_content = bundled_path.read_text(encoding="utf-8")
                current_content = dest_path.read_text(encoding="utf-8")
                if bundled_content == current_content:
                    console.print(f"  [dim]- {template_file}（未变更）[/dim]")
                    skipped_count += 1
                    continue
                else:
                    console.print(
                        f"  [yellow]![/yellow] {template_file} 本地有修改，"
                        f"使用 --force 覆盖"
                    )
                    skipped_count += 1
                    continue
            else:
                skipped_count += 1
                continue

        # 优先尝试从远端下载
        downloaded = False
        try:
            url = get_github_raw_url(
                TEMPLATE_REPO,
                f"{TEMPLATE_PATH_PREFIX}/{template_file}",
                TEMPLATE_BRANCH,
            )
            downloaded = asyncio.run(download_file(url, dest_path))
        except Exception:
            # 下载失败，将使用本地兜底
            downloaded = False

        if downloaded:
            console.print(f"  [green]√[/green] {template_file}（已下载）")
            updated_count += 1
        else:
            # 使用内置模板作为兜底
            bundled_path = bundled_templates_dir / template_file
            if bundled_path.exists():
                shutil.copy2(bundled_path, dest_path)
                console.print(f"  [green]√[/green] {template_file}（来自内置模板）")
                updated_count += 1
            else:
                console.print(
                    f"  [red]×[/red] {template_file}（不可用）"
                )

    # 汇总
    if updated_count > 0:
        console.print(f"\n[green]√[/green] 已更新 {updated_count} 个模板")
    if skipped_count > 0:
        console.print(f"[dim]已跳过 {skipped_count} 个模板[/dim]")


def _update_slash_commands(
    project_root: Path,
    cc_spec_root: Path,
    config: Config,
    force: bool,
) -> None:
    """为已配置的 agents 更新 slash 命令。

    参数：
        project_root：项目根目录
        cc_spec_root：.cc-spec 目录
        config：当前配置
        force：是否强制覆盖
    """
    console.print("[cyan]正在更新 slash 命令...[/cyan]")

    # 获取当前 agent
    current_agent = config.agent

    # 为当前 agent 更新命令
    agent_dir = _get_agent_command_dir(project_root, current_agent)
    if agent_dir and agent_dir.exists():
        _generate_agent_commands(agent_dir, current_agent)
        console.print(
            f"  [green]√[/green] 已更新 {current_agent} 的命令"
        )
    elif agent_dir:
        agent_dir.mkdir(parents=True, exist_ok=True)
        _generate_agent_commands(agent_dir, current_agent)
        console.print(
            f"  [green]√[/green] 已创建 {current_agent} 的命令"
        )


def _update_subagent_config(
    cc_spec_root: Path,
    config: Config,
    force: bool,
) -> None:
    """用 v1.1 功能更新 subagent 配置。

    参数：
        cc_spec_root：.cc-spec 目录
        config：当前配置
        force：是否强制覆盖
    """
    console.print("[cyan]正在更新 subagent 配置...[/cyan]")

    config_path = cc_spec_root / "config.yaml"

    # 以原始 YAML 形式读取当前配置以保留结构
    try:
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        data = {}

    # 检查 v1.1 的 subagent 配置是否已存在
    subagent = data.get("subagent", {})

    updated = False

    # 若缺失则添加 common 配置
    if "common" not in subagent:
        subagent["common"] = {
            "model": "sonnet[1m]",
            "timeout": 300000,
            "permissionMode": "acceptEdits",
            "tools": "Read,Write,Edit,Glob,Grep,Bash",
        }
        updated = True
        console.print("  [green]+[/green] Added common configuration")

    # 若缺失则添加 profiles
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
                "model": "sonnet[1m]",
                "timeout": 180000,
                "tools": "Read,Glob,Grep,WebFetch,WebSearch",
                "description": "Exploration tasks: code research",
            },
        }
        updated = True
        console.print("  [green]+[/green] Added profile configurations")

    if updated:
        data["subagent"] = subagent
        data["version"] = "1.1"

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

        console.print("  [green]√[/green] 已将 config.yaml 更新到 v1.1")
    else:
        console.print("  [dim]Subagent configuration is already up to date[/dim]")


def _show_agents(config: Config) -> None:
    """展示可用与已配置的 agents。

    参数：
        config：当前配置
    """
    console.print("[bold]Available AI Tools:[/bold]")
    console.print()

    current = config.agent

    for agent in AVAILABLE_AGENTS:
        if agent == current:
            console.print(f"  [green]●[/green] {agent} [dim](current)[/dim]")
        else:
            console.print(f"  [dim]○[/dim] {agent}")

    console.print()
    console.print(
        "[dim]Add agents with: cc-spec update --add-agent <name>[/dim]"
    )
