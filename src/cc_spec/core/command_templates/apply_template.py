"""apply 命令模板（v0.1.5）。

目标：执行 tasks.yaml 中任务（Wave 并行），由 cc-spec 负责调度并调用 Codex。
原则：Claude 只编排，不直接 Write/Edit；上下文通过 KB/RAG。
"""

from .base import CommandTemplate, CommandTemplateContext


class ApplyTemplate(CommandTemplate):
    def get_outline(self, ctx: CommandTemplateContext) -> str:
        return """执行 `.cc-spec/changes/<change>/tasks.yaml` 中的任务。

**执行层**：
- `cc-spec apply` 会并发调度任务，并在每个任务中调用 Codex CLI
- 每个 Wave 结束后会增量更新 KB；全部成功后会 compact（events → snapshot）
""".strip()

    def get_execution_steps(self, ctx: CommandTemplateContext) -> list[str]:
        return [
            """**前置检查**

- 确认 tasks.yaml 存在
- 若 KB 未初始化：先运行 `/cc-spec init`（阶段 2 建库/更新库）
""",
            """**执行 apply**

```bash
cc-spec apply $ARGUMENTS
```

可选：
- `--resume`：重试 FAILED/IN_PROGRESS 任务
- `--dry-run`：只预览执行计划
""",
            """**失败处理（最小回路）**

- 若出现失败：
  - 先读失败任务输出（cc-spec apply 会打印）
  - 需要返工的任务用 `cc-spec clarify <task-id>` 标记
  - 重新执行：`cc-spec apply --resume`
""",
            """**执行后验证**

- 成功后执行验收：
  ```bash
  cc-spec accept $ARGUMENTS
  ```
""",
        ]

    def get_validation_checklist(self, ctx: CommandTemplateContext) -> list[str]:
        return [
            "tasks.yaml 中本次可执行任务已更新为 completed/failed",
            "失败时可用 `cc-spec apply --resume` 继续",
            "KB 已在 apply 过程中增量更新，并在成功后 compact",
            "下一步已指向 accept",
        ]

    def get_guidelines(self, ctx: CommandTemplateContext) -> str:
        return """- Claude 只编排：不要直接改代码/改 tasks.yaml
- 任务执行的上下文来自 KB；不要在 prompt 里塞大段文件全文
""".strip()
