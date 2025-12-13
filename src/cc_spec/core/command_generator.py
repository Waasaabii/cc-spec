"""cc-spec v1.2 的 slash 命令生成模块。

该模块为不同 AI 工具生成对应的命令文件。

v1.2：新增 8 个命令生成器（总计 17+）。
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

# 受管理区块标记
MANAGED_START = "<!-- CC-SPEC:START -->"
MANAGED_END = "<!-- CC-SPEC:END -->"

# 所有 cc-spec 命令
CC_SPEC_COMMANDS = [
    ("specify", "Create or edit a change specification"),
    ("clarify", "Review tasks and mark for rework"),
    ("plan", "Generate execution plan from proposal"),
    ("apply", "Execute tasks using SubAgent"),
    ("checklist", "Validate task completion"),
    ("archive", "Archive a completed change"),
    ("quick-delta", "Quick mode for simple changes"),
    ("list", "List changes, tasks, specs or archives"),
    ("goto", "Navigate to a change or task"),
    ("update", "Update configuration and templates"),
]


class CommandGenerator(ABC):
    """命令生成器的抽象基类。

    不同 AI 工具的命令文件格式与目录位置各不相同。
    """

    file_format: str = "markdown"
    folder: str = "commands"
    namespace: str = "speckit"

    @abstractmethod
    def get_command_dir(self, project_root: Path) -> Path:
        """获取命令文件应创建到的目录。

        参数：
            project_root：项目根目录

        返回：
            命令目录路径
        """
        ...

    def generate_command(
        self,
        cmd_name: str,
        description: str,
        project_root: Path,
    ) -> Path | None:
        """生成单个命令文件。

        参数：
            cmd_name：命令名称
            description：命令描述
            project_root：项目根目录

        返回：
            创建的文件路径；失败则返回 None
        """
        cmd_dir = self.get_command_dir(project_root)
        cmd_dir.mkdir(parents=True, exist_ok=True)

        if self.file_format == "toml":
            return self._write_toml_command(cmd_dir, cmd_name, description)
        else:
            return self._write_md_command(cmd_dir, cmd_name, description)

    def generate_all(self, project_root: Path) -> list[Path]:
        """生成全部命令文件。

        参数：
            project_root：项目根目录

        返回：
            创建的文件路径列表
        """
        created = []
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
        """更新已有命令文件，并保留用户自定义内容。

        参数：
            cmd_name：命令名称
            description：命令描述
            project_root：项目根目录

        返回：
            更新后的文件路径；未更新则返回 None
        """
        cmd_dir = self.get_command_dir(project_root)

        if self.file_format == "toml":
            file_path = cmd_dir / f"{cmd_name}.toml"
        else:
            file_path = cmd_dir / f"{cmd_name}.md"

        if not file_path.exists():
            return self.generate_command(cmd_name, description, project_root)

        # 读取已有内容
        existing = file_path.read_text(encoding="utf-8")

        # 仅在包含受管理区块时才更新
        if MANAGED_START not in existing:
            return None

        # 生成新内容并更新受管理区块
        if self.file_format == "toml":
            new_content = self._get_toml_content(cmd_name, description)
        else:
            new_content = self._get_md_content(cmd_name, description)

        updated = self._update_managed_block(existing, new_content)
        file_path.write_text(updated, encoding="utf-8")
        return file_path

    def _write_md_command(
        self,
        cmd_dir: Path,
        cmd_name: str,
        description: str,
    ) -> Path:
        """写入 Markdown 格式的命令文件。"""
        file_path = cmd_dir / f"{cmd_name}.md"
        content = self._get_md_content(cmd_name, description)
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def _write_toml_command(
        self,
        cmd_dir: Path,
        cmd_name: str,
        description: str,
    ) -> Path:
        """写入 TOML 格式的命令文件。"""
        file_path = cmd_dir / f"{cmd_name}.toml"
        content = self._get_toml_content(cmd_name, description)
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def _get_md_content(self, cmd_name: str, description: str) -> str:
        """获取 Markdown 命令内容。"""
        return f"""---
description: {description}
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

{MANAGED_START}
## 工作流: cc-spec {cmd_name}

用户请求: $ARGUMENTS

**执行步骤**:
1. 解析用户参数
2. 运行 `cc-spec {cmd_name} $ARGUMENTS`
3. 显示结果并建议下一步操作

**命令参考**:
```
cc-spec {cmd_name} --help
```
{MANAGED_END}
"""

    def _get_toml_content(self, cmd_name: str, description: str) -> str:
        """获取 TOML 命令内容。"""
        return f'''description = "{description}"

[prompt]
content = """
{MANAGED_START}
## 工作流: cc-spec {cmd_name}

用户请求: {{{{args}}}}

