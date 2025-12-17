"""specify 命令模板（v0.1.5）。

目标：在 Claude Code 中通过 Bash 调用 cc-spec + Codex 生成 proposal.md。
原则：Claude 只编排，不直接 Write/Edit；产出交给 Codex 或 cc-spec CLI。
"""

from .base import CommandTemplate, CommandTemplateContext


class SpecifyTemplate(CommandTemplate):
    def get_outline(self, ctx: CommandTemplateContext) -> str:
        return """创建或更新变更规格说明（proposal.md）。

**分工**：
- Claude Code：只编排（Bash/Read/Glob/Grep/AskUserQuestion/TodoWrite）
- Codex：产出文件（proposal.md）
- KB：作为后续上下文来源（RAG），并记录 workflow records

**产物**：
- `.cc-spec/changes/<change>/proposal.md`（给人看的规格）
""".strip()

    def get_execution_steps(self, ctx: CommandTemplateContext) -> list[str]:
        return [
            """**解析输入并确定变更**

- 若 `$ARGUMENTS` 为空：用 AskUserQuestion 让用户补充需求描述
- 若 `$ARGUMENTS` 为 `C-XXX`：按 ID 编辑模式定位已有 proposal
- 否则：将 `$ARGUMENTS` 作为变更名称（action-noun，小写+连字符）
""",
            """**创建/定位变更结构（cc-spec 负责骨架）**

```bash
cc-spec list changes
cc-spec specify $ARGUMENTS
```

记录输出的 change_id（C-XXX）与 proposal 路径。
""",
            """**用 Codex 生成 proposal.md（Claude 不写文件）**

用 Bash 调 Codex，只允许改 proposal.md：

```bash
codex exec --skip-git-repo-check --cd . --json - <<'EOF'
目标：只编辑 .cc-spec/changes/<change>/proposal.md
输入：用户需求 = $ARGUMENTS
要求：
- 写出 Why / What Changes / Impact / Success Criteria
- 每条需求可测试可验证，避免实现细节（语言/框架/API/表结构）
EOF
```
""",
            """**验证 proposal.md（Read/Glob/Grep）**

- Read proposal.md，确认章节齐全且非空
- 如不合格：再次用 Codex 只修 proposal.md（不要让 Claude 直接 Edit）
""",
            """**写入可追溯记录（推荐）**

```bash
cc-spec kb record --step specify --change "<change>" --notes "proposal generated"
```
""",
        ]

    def get_validation_checklist(self, ctx: CommandTemplateContext) -> list[str]:
        return [
            "proposal.md 已生成且包含 Why/What Changes/Impact",
            "Success Criteria 可验证（可量化或明确验收方式）",
            "未使用 Claude 的 Write/Edit 直接产出文件",
            "（可选）已写入 `kb record --step specify`",
        ]

    def get_guidelines(self, ctx: CommandTemplateContext) -> str:
        return """- Claude 只编排：Bash 调 cc-spec/codex；不要直接 Write/Edit
- 规格面向“人读”，描述 WHAT/WHY，避免 HOW
- 若需要上下文：优先依赖 KB（/cc-spec init 建库）而非读大量文档
""".strip()

