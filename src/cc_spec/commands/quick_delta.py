"""cc-spec 的 quick-delta 命令实现。

该命令为不需要完整工作流的简单变更提供精简流程：生成 mini-proposal 并直接归档。

"""

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cc_spec.core.delta import DeltaOperation
from cc_spec.rag.incremental import detect_git_changes
from cc_spec.rag.workflow import try_write_mode_decision
from cc_spec.ui.banner import show_banner
from cc_spec.utils.files import ensure_dir, get_changes_dir

console = Console()

# 快速流程阈值（文件数 > 5 强制标准流程）
MAX_QUICK_DELTA_FILES = 5
QUICK_DELTA_SKIPPED_STEPS = ["clarify", "plan", "apply", "accept"]


# ============================================================================
# ============================================================================

@dataclass
class FileChange:
    """文件变更信息 。

    属性：
        path: 文件路径
        operation: 变更类型 (ADDED/MODIFIED/REMOVED/RENAMED)
        old_path: 原文件路径 (仅用于 RENAMED)
        additions: 新增行数 (可选)
        deletions: 删除行数 (可选)
    """

    path: str
    operation: DeltaOperation
    old_path: str | None = None
    additions: int = 0
    deletions: int = 0


@dataclass
class DiffStats:
    """Git diff 统计信息 。

    属性：
        changes: 文件变更列表
        total_additions: 总新增行数
        total_deletions: 总删除行数
    """

    changes: list[FileChange]
    total_additions: int = 0
    total_deletions: int = 0

    def count_by_operation(self, operation: DeltaOperation) -> int:
        """统计指定操作类型的文件数。"""
        return sum(1 for c in self.changes if c.operation == operation)


def _count_changed_files(project_root: Path) -> int | None:
    """统计当前工作区的变更文件数（含 untracked）。"""
    change_set = detect_git_changes(project_root)
    if change_set is None:
        return None
    paths = [*change_set.changed, *change_set.removed, *change_set.untracked]
    filtered: list[str] = []
    for path in paths:
        norm = path.replace("\\", "/")
        if norm == ".cc-spec" or norm.startswith(".cc-spec/"):
            continue
        filtered.append(path)
    return len(filtered)


def _build_quick_requirements(message: str) -> dict[str, object]:
    """构建 quick-delta 的最小需求集结构（写入 KB 记录）。"""
    text = (message or "").strip()
    return {
        "why": "",
        "what": text,
        "impact": "",
        "success_criteria": "",
        "missing_fields": ["why", "impact", "success_criteria"],
    }


