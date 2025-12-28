"""init（Claude 内）命令模板：初始化项目 + 多级索引。

注意：v0.2.x 起项目结构理解以多级索引为准，不再依赖向量库检索。
"""

from .base import CommandTemplate, CommandTemplateContext


class InitTemplate(CommandTemplate):
    """在 Claude Code 内执行的 `/cc-spec init`：初始化项目 + 多级索引。"""

    def get_outline(self, ctx: CommandTemplateContext) -> str:
        return """初始化项目（bootstrap）并生成多级索引文件（PROJECT_INDEX / FOLDER_INDEX）。

**定位（重要）**：
- `cc-spec init`：生成/更新 Commands/Standards/模板等基础结构（可重复执行）
- `cc-spec init-index`：生成/更新项目多级索引（推荐默认 L1+L2）

**原则**：
- Claude Code 只负责编排：只用 Bash/Read/Glob/Grep/AskUserQuestion/TodoWrite
- 任何文件产出/修改交给 Codex（或 cc-spec CLI）
""".strip()

    def get_execution_steps(self, ctx: CommandTemplateContext) -> list[str]:
        return [
            """**前置检查：确认项目已 bootstrap（存在 `.cc-spec/`）**

- 用 Bash 检查当前项目是否存在 `.cc-spec/`
- 如果不存在：提示用户先在终端运行 `cc-spec init`（阶段 1），然后回到 Claude 再执行本命令
""",
            """**生成/更新多级索引（推荐 L1+L2）**

- 运行：
  ```bash
  cc-spec init-index --level l1 --level l2
  ```
""",
            """**一致性检查（可选）**

- 运行：
  ```bash
  cc-spec check-index
  ```
""",
        ]

    def get_validation_checklist(self, ctx: CommandTemplateContext) -> list[str]:
        return [
            "已生成 `PROJECT_INDEX.md`",
            "已生成各目录 `FOLDER_INDEX.md`（如启用 L2）",
            "已写入 `.cc-spec/index/status.json`",
            "扫描范围已由用户确认（必要时调整 `.cc-specignore`）",
        ]
