"""cc-spec 的 slash 命令生成模块（v0.1.5）。

v0.1.5 的定位是：
- Claude Code：只负责编排（不直接写文件）
- Codex CLI：执行层，由 cc-spec 在 apply 阶段调用

因此，命令生成器只需要为 Claude Code 生成 `/cc-spec:*` 命令文件。
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path

from cc_spec.core.command_templates import (
    ApplyTemplate,
    ChecklistTemplate,
    ClarifyTemplate,
    CommandTemplate,
    CommandTemplateContext,
    InitTemplate,
    PlanTemplate,
    QuickDeltaTemplate,
    SpecifyTemplate,
)

# 受管理区块标记
MANAGED_START = "<!-- CC-SPEC:START -->"
MANAGED_END = "<!-- CC-SPEC:END -->"

# 所有 cc-spec 命令（与 CLI 子命令对齐）
CC_SPEC_COMMANDS = [
    ("init", "初始化项目（生成 Commands/Standards/模板）"),
    ("init-index", "初始化项目多级索引（PROJECT_INDEX/FOLDER_INDEX）"),
    ("update-index", "增量更新项目多级索引"),
    ("check-index", "检查项目多级索引一致性"),
    ("specify", "创建或编辑变更规格"),
    ("clarify", "审查任务并标记返工"),
    ("plan", "根据提案生成执行计划"),
    ("apply", "使用 SubAgent 执行任务"),
    ("accept", "端到端验收：执行自动化检查，验证功能可用"),
    ("archive", "归档已完成的变更"),
    ("quick-delta", "快速记录简单变更"),
    ("list", "列出变更、任务、规格或归档"),
    ("goto", "跳转到指定变更或任务"),
    ("update", "更新配置与模板"),
]

# 命令到模板的映射（主要命令使用结构化模板）
COMMAND_TEMPLATES: dict[str, type[CommandTemplate]] = {
    "init": InitTemplate,
    "specify": SpecifyTemplate,
    "clarify": ClarifyTemplate,
    "plan": PlanTemplate,
    "apply": ApplyTemplate,
    "quick-delta": QuickDeltaTemplate,
}


class CommandGenerator(ABC):
    """命令生成器抽象基类。"""

    file_format: str = "markdown"
    folder: str = "commands"
    namespace: str = "cc-spec"
    file_name_prefix: str = ""
    allowed_tools: str = "Bash, Read, Glob, Grep, TodoWrite, AskUserQuestion"

    _current_project_root: Path | None = None

    @abstractmethod
    def get_command_dir(self, project_root: Path) -> Path:
        """获取命令文件应创建到的目录。"""
        ...

    def generate_command(
        self,
        cmd_name: str,
        description: str,
        project_root: Path,
    ) -> Path | None:
        """生成单个命令文件。"""
        self._current_project_root = project_root

        cmd_dir = self.get_command_dir(project_root)
        cmd_dir.mkdir(parents=True, exist_ok=True)

        if self.file_format == "toml":
            return self._write_toml_command(cmd_dir, cmd_name, description)
        return self._write_md_command(cmd_dir, cmd_name, description)

    def generate_all(self, project_root: Path) -> list[Path]:
        """生成全部命令文件。"""
        created: list[Path] = []
        for cmd_name, description in CC_SPEC_COMMANDS:
            path = self.generate_command(cmd_name, description, project_root)
            if path:
                created.append(path)
        return created

    def update_command(
        self,
        cmd_name: str,
        description: str,
        project_root: Path,
    ) -> Path | None:
        """更新已有命令文件，并保留用户自定义内容（受管理区块外）。"""
        self._current_project_root = project_root
        cmd_dir = self.get_command_dir(project_root)

        file_stem = self._get_command_file_stem(cmd_name)
        if self.file_format == "toml":
            file_path = cmd_dir / f"{file_stem}.toml"
        else:
            file_path = cmd_dir / f"{file_stem}.md"

        if not file_path.exists():
            return self.generate_command(cmd_name, description, project_root)

        existing = file_path.read_text(encoding="utf-8")
        if MANAGED_START not in existing:
            return None

        new_content = (
            self._get_toml_content(cmd_name, description)
            if self.file_format == "toml"
            else self._get_md_content(cmd_name, description)
        )
        updated = self._update_managed_block(existing, new_content)
        file_path.write_text(updated, encoding="utf-8")
        return file_path

    def _get_command_file_stem(self, cmd_name: str) -> str:
        return f"{self.file_name_prefix}{cmd_name}"

    def _write_md_command(
        self,
        cmd_dir: Path,
        cmd_name: str,
        description: str,
    ) -> Path:
        file_path = cmd_dir / f"{self._get_command_file_stem(cmd_name)}.md"
        file_path.write_text(self._get_md_content(cmd_name, description), encoding="utf-8")
        return file_path

    def _write_toml_command(
        self,
        cmd_dir: Path,
        cmd_name: str,
        description: str,
    ) -> Path:
        file_path = cmd_dir / f"{self._get_command_file_stem(cmd_name)}.toml"
        file_path.write_text(self._get_toml_content(cmd_name, description), encoding="utf-8")
        return file_path

    def _get_md_content(self, cmd_name: str, description: str) -> str:
        template_cls = COMMAND_TEMPLATES.get(cmd_name)
        if template_cls:
            ctx = CommandTemplateContext(
                command_name=cmd_name,
                namespace=self.namespace,
                project_root=self._current_project_root,
            )
            template = template_cls()
            template_content = template.render(ctx)
            body = f"{MANAGED_START}\n{template_content}\n{MANAGED_END}"
        else:
            body = (
                f"{MANAGED_START}\n"
                f"## 工作流: cc-spec {cmd_name}\n\n"
                "用户请求: $ARGUMENTS\n\n"
                "**执行步骤**:\n"
                "1. 解析用户参数\n"
                f"2. 运行 `cc-spec {cmd_name} $ARGUMENTS`\n"
                "3. 显示结果并建议下一步操作\n\n"
                "**命令参考**:\n"
                f"```\ncc-spec {cmd_name} --help\n```\n"
                f"{MANAGED_END}"
            )

        return f"""---