def _parse_git_diff() -> DiffStats | None:
    """解析 git diff 获取文件变更列表 。

    优先解析 staged 变更，如果没有则解析最近一次 commit 的变更。

    返回：
        DiffStats 对象，包含变更列表和统计信息；如果失败则返回 None
    """
    # 首先尝试获取 staged 变更
    result = subprocess.run(
        ["git", "diff", "--staged", "--name-status"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0 and result.stdout.strip():
        changes = _parse_name_status(result.stdout)
        stats = _get_diff_stats("--staged")
    else:
        # 没有 staged 变更，尝试获取最近一次 commit 的变更
        result = subprocess.run(
            ["git", "diff", "HEAD~1", "--name-status"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0 or not result.stdout.strip():
            return None

        changes = _parse_name_status(result.stdout)
        stats = _get_diff_stats("HEAD~1")

    # 合并行数统计到 changes
    for change in changes:
        if change.path in stats:
            change.additions, change.deletions = stats[change.path]

    total_additions = sum(c.additions for c in changes)
    total_deletions = sum(c.deletions for c in changes)

    return DiffStats(
        changes=changes,
        total_additions=total_additions,
        total_deletions=total_deletions,
    )


def _parse_name_status(output: str) -> list[FileChange]:
    """解析 git diff --name-status 输出。

    参数：
        output: git diff --name-status 的输出

    返回：
        FileChange 列表
    """
    changes: list[FileChange] = []

    for line in output.strip().split("\n"):
        if not line:
            continue

        parts = line.split("\t")
        if len(parts) < 2:
            continue

        status = parts[0][0]  # A/M/D/R 等
        file_path = parts[1]

        # 确定变更类型
        if status == "A":
            operation = DeltaOperation.ADDED
        elif status == "M":
            operation = DeltaOperation.MODIFIED
        elif status == "D":
            operation = DeltaOperation.REMOVED
        elif status == "R":
            operation = DeltaOperation.RENAMED
        else:
            # 其他状态 (C=复制, U=未合并等) 视为 MODIFIED
            operation = DeltaOperation.MODIFIED

        # 处理 RENAMED 的情况：格式为 R<score>\told_path\tnew_path
        old_path = None
        if status == "R" and len(parts) >= 3:
            old_path = parts[1]
            file_path = parts[2]

        changes.append(FileChange(
            path=file_path,
            operation=operation,
            old_path=old_path,
        ))

    return changes


def _get_diff_stats(diff_target: str) -> dict[str, tuple[int, int]]:
    """获取每个文件的行数统计。

    参数：
        diff_target: diff 目标 (如 "--staged" 或 "HEAD~1")

    返回：
        文件路径到 (additions, deletions) 的映射
    """
    stats: dict[str, tuple[int, int]] = {}

    result = subprocess.run(
        ["git", "diff", diff_target, "--numstat"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return stats

    for line in result.stdout.strip().split("\n"):
        if not line:
            continue

        parts = line.split("\t")
        if len(parts) < 3:
            continue

        # numstat 格式: additions\tdeletions\tfilename
        try:
            # 二进制文件显示为 "-"
            additions = int(parts[0]) if parts[0] != "-" else 0
            deletions = int(parts[1]) if parts[1] != "-" else 0
            file_path = parts[2]
            stats[file_path] = (additions, deletions)
        except ValueError:
            continue

    return stats


# ============================================================================
# 主命令实现
# ============================================================================


def quick_delta_command(
    message: str = typer.Argument(..., help="变更描述（例如：修复登录页面样式问题）"),
) -> None:
    """超简单模式：一步生成变更记录。

    quick-delta 命令用于快速记录不需要完整工作流的简单变更：
    - 小改动（配置调整、样式修复等）
    - 紧急修复（hotfix）
    - 不需要设计规划的微小改进

    命令会：
    1. 自动生成带时间戳的变更名称
    2. 创建简化版的 mini-proposal.md
    3. 直接归档到 archive/ 目录
    4. 可选：记录关联的 Git commit 信息

    参数：
        message：变更描述，应该简洁明了地说明改动内容
    """
    # 显示启动 Banner
    show_banner(console)

    # 查找项目根目录
    project_root = Path.cwd()
    cc_spec_root = project_root / ".cc-spec"

    if not cc_spec_root.exists():
        console.print(
            "[red]错误：[/red] 当前目录不是 cc-spec 项目。请先运行 'cc-spec init'。",
            style="red",
        )
        raise typer.Exit(1)

    # 1. 生成变更名称（格式：quick-YYYYMMDD-HHMMSS-{slug}）
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d-%H%M%S")

    # 从 message 生成 slug（取前30个字符，转换为 kebab-case）
    slug = _generate_slug(message)
    change_name = f"quick-{timestamp}-{slug}"

    # quick-delta 预检：文件数阈值 > 5 强制标准流程
    file_count = _count_changed_files(project_root)
    if file_count is not None and file_count > MAX_QUICK_DELTA_FILES:
        try_write_mode_decision(
            project_root,
            change_name=change_name,
            mode="standard",
            reason=f"file_count>{MAX_QUICK_DELTA_FILES}",
            file_count=file_count,
            user_phrase=message,
        )
        console.print(
            f"[red]检测到 {file_count} 个文件变更，超过 quick-delta 阈值 "
            f"{MAX_QUICK_DELTA_FILES}。请改用标准流程（cc-spec specify）。[/red]"
        )
        raise typer.Exit(1)

    console.print(
        "[cyan]正在创建 quick-delta 记录...[/cyan]\n",
    )

    console.print(f"[dim]变更名称：[/dim] [bold]{change_name}[/bold]")

    # 2. 获取 Git 信息（如果可用）
    git_info = _get_git_info()

    if git_info:
        console.print(
            f"[dim]Git 提交：[/dim] {git_info['hash'][:7]} - {git_info['message']}"
        )
    else:
        console.print("[dim]Git 信息：[/dim] 不可用")

    diff_stats = _parse_git_diff()

    if diff_stats and diff_stats.changes:
        console.print(f"[dim]文件变更：[/dim] {len(diff_stats.changes)} 个文件")
        # 显示文件变更表格
        _display_file_changes_table(diff_stats)
    else:
        console.print("[dim]文件变更：[/dim] 未检测到暂存区变更")

    # 记录 quick-delta 模式判定与最小需求集（尽力写入 KB）
    extra_outputs: dict[str, object] = {}
    if git_info:
        extra_outputs["git"] = git_info
    if diff_stats:
        extra_outputs["diff"] = {
            "files": len(diff_stats.changes),
            "additions": diff_stats.total_additions,
            "deletions": diff_stats.total_deletions,
        }
    try_write_mode_decision(
        project_root,
        change_name=change_name,
        mode="quick",
        reason="quick-delta invoked",
        file_count=file_count,
        user_phrase=message,
        skipped_steps=QUICK_DELTA_SKIPPED_STEPS,
        requirements=_build_quick_requirements(message),
        extra_outputs=extra_outputs or None,
    )

    # 3. 创建归档目录结构
    changes_dir = get_changes_dir(project_root)
    archive_dir = changes_dir / "archive"
    ensure_dir(archive_dir)

    # 直接在 archive 下创建变更目录
    change_dir = archive_dir / change_name
    ensure_dir(change_dir)

    # 4. 创建 mini-proposal.md 
    mini_proposal_path = change_dir / "mini-proposal.md"
    mini_proposal_content = _generate_mini_proposal(
        message=message,
        change_name=change_name,
        timestamp=now,
        git_info=git_info,
        diff_stats=diff_stats,  
    )

    mini_proposal_path.write_text(mini_proposal_content, encoding="utf-8")
    console.print(
        "\n[green]✓[/green] 已创建 mini-proposal.md",
    )

    # 5. 显示成功信息
    console.print(
        "\n[bold green]quick-delta 记录创建成功！[/bold green]",
        style="green",
    )

    # 显示归档位置
    relative_path = change_dir.relative_to(project_root)
    console.print(
        f"\n[dim]已归档到：[/dim] [cyan]{relative_path}[/cyan]"
    )

    # 显示内容预览 
    preview_panel = Panel(
        _format_preview(message, git_info, diff_stats),
        title="[bold]quick-delta 摘要[/bold]",
        border_style="green",
        padding=(1, 2),
    )
    console.print("\n", preview_panel)

    # 提示后续操作
    console.print(
        "\n[dim]提示：该变更已被直接归档。复杂变更请改用 'cc-spec specify'。[/dim]"
    )


def _generate_slug(message: str, max_length: int = 30) -> str:
    """从 message 生成 URL 友好的 slug。

    参数：
        message：原始消息
        max_length：slug 最大长度

    返回：
        kebab-case 格式的 slug
    """
    # 转换为小写
    slug = message.lower()

    # 移除特殊字符，保留字母、数字、空格、中文字符
    slug = re.sub(r"[^\w\s\u4e00-\u9fff-]", "", slug)

    # 截取前 max_length 个字符
    slug = slug[:max_length]

    # 将空格替换为连字符
    slug = re.sub(r"\s+", "-", slug.strip())

    # 移除多余的连字符
    slug = re.sub(r"-+", "-", slug)

    # 移除首尾连字符
    slug = slug.strip("-")

    # 如果 slug 为空，使用默认值
    if not slug:
        slug = "change"

    return slug


def _get_git_info() -> dict[str, str] | None:
    """获取当前 Git commit 信息。

    返回：
        包含 hash、author、message 的字典，如果不在 Git 仓库则返回 None
    """
    try:
        # 检查是否在 Git 仓库中
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            check=True,
            capture_output=True,
            text=True,
        )

        # 获取最新 commit 的信息
        git_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        git_author = subprocess.run(
            ["git", "log", "-1", "--format=%an <%ae>"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        git_message = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        return {
            "hash": git_hash,
            "author": git_author,
            "message": git_message,
        }

    except (subprocess.CalledProcessError, FileNotFoundError):
        # Git 不可用或不在仓库中
        return None


def _display_file_changes_table(diff_stats: DiffStats) -> None:
    """显示文件变更表格 。

    参数：
        diff_stats：Git diff 统计信息
    """
    table = Table(title="文件变更", border_style="cyan", show_lines=False)
    table.add_column("类型", style="cyan", justify="center", width=10)
    table.add_column("文件", style="white")
    table.add_column("+/-", style="dim", justify="right", width=10)

    # 操作类型的显示样式
    op_styles = {
        DeltaOperation.ADDED: ("[green]ADDED[/green]", "+"),
        DeltaOperation.MODIFIED: ("[yellow]MODIFIED[/yellow]", "~"),
        DeltaOperation.REMOVED: ("[red]REMOVED[/red]", "-"),
        DeltaOperation.RENAMED: ("[blue]RENAMED[/blue]", "→"),
    }

    for change in diff_stats.changes:
        op_text, _ = op_styles.get(change.operation, ("[dim]?[/dim]", "?"))

        # 文件路径 (RENAMED 显示 old -> new)
        if change.operation == DeltaOperation.RENAMED and change.old_path:
            file_display = f"{change.old_path} → {change.path}"
        else:
            file_display = change.path

        # 行数统计
        if change.additions > 0 or change.deletions > 0:
            stats_display = f"+{change.additions} -{change.deletions}"
        else:
            stats_display = "-"

        table.add_row(op_text, file_display, stats_display)

    console.print()
    console.print(table)

    # 显示汇总统计
    added_count = diff_stats.count_by_operation(DeltaOperation.ADDED)
    modified_count = diff_stats.count_by_operation(DeltaOperation.MODIFIED)
    removed_count = diff_stats.count_by_operation(DeltaOperation.REMOVED)
    renamed_count = diff_stats.count_by_operation(DeltaOperation.RENAMED)

    summary_parts = []
    if added_count > 0:
        summary_parts.append(f"[green]+{added_count}[/green]")
    if modified_count > 0:
        summary_parts.append(f"[yellow]~{modified_count}[/yellow]")
    if removed_count > 0:
        summary_parts.append(f"[red]-{removed_count}[/red]")
    if renamed_count > 0:
        summary_parts.append(f"[blue]→{renamed_count}[/blue]")

    stats_text = (
        f"[dim]Total:[/dim] {' '.join(summary_parts)}, "
        f"+{diff_stats.total_additions} -{diff_stats.total_deletions} lines"
    )
    console.print(stats_text)


def _generate_mini_proposal(
    message: str,
    change_name: str,
    timestamp: datetime,
    git_info: dict[str, str] | None,
    diff_stats: DiffStats | None = None,  
) -> str:
    """生成 mini-proposal.md 内容。

    参数：
        message：变更描述
        change_name：变更名称
        timestamp：创建时间
        git_info：Git 信息（可选）
        diff_stats：

    返回：
        mini-proposal 的 markdown 内容
    """
    lines = [
        f"# 快速变更：{message}",
        "",
        "## 变更信息",
        "",
        f"- **变更名称**: {change_name}",
        f"- **创建时间**: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
        "- **变更类型**: quick-delta",
        f"- **描述**: {message}",
        "",
    ]

    # 添加 Git 信息（如果可用）
    if git_info:
        lines.extend([
            "## Git 信息",
            "",
            f"- **提交**: `{git_info['hash']}`",
            f"- **作者**: {git_info['author']}",
            f"- **消息**: {git_info['message']}",
            "",
        ])

    if diff_stats and diff_stats.changes:
        lines.extend([
            "## 文件变更",
            "",
            "| 文件 | 类型 | +/- |",
            "|------|------|-----|",
        ])

        op_names = {
            DeltaOperation.ADDED: "ADDED",
            DeltaOperation.MODIFIED: "MODIFIED",
            DeltaOperation.REMOVED: "REMOVED",
            DeltaOperation.RENAMED: "RENAMED",
        }

        for change in diff_stats.changes:
            op_name = op_names.get(change.operation, "?")
            if change.operation == DeltaOperation.RENAMED and change.old_path:
                file_display = f"{change.old_path} → {change.path}"
            else:
                file_display = change.path

            if change.additions > 0 or change.deletions > 0:
                stats_display = f"+{change.additions} -{change.deletions}"
            else:
                stats_display = "-"

            lines.append(f"| {file_display} | {op_name} | {stats_display} |")

        lines.append("")

        # 添加变更统计
        lines.extend([
            "## 变更统计",
            "",
        ])

        added_count = diff_stats.count_by_operation(DeltaOperation.ADDED)
        modified_count = diff_stats.count_by_operation(DeltaOperation.MODIFIED)
        removed_count = diff_stats.count_by_operation(DeltaOperation.REMOVED)
        renamed_count = diff_stats.count_by_operation(DeltaOperation.RENAMED)

        if added_count > 0:
            lines.append(f"- **ADDED**: {added_count} 文件")
        if modified_count > 0:
            lines.append(f"- **MODIFIED**: {modified_count} 文件")
        if removed_count > 0:
            lines.append(f"- **REMOVED**: {removed_count} 文件")
        if renamed_count > 0:
            lines.append(f"- **RENAMED**: {renamed_count} 文件")

        lines.append(
            f"- **总计**: {len(diff_stats.changes)} 文件, "
            f"+{diff_stats.total_additions} 行, -{diff_stats.total_deletions} 行"
        )
        lines.append("")

    # 添加备注
    lines.extend([
        "## 备注",
        "",
        "此变更通过 `cc-spec quick-delta` 命令快速创建，跳过了完整的规格流程。",
        "",
        "quick-delta 适用于：",
        "- 小改动（配置调整、样式修复等）",
        "- 紧急修复（hotfix）",
        "- 不需要设计规划的微小改进",
        "",
        "对于复杂变更，请使用完整的 cc-spec 工作流：",
        "1. `cc-spec specify` - 创建需求规格",
        "2. `cc-spec clarify` - 澄清需求",
        "3. `cc-spec plan` - 生成执行计划",
        "4. `cc-spec apply` - 执行任务",
        "5. `cc-spec accept` - 端到端验收",
        "6. `cc-spec archive` - 归档变更",
        "",
    ])

    return "\n".join(lines)


def _format_preview(
    message: str,
    git_info: dict[str, str] | None,
    diff_stats: DiffStats | None = None,  
) -> str:
    """格式化预览内容。

    参数：
        message：变更描述
        git_info：Git 信息（可选）
        diff_stats：

    返回：
        格式化的预览文本
    """
    lines = [
        f"[bold]描述：[/bold] {message}",
    ]

    if git_info:
        lines.append(
            f"[bold]Git 提交：[/bold] {git_info['hash'][:7]} - {git_info['message']}"
        )

    if diff_stats and diff_stats.changes:
        added_count = diff_stats.count_by_operation(DeltaOperation.ADDED)
        modified_count = diff_stats.count_by_operation(DeltaOperation.MODIFIED)
        removed_count = diff_stats.count_by_operation(DeltaOperation.REMOVED)
        renamed_count = diff_stats.count_by_operation(DeltaOperation.RENAMED)

        parts = []
        if added_count > 0:
            parts.append(f"[green]+{added_count}[/green]")
        if modified_count > 0:
            parts.append(f"[yellow]~{modified_count}[/yellow]")
        if removed_count > 0:
            parts.append(f"[red]-{removed_count}[/red]")
        if renamed_count > 0:
            parts.append(f"[blue]→{renamed_count}[/blue]")

        lines.append(
            f"[bold]变更文件：[/bold] {' '.join(parts)} "
            f"（+{diff_stats.total_additions} -{diff_stats.total_deletions} 行）"
        )

    return "\n".join(lines)
