"""quick-delta 命令模板。"""

from .base import CommandTemplate, CommandTemplateContext


class QuickDeltaTemplate(CommandTemplate):
    """quick-delta 命令模板实现。"""

    def get_outline(self, ctx: CommandTemplateContext) -> str:
        return """快速变更通道：一步创建并归档简单变更。

**定位**
- 仅用于小改动/紧急修复/微小优化
- 文档简化：自动生成 mini-proposal.md 并直接归档，作为最小追溯记录

**约束**
- 模式由模型基于影响面评估决定
- 影响文件数 > 5 强制标准流程（禁止 quick）
""".strip()

    def get_execution_steps(self, ctx: CommandTemplateContext) -> list[str]:
        return [
            """**解析用户输入与意图确认**

- 若 `$ARGUMENTS` 为空：AskUserQuestion 让用户提供变更描述
- 若包含“跳过/强制快速”等明确表达：记录原句到 mini-proposal.md（或在回复中明确），并保留作为模式判定依据
""",
            """**评估影响范围（强规则）**

- 统计变更文件数（示例）：
  ```bash
  git status --porcelain
  ```
- 若影响文件数 > 5：强制走标准流程（提示使用 `cc-spec specify`）
- 否则：允许 quick-delta
""",
            """**执行 quick-delta**

```bash
cc-spec quick-delta "$ARGUMENTS"
```
""",
            """**确认产物**

- 归档目录出现：`.cc-spec/changes/archive/quick-*/mini-proposal.md`
""",
        ]

    def get_validation_checklist(self, ctx: CommandTemplateContext) -> list[str]:
        return [
            "未超过 5 个文件变更，或已改走标准流程",
            "quick-delta 已生成 mini-proposal.md 并归档",
            "用户显式跳过/强制的原始语句已记录（如存在）",
        ]
