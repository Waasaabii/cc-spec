"""apply 命令的模板实现。

该模板为 AI 工具提供执行 tasks.md 中任务的完整工作流指令。
包含 SubAgent 并行执行、锁机制、状态追踪等核心功能的详细说明。

模板长度：约 220 行
设计目标：提供清晰的 Wave 执行流程和技术检查步骤
"""

from .base import CommandTemplate, CommandTemplateContext


class ApplyTemplate(CommandTemplate):
    """apply 命令的模板类。

    核心功能：
    - SubAgent 并行执行 tasks.md 中的任务
    - Wave 内并行、Wave 间串行的执行流程
    - 锁机制防止并发冲突
    - 状态追踪和结果收集
    """

    def get_outline(self, ctx: CommandTemplateContext) -> str:
        """获取 apply 命令的大纲描述。

        返回：
            命令功能概述
        """
        return """使用 SubAgent 并行执行 tasks.md 中定义的所有任务。

任务按 Wave 分组执行：
- 同一 Wave 内的任务并行执行（受最大并发数限制）
- Wave 之间按顺序串行执行
- 支持锁机制防止多实例并发冲突
- 自动追踪执行状态并更新 tasks.md

该命令是 cc-spec 工作流的核心执行步骤，将设计方案转化为实际代码实现。
"""

    def get_execution_steps(self, ctx: CommandTemplateContext) -> list[str]:
        """获取 apply 命令的执行步骤。

        返回：
            详细的执行步骤列表
        """
        return [
            # 步骤 1: 前置检查
            """**前置检查与环境准备**

检查项：
- 验证当前目录是 cc-spec 项目（存在 .cc-spec/ 目录）
- 确认变更目录存在（通过参数或当前激活变更）
- 验证 tasks.md 文件存在且可读
- 加载 config.yaml 配置（用于 SubAgent Profile 和锁配置）
- 检查 plan.md 是否存在（提供技术栈上下文）

如果任何检查失败，输出清晰的错误提示并停止执行。
""",

            # 步骤 2: 解析 tasks.md
            """**解析 tasks.md 结构**

使用 parse_tasks_md() 解析文档：
- 提取所有 Wave 和 Task 定义
- 识别任务状态：🟦 待执行、🟨 进行中、🟩 已完成、🟥 失败、🟧 超时
- 检查任务依赖关系（dependencies 字段）
- 统计任务数量：total_waves、total_tasks、idle_tasks、completed_tasks

任务 ID 格式示例：W1-T1、W2-T3

验证要点：
- 确保至少有一个 Wave
- 确保有待执行的任务（idle_tasks > 0）
- 依赖任务必须存在且在前序 Wave 中
""",

            # 步骤 3: 显示任务摘要
            """**显示任务摘要表格**

生成任务摘要表：包含 Wave 编号、任务 ID、状态（○待执行/√已完成/×失败）、依赖。

输出统计：找到 X 个波次中的 Y 个任务，待执行 Z 个

特殊情况处理：
- 如果 idle_tasks == 0 且全部完成：提示运行 `cc-spec checklist` 验证，停止执行
- 如果 idle_tasks == 0 但有失败：提示使用 `--resume` 重试，停止执行
""",

            # 步骤 4: Resume 逻辑
            """**处理 Resume 模式（如果启用 --resume）**

查找第一个包含未完成任务的 Wave：
- 遍历所有 Wave，找到第一个有 IDLE/IN_PROGRESS/FAILED 状态任务的 Wave
- 跳过所有已完成的 Wave
- 输出："从波次 X 继续执行（跳过了 Y 个已完成波次）"

如果所有任务已完成，输出"没有需要恢复的任务"并停止。
""",

            # 步骤 5: 锁机制初始化
            """**锁机制初始化与处理（v1.3）**

锁机制用途：防止多个 AI 实例同时执行同一任务，避免文件冲突

锁文件位置：`.cc-spec/locks/<task-id>.lock`

初始化流程：
1. 创建 LockManager 实例
2. 读取 config.yaml 中的锁配置（enabled、timeout_minutes、cleanup_on_start）
3. 如果 cleanup_on_start=true，清理过期锁

处理特殊选项：
- **--force-unlock <task-id>**：强制释放指定任务的锁
- **--skip-locked**：遇到被锁任务时跳过，继续执行其他任务
- **--no-lock**：完全禁用锁机制（单人开发或调试用）
""",

            # 步骤 6: 执行准备
            """**执行准备与状态更新**

显示执行配置：准备执行 X 个任务，最大并发 10，单任务超时 300s，锁机制启用

更新 status.yaml：设置 current_stage=apply，status=in_progress，记录 started_at，waves_total

创建 SubAgentExecutor 实例，传入：
tasks_md_path、max_concurrent、timeout_ms、config（Profile支持）、cc_spec_root（锁支持）
""",

            # 步骤 7: Wave-by-Wave 执行
            """**Wave-by-Wave 并发执行（核心流程）**

**Wave 循环**：跳过已完成 Wave，获取 IDLE 任务，并发执行（最多10个），检查失败后停止

**任务执行（带锁）**：
1. 生成 agent_id（agent-<8位随机字符>）
2. 尝试获取锁：成功则执行，失败则跳过或报错
3. 构建提示词（任务描述、依赖、文档、入口、清单）
4. 启动 SubAgent
5. 释放锁（finally确保）

**并发控制**：asyncio.Semaphore，默认 10 个并发

**实时进度**：显示每个任务的状态和耗时
""",

            # 步骤 8: 结果更新
            """**更新 tasks.md 和状态文件**

**任务状态更新**：
- 成功任务：状态改为 🟩 已完成，记录完成时间和 SubAgent ID，勾选检查清单
- 失败任务：状态改为 🟥 失败，记录失败时间和错误信息

**status.yaml 更新**：
- 成功：status=completed, waves_completed=waves_total
- 失败：status=failed, waves_completed=失败前完成的 Wave 数
""",

            # 步骤 9: 技术检查
            """**执行技术检查（所有任务完成后）**

根据 plan.md 中的技术栈自动运行检查：

**Python 项目：**
- Lint 检查：`uv run ruff check src/`（警告不阻断）
- 类型检查：`uv run mypy src/cc_spec/`（警告不阻断）
- 测试执行：`uv run pytest`（失败阻断流程）

**其他技术栈示例：**
- TypeScript：`eslint src/`、`tsc --noEmit`、`npm test`
- Go：`go vet ./...`、`golangci-lint run`、`go test ./...`
- Rust：`cargo clippy`、`cargo fmt --check`、`cargo test`

检查结果处理：
- Lint/类型检查：记录警告但继续执行
- 测试失败：标记为执行失败，输出详细错误，阻断流程

如果技术检查失败：
- 输出错误详情和修复建议
- 不自动标记任务为失败（由开发者决定是否需要修复）
""",

            # 步骤 10: 结果报告
            """**生成执行结果摘要**

**成功场景**：输出摘要（波次数、任务数、成功率、总耗时），提示运行 `cc-spec checklist` 验收

**失败场景**：输出摘要和失败详情，
提示修复任务后运行 `cc-spec clarify <task-id>` 和 `cc-spec apply --resume`

**部分失败（skip-locked）**：列出跳过的被锁任务，建议等待或使用 --force-unlock
""",
        ]

    def get_validation_checklist(self, ctx: CommandTemplateContext) -> list[str]:
        """获取 apply 命令的验证检查清单。

        返回：
            验证项列表
        """
        return [
            "所有待执行任务已成功完成",
            "tasks.md 中的任务状态已正确更新（🟩 已完成）",
            "执行日志包含 completed_at 和 subagent_id",
            "status.yaml 的 apply 阶段状态为 completed",
            "waves_completed 等于 waves_total",
            "没有任务处于 IN_PROGRESS 状态（避免僵尸任务）",
            "所有锁文件已释放（.cc-spec/locks/ 为空或仅有过期锁）",
            "代码静态检查通过（或仅有警告）",
            "测试执行通过（如果存在测试任务）",
            "构建验证成功（如果需要构建）",
        ]

    def get_guidelines(self, ctx: CommandTemplateContext) -> str:
        """获取 apply 命令的执行指南。

        返回：
            指南文本
        """
        return """## 执行指南

### SubAgent 执行原理

**核心概念**：
- **SubAgent**：独立 AI 实例，负责单个任务
- **Wave**：任务分组，同 Wave 内并行，Wave 间串行
- **执行器**：管理生命周期、并发控制、状态同步

### 锁机制使用

**使用场景**：多人协作、分布式执行、避免文件冲突
**禁用场景**：单人开发、调试测试
**超时设置**：默认 30 分钟，可配置
**强制解锁**：`--force-unlock <task-id>`

### Profile 配置

```yaml
subagent:
  profiles:
    common:  # 标准任务，5 分钟超时
      timeout: 300000
    quick:   # 简单任务，1 分钟超时
      timeout: 60000
    deep:    # 复杂任务，15 分钟超时
      timeout: 900000
```

### 常见问题处理

1. **任务超时**：增加 `--timeout` 或使用 deep profile
2. **锁冲突**：等待完成或 `--force-unlock`
3. **依赖失败**：修复前置任务，`--resume` 继续
4. **文件冲突**：调整 Wave 分组，避免同时修改

### 性能优化

- **并发数**：CPU 密集型 = 核心数，I/O 密集型 = 2×核心数
- **Wave 分组**：独立任务同 Wave，依赖任务不同 Wave
- **Profile 选择**：简单用 quick，复杂用 deep

### 调试命令

```bash
cc-spec apply --dry-run              # 预览执行计划
cc-spec apply --resume               # 从失败点继续
cc-spec apply --force-unlock W1-T1   # 强制解锁任务
cc-spec apply --skip-locked          # 跳过被锁任务
cc-spec apply --no-lock              # 禁用锁（调试用）
```
"""