description: {description}
allowed-tools: {self.allowed_tools}
---

{body}
"""

    def _get_toml_content(self, cmd_name: str, description: str) -> str:
        template_cls = COMMAND_TEMPLATES.get(cmd_name)
        if template_cls:
            ctx = CommandTemplateContext(
                command_name=cmd_name,
                namespace=self.namespace,
                project_root=self._current_project_root,
            )
            template = template_cls()
            content = template.render(ctx)
        else:
            content = f"运行 `cc-spec {cmd_name} $ARGUMENTS`"

        return f"""description = "{description}"
allowed_tools = "{self.allowed_tools}"

# {MANAGED_START}
{content}
# {MANAGED_END}
"""

    def _update_managed_block(self, existing: str, new_content: str) -> str:
        new_match = re.search(
            rf"{re.escape(MANAGED_START)}.*?{re.escape(MANAGED_END)}",
            new_content,
            re.DOTALL,
        )
        if not new_match:
            return existing

        new_block = new_match.group(0)
        return re.sub(
            rf"{re.escape(MANAGED_START)}.*?{re.escape(MANAGED_END)}",
            new_block,
            existing,
            flags=re.DOTALL,
        )


class ClaudeCommandGenerator(CommandGenerator):
    """Claude Code 的命令生成器。"""

    file_format = "markdown"
    namespace = "cc-spec"
    allowed_tools = "Bash, Read, Glob, Grep, TodoWrite, AskUserQuestion"

    def get_command_dir(self, project_root: Path) -> Path:
        return project_root / ".claude" / "commands" / self.namespace


COMMAND_GENERATORS: dict[str, type[CommandGenerator]] = {
    "claude": ClaudeCommandGenerator,
}


def get_generator(agent: str) -> CommandGenerator | None:
    generator_cls = COMMAND_GENERATORS.get(agent.lower())
    if not generator_cls:
        return None
    return generator_cls()


def get_available_agents() -> list[str]:
    return list(COMMAND_GENERATORS.keys())
