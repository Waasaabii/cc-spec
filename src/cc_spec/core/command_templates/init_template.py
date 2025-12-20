"""init（Claude 内阶段 2）命令模板：构建/更新 RAG 知识库。"""

from .base import CommandTemplate, CommandTemplateContext


class InitTemplate(CommandTemplate):
    """在 Claude Code 内执行的 `/cc-spec init`：构建/更新 KB（向量库）。"""

    def get_outline(self, ctx: CommandTemplateContext) -> str:
        return """构建/更新项目级 RAG 知识库（ChromaDB 向量库 + workflow records）。

**定位（重要）**：
- 终端 `cc-spec init`：只做本地结构准备（不扫描、不调用 AI、不写向量库）
- Claude 内 `/cc-spec init`：执行扫描 → 切片 → 入库（需要 AI/向量化）

**原则**：
- Claude Code 只负责编排：只用 Bash/Read/Glob/Grep/AskUserQuestion/TodoWrite
- 任何文件产出/修改交给 Codex（或 cc-spec CLI）
- 先输出扫描报告供人确认，再执行入库
""".strip()

    def get_execution_steps(self, ctx: CommandTemplateContext) -> list[str]:
        return [
            """**前置检查：确认已执行过终端 `cc-spec init`**

- 用 Bash 检查当前项目是否存在 `.cc-spec/`
- 如果不存在：提示用户先在终端运行 `cc-spec init`（阶段 1），然后回到 Claude 再执行本命令
""",
            """**输出扫描报告（先看再入库）**

- 运行：
  ```bash
  cc-spec kb preview
  ```
- 将输出的 included/excluded 与 excluded reasons 摘要展示给用户
- 询问用户是否需要调整：
  - `.cc-specignore`（扫描范围）
  - `--max-bytes`（单文件大小上限）
  - `--reference-mode index|full`（reference 两级入库策略）
  - `--codex-batch-files/--codex-batch-chars`（Codex 切片批处理大小：更快但更易超时/格式不稳）
""",
            """**决定 init vs update**

- 用 Bash 检查 KB 状态：
  ```bash
  cc-spec kb status
  ```
- 规则：
  - 首次构建（manifest/vectordb 不存在）→ `cc-spec kb init`
  - 已存在 KB（manifest/vectordb 存在）→ `cc-spec kb update`
""",
            """**执行 KB 构建/更新（默认 reference-mode=index）**

- 首次构建：
  ```bash
  cc-spec kb init --reference-mode index
  ```
- 增量更新：
  ```bash
  cc-spec kb update --reference-mode index
  ```
- 如果用户明确要求，允许切换为 `--reference-mode full`
""",
            """**快速自检：检索是否可用**

- 运行一条 query（可用项目名/模块名替换）：
  ```bash
  cc-spec kb query "项目入口 关键模块" --n 5
  ```
- 若返回为空：
  - 检查 `.cc-specignore` 是否把主要目录排除了
  - 检查 `cc-spec kb init` 输出是否提示依赖缺失或 Codex/Embedding 失败
""",
            """**写入 workflow record（可追溯）**

- 运行：
  ```bash
  cc-spec kb record --step init --change "project" --notes "kb init/update completed"
  ```
""",
        ]

    def get_validation_checklist(self, ctx: CommandTemplateContext) -> list[str]:
        return [
            "已存在 `.cc-spec/vectordb/` 且 `cc-spec kb status` 显示文件齐全",
            "`cc-spec kb query ...` 能返回至少 1 条结果",
            "扫描范围已由用户确认（必要时调整 `.cc-specignore`）",
            "已写入 `kb record --step init`（可追溯）",
        ]
