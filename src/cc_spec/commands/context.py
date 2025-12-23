"""cc-spec 的 context 命令实现。

输出当前阶段上下文信息，可通过 Hooks 自动注入到 AI 对话中。

"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from cc_spec.core.id_manager import IDManager
from cc_spec.core.state import (
    Stage,
    get_current_change,
    load_state,
)
from cc_spec.utils.files import find_project_root, get_cc_spec_dir

console = Console()

# 阶段描述
STAGE_DESCRIPTIONS = {
    Stage.SPECIFY: "需求提案阶段：CC↔用户确认需求",
    Stage.DETAIL: "详情讨论阶段：CC↔CX 自动讨论改动点",
    Stage.REVIEW: "用户审查阶段：用户审查 detail.md，澄清歧义",
    Stage.PLAN: "计划生成阶段：生成 tasks.yaml",
    Stage.APPLY: "任务执行阶段：并行或串行执行 task",
    Stage.ACCEPT: "端到端验收阶段：执行自动化检查，验证功能可用",
    Stage.ARCHIVE: "归档阶段：归档已完成的变更",
}

# 阶段职责
STAGE_RESPONSIBILITIES = {
    Stage.SPECIFY: """
- 与用户沟通，理解需求
- 编写 proposal.md
- 确认需求已明确
""",
    Stage.DETAIL: """
- 与 CX 讨论改动点（运行 cc-spec chat）
- 确认技术方案
- 编写 detail.md
""",
    Stage.REVIEW: """
- 引导用户审查 detail.md
- 澄清歧义
- 编写 review.md
""",
    Stage.PLAN: """
- 根据 review.md 生成 tasks.yaml
- 定义任务波次和依赖
- 确认执行计划
""",
    Stage.APPLY: """
- 编排任务执行（并行或串行）
- 监控 CX 执行进度
- 快速修复 CX 产生的 bug
- 确保功能端到端可用
""",
    Stage.ACCEPT: """
- 执行自动化检查（lint/test/build/type-check）
- 验证功能端到端可用
- 检查新增文件是否被正确集成
- 生成验收报告
""",
    Stage.ARCHIVE: """
- 确认 accept 阶段已完成
- 合并 delta 到主规格
- 移动变更到归档目录
""",
}

# CC 角色定义
CC_ROLE = """## cc-spec 工作流角色

你是 CC (Claude Code)，在 cc-spec 工作流中担任 **决策者和编排者**：
- 与用户沟通，理解需求
- 做最终决策，拍板方案
- 编写文档（proposal、review、acceptance 等）
- 快速修复 CX 产生的 bug
- 质量把控，确保功能端到端可用

CX (Codex) 是你的顾问，负责调研和批量执行。你可以通过 `cc-spec chat` 与 CX 协作。
"""

# CX 角色定义（AGENTS.md 用）
CX_ROLE = """## cc-spec 工作流角色

你是 CX (Codex)，在 cc-spec 工作流中担任 **顾问和执行者**：
- 调研分析，提供建议
- 批量代码生成和实现
- 执行测试和验证
- 大范围重复性任务

CC (Claude Code) 是决策者。你可以充分表达观点，但最终决策权归 CC。
不要限制自己的能力，充分分析和表达。
"""


def context_command(
    change_or_id: Optional[str] = typer.Argument(
        None,
        help="变更名称或 ID（例如 add-oauth 或 C-001）",
    ),
    show_stage: bool = typer.Option(
        False,
        "--stage",
        "-s",
        help="输出当前阶段信息",
    ),
    show_role: bool = typer.Option(
        False,
        "--role",
        "-r",
        help="输出角色定义（默认 CC）",
    ),
    cx_role: bool = typer.Option(
        False,
        "--cx",
        help="输出 CX 角色定义（与 --role 配合使用）",
    ),
    show_change: bool = typer.Option(
        False,
        "--change",
        "-c",
        help="输出当前变更信息",
    ),
    markdown: bool = typer.Option(
        False,
        "--md",
        help="以 Markdown 格式输出（适合注入到对话）",
    ),
) -> None:
    """输出当前阶段上下文信息。

    该命令可用于：
    1. 手动查看当前阶段和职责
    2. 通过 Hooks 自动注入到 AI 对话中
    3. 生成 CLAUDE.md 或 AGENTS.md 的角色定义

    示例：
        cc-spec context --stage          # 输出当前阶段
        cc-spec context --role           # 输出 CC 角色定义
        cc-spec context --role --cx      # 输出 CX 角色定义
        cc-spec context --change         # 输出当前变更信息
        cc-spec context --stage --md     # 以 Markdown 格式输出
    """
    # 如果没有指定任何选项，默认输出全部信息
    if not any([show_stage, show_role, show_change]):
        show_stage = True
        show_change = True

    # 查找项目根目录
    project_root = find_project_root()
    if project_root is None:
        console.print(
            "[red]错误：[/red] 当前目录不是 cc-spec 项目。",
            style="red",
        )
        raise typer.Exit(1)

    cc_spec_root = get_cc_spec_dir(project_root)
    id_manager = IDManager(cc_spec_root)

    # 确定变更
    change_name: str | None = None
    state = None

    if change_or_id:
        if change_or_id.startswith("C-"):
            entry = id_manager.get_change_entry(change_or_id)
            if entry:
                change_name = entry.name
        else:
            change_name = change_or_id

        if change_name:
            change_dir = cc_spec_root / "changes" / change_name
            state_path = change_dir / "status.yaml"
            if state_path.exists():
                state = load_state(state_path)
    else:
        state = get_current_change(cc_spec_root)

    # 输出角色定义
    if show_role:
        if cx_role:
            if markdown:
                console.print(CX_ROLE.strip())
            else:
                console.print("[bold cyan]CX (Codex) 角色定义：[/bold cyan]")
                console.print(CX_ROLE.strip())
        else:
            if markdown:
                console.print(CC_ROLE.strip())
            else:
                console.print("[bold cyan]CC (Claude Code) 角色定义：[/bold cyan]")
                console.print(CC_ROLE.strip())
        console.print()

    # 输出变更信息
    if show_change:
        if state:
            if markdown:
                console.print(f"**当前变更**: {state.change_name}")
                console.print(f"**创建时间**: {state.created_at}")
            else:
                console.print(f"[bold cyan]当前变更：[/bold cyan] {state.change_name}")
                console.print(f"[dim]创建时间：{state.created_at}[/dim]")
        else:
            if markdown:
                console.print("**当前变更**: 无")
            else:
                console.print("[yellow]当前无激活的变更[/yellow]")
        console.print()

    # 输出阶段信息
    if show_stage:
        if state:
            current_stage = state.current_stage
            description = STAGE_DESCRIPTIONS.get(current_stage, "未知阶段")
            responsibilities = STAGE_RESPONSIBILITIES.get(current_stage, "")

            if markdown:
                console.print(f"## 当前阶段：{current_stage.value}")
                console.print()
                console.print(f"**描述**: {description}")
                console.print()
                console.print("**职责**:")
                console.print(responsibilities.strip())
            else:
                console.print(f"[bold cyan]当前阶段：[/bold cyan] {current_stage.value}")
                console.print(f"[dim]{description}[/dim]")
                console.print()
                console.print("[bold]职责：[/bold]")
                console.print(responsibilities.strip())
        else:
            if markdown:
                console.print("## 当前阶段：无")
            else:
                console.print("[yellow]当前无激活的变更，无法确定阶段[/yellow]")