**执行步骤**:
1. 解析用户参数
2. 运行 `cc-spec {cmd_name} {{{{args}}}}`
3. 显示结果并建议下一步操作
{MANAGED_END}
"""
'''

    def _update_managed_block(self, existing: str, new_content: str) -> str:
        """仅更新现有内容中的受管理区块。"""
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


class ClaudeCommandGenerator(CommandGenerator):
    """Claude Code 的命令生成器。"""

    file_format = "markdown"
    namespace = "speckit"

    def get_command_dir(self, project_root: Path) -> Path:
        return project_root / ".claude" / "commands" / self.namespace


class CursorCommandGenerator(CommandGenerator):
    """Cursor 的命令生成器。"""

    file_format = "markdown"
    namespace = ""

    def get_command_dir(self, project_root: Path) -> Path:
        return project_root / ".cursor" / "commands"


class GeminiCommandGenerator(CommandGenerator):
    """Gemini CLI 的命令生成器。"""

    file_format = "toml"
    namespace = "speckit"

    def get_command_dir(self, project_root: Path) -> Path:
        return project_root / ".gemini" / "commands" / self.namespace


class CopilotCommandGenerator(CommandGenerator):
    """GitHub Copilot 的命令生成器。"""

    file_format = "markdown"
    namespace = ""

    def get_command_dir(self, project_root: Path) -> Path:
        return project_root / ".github" / "copilot" / "commands"


class AmazonQCommandGenerator(CommandGenerator):
    """Amazon Q 的命令生成器。"""

    file_format = "markdown"
    namespace = "speckit"

    def get_command_dir(self, project_root: Path) -> Path:
        return project_root / ".amazonq" / "commands" / self.namespace


class WindsurfCommandGenerator(CommandGenerator):
    """Windsurf 的命令生成器。"""

    file_format = "markdown"
    namespace = ""

    def get_command_dir(self, project_root: Path) -> Path:
        return project_root / ".windsurf" / "commands"


class QwenCommandGenerator(CommandGenerator):
    """Qwen 的命令生成器。"""

    file_format = "markdown"
    namespace = "speckit"

    def get_command_dir(self, project_root: Path) -> Path:
        return project_root / ".qwen" / "commands" / self.namespace


class CodeiumCommandGenerator(CommandGenerator):
    """Codeium 的命令生成器。"""

    file_format = "markdown"
    namespace = ""

    def get_command_dir(self, project_root: Path) -> Path:
        return project_root / ".codeium" / "commands"


class ContinueCommandGenerator(CommandGenerator):
    """Continue.dev 的命令生成器。"""

    file_format = "markdown"
    namespace = ""

    def get_command_dir(self, project_root: Path) -> Path:
        return project_root / ".continue" / "commands"


# v1.2：新的命令生成器

class TabnineCommandGenerator(CommandGenerator):
    """Tabnine 的命令生成器。"""

    file_format = "markdown"
    namespace = "speckit"

    def get_command_dir(self, project_root: Path) -> Path:
        return project_root / ".tabnine" / "commands" / self.namespace


class AiderCommandGenerator(CommandGenerator):
    """Aider 的命令生成器。"""

    file_format = "markdown"
    namespace = ""

    def get_command_dir(self, project_root: Path) -> Path:
        return project_root / ".aider" / "commands"


class DevinCommandGenerator(CommandGenerator):
    """Devin 的命令生成器。"""

    file_format = "markdown"
    namespace = "speckit"

    def get_command_dir(self, project_root: Path) -> Path:
        return project_root / ".devin" / "commands" / self.namespace


class ReplitCommandGenerator(CommandGenerator):
    """Replit AI 的命令生成器。"""

    file_format = "markdown"
    namespace = ""

    def get_command_dir(self, project_root: Path) -> Path:
        return project_root / ".replit" / "commands"


class CodyCommandGenerator(CommandGenerator):
    """Sourcegraph Cody 的命令生成器。"""

    file_format = "markdown"
    namespace = "speckit"

    def get_command_dir(self, project_root: Path) -> Path:
        return project_root / ".cody" / "commands" / self.namespace


class SupermavenCommandGenerator(CommandGenerator):
    """Supermaven 的命令生成器。"""

    file_format = "markdown"
    namespace = ""

    def get_command_dir(self, project_root: Path) -> Path:
        return project_root / ".supermaven" / "commands"


class KiloCodeCommandGenerator(CommandGenerator):
    """Kilo Code 的命令生成器。"""

    file_format = "markdown"
    namespace = ""

    def get_command_dir(self, project_root: Path) -> Path:
        return project_root / ".kilo" / "commands"


class AuggieCommandGenerator(CommandGenerator):
    """Auggie 的命令生成器。"""

    file_format = "markdown"
    namespace = "speckit"

    def get_command_dir(self, project_root: Path) -> Path:
        return project_root / ".auggie" / "commands" / self.namespace


# 所有命令生成器的注册表
COMMAND_GENERATORS: dict[str, type[CommandGenerator]] = {
    # 原始 9 个生成器
    "claude": ClaudeCommandGenerator,
    "cursor": CursorCommandGenerator,
    "gemini": GeminiCommandGenerator,
    "copilot": CopilotCommandGenerator,
    "amazonq": AmazonQCommandGenerator,
    "windsurf": WindsurfCommandGenerator,
    "qwen": QwenCommandGenerator,
    "codeium": CodeiumCommandGenerator,
    "continue": ContinueCommandGenerator,
    # v1.2：新增 8 个生成器
    "tabnine": TabnineCommandGenerator,
    "aider": AiderCommandGenerator,
    "devin": DevinCommandGenerator,
    "replit": ReplitCommandGenerator,
    "cody": CodyCommandGenerator,
    "supermaven": SupermavenCommandGenerator,
    "kilo": KiloCodeCommandGenerator,
    "auggie": AuggieCommandGenerator,
}


def get_generator(agent: str) -> CommandGenerator | None:
    """获取指定 agent 的命令生成器。

    参数：
        agent：agent 名称（例如 "claude"、"cursor"）

    返回：
        CommandGenerator 实例；未找到则返回 None
    """
    generator_cls = COMMAND_GENERATORS.get(agent.lower())
    if generator_cls:
        return generator_cls()
    return None


def get_available_agents() -> list[str]:
    """获取可用的 agent 名称列表。

    返回：
        agent 名称列表
    """
    return list(COMMAND_GENERATORS.keys())
