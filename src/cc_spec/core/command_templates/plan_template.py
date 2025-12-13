"""plan 命令的模板实现。

该模板为 plan 命令提供完整的执行指令，包括：
- 九段大纲规划流程
- Gate/Wave 并行任务结构
- 技术硬要求提取
- tasks.yaml 结构化输出
"""

from .base import CommandTemplate, CommandTemplateContext


class PlanTemplate(CommandTemplate):
    """plan 命令的模板实现。

    该模板实现 Gate/Wave 结构化任务规划，将 proposal.md 转化为可执行的 tasks.yaml。

    核心功能：
    - 分析 proposal.md 并识别技术硬要求
    - 根据依赖关系将任务拆分为 Gate-0（串行）和 Wave-N（并行）
    - 生成结构化的 tasks.yaml（体积降低 80%）
    - 校验依赖关系并提供执行顺序
    """

    def get_outline(self, ctx: CommandTemplateContext) -> str:
        """获取 plan 命令的大纲描述。"""
        return """根据 proposal.md 生成结构化的执行计划（tasks.yaml）。

**核心目标：**
- 将变更需求拆解为可并行执行的任务组
- 创建 Gate-0（基础设施，串行执行）
- 创建 Wave-1~N（功能任务，并行执行）
- 为每个任务定义检查清单和预估上下文
- 生成 tasks.yaml（结构化，体积降低 80%）

**输入：** proposal.md（变更提案）
**输出：** tasks.yaml（结构化任务定义）

**任务结构：**
```yaml
meta:
  change_id: <change-name>
  change_name: <描述性名称>
  max_concurrent: 10
  total_tasks: N
  estimated_lines: ~XXXX

waves:
  - id: 0
    type: gate  # 串行执行
    tasks: [...]
  - id: 1
    type: wave  # 并行执行
    tasks: [...]
```"""

    def get_execution_steps(self, ctx: CommandTemplateContext) -> list[str]:
        """获取 plan 命令的执行步骤列表（九段大纲）。"""
        return [
            "读取并分析 proposal.md，理解变更的背景、目标、技术决策和成功标准",

            (
                "识别技术硬要求：从 .claude/CLAUDE.md（或 CLAUDE.md）、AGENTS.md、"
                "pyproject.toml 中提取测试命令、lint 工具、类型检查要求"
            ),

            (
                "分析依赖关系，确定任务顺序：识别哪些任务必须串行（基础设施）、"
                "哪些可以并行（功能实现）"
            ),

            (
                "创建 Gate-0（串行门控任务）：包含基础设施任务，如数据模型、核心接口、"
                "环境配置。这些任务必须在所有其他任务之前完成"
            ),

            (
                "创建 Wave-1~N（并行波次任务）：将功能任务按依赖关系分组到不同 Wave。"
                "同一 Wave 内任务互不依赖，可并发执行。跨 Wave 依赖只能指向更早 Wave"
            ),

            (
                "为每个任务生成预估上下文：根据涉及的文件、引用的代码、检查清单等估算代码行数"
                "（estimate 字段）。确保单个任务不超过 150K tokens"
            ),

            (
                "定义检查清单和验收标准：为每个任务创建 checklist 字段，"
                "列出 3-5 条可验证的完成标准。检查清单必须具体、可测试"
            ),

            (
                "生成 tasks.yaml：使用 YAML 格式输出，包含 meta 元信息、waves 波次定义、"
                "execution_order 执行顺序说明。确保结构清晰、易于解析"
            ),

            (
                "校验依赖关系并报告：检查是否有循环依赖、Wave 分组是否合理、任务 ID 是否唯一。"
                "生成执行顺序摘要（Gate-0: T01, T02 (串行) → Wave-1: T03, T04, T05 (并行)）"
            )
        ]

    def get_validation_checklist(self, ctx: CommandTemplateContext) -> list[str]:
        """获取 plan 命令完成后的验证检查清单。"""
        return [
            "tasks.yaml 已生成并包含完整的 meta 和 waves 字段",
            "Gate-0 包含基础设施任务（数据模型、核心接口、环境配置），标记为 type: gate",
            "Wave 分组正确：同 Wave 内任务互不依赖，跨 Wave 依赖只指向更早 Wave，无循环依赖",
            "每个任务有明确的检查清单（checklist 字段，3-5 条具体、可测试的标准）",
            "预估上下文在合理范围内（estimate 字段，单个任务 <150K tokens，约 <500 行代码）",
            "任务 ID 唯一且连续（T01, T02, T03...），deps 字段引用的任务 ID 均存在",
            "execution_order 字段准确反映 Gate/Wave 执行顺序",
            "tasks.yaml 体积相比传统 tasks.md 降低约 80%（通过结构化和 $templates/ 引用）"
        ]

    def get_guidelines(self, ctx: CommandTemplateContext) -> str:
        """获取 plan 命令的指南。"""
        return """## Gate/Wave 规划原则

### Gate-0（串行执行）

**定义：** 基础设施任务，必须先于所有功能任务完成。

**包含内容：**
- 数据模型定义（如 SQLAlchemy models、Pydantic schemas）
- 核心接口/抽象基类（如 CommandTemplate, AmbiguityDetector）
- 环境配置（如 config.yaml 结构、环境变量）
- 项目初始化脚本

**特点：**
- 串行执行（一个任务完成后才能开始下一个）
- 通常涉及核心架构和共享组件
- 其他任务通常会依赖 Gate-0 的产出

**示例：**
```yaml
- id: 0
  type: gate
  tasks:
    - id: T01
      name: TEMPLATE-BASE
      desc: 创建命令模板基础设施
      files:
        - src/cc_spec/core/command_templates/base.py
```

### Wave-N（并行执行）

**定义：** 可并发执行的任务组，同一 Wave 内任务互不依赖。

**分组原则：**
1. **Wave-1**：直接依赖 Gate-0 的核心功能（如各命令的模板实现）
2. **Wave-2**：依赖 Wave-1 的扩展功能（如检测器、高级模板）
3. **Wave-N**：依赖前序 Wave 的集成任务

**依赖规则：**
- 同一 Wave 内任务不能相互依赖
- 跨 Wave 依赖只能指向更早的 Wave（如 Wave-2 可依赖 Wave-1，但不能依赖 Wave-3）
- 避免循环依赖（A 依赖 B，B 依赖 A）

**示例：**
```yaml
- id: 1
  type: wave
  tasks:
    - id: T03
      name: SPECIFY-TEMPLATE
      deps: [T01]  # 依赖 Gate-0 的 T01
    - id: T04
      name: CLARIFY-TEMPLATE
      deps: [T01]  # 依赖 Gate-0 的 T01
    - id: T05
      name: PLAN-TEMPLATE
      deps: [T01]  # 依赖 Gate-0 的 T01
```

## 技术硬要求提取

从以下位置提取技术要求并在 tasks.yaml 中体现：

### 1. .claude/CLAUDE.md 或 CLAUDE.md

**关注内容：**
- 测试命令（如 `uv run pytest`、`pnpm test`）
- Lint 工具（如 `uv run ruff check`、`pnpm lint`）
- 类型检查（如 `uv run mypy`、`pnpm type-check`）
- 构建命令（如 `pnpm build`、`uv build`）

**应用方式：** 在每个任务的 checklist 中加入技术检查项（如"代码通过 ruff check"）

### 2. AGENTS.md

**关注内容：**
- 多 AI 工具支持要求
- 命令生成规范
- 工具特定的约束

### 3. pyproject.toml / package.json

**关注内容：**
- Python 版本要求（如 `requires-python = ">=3.10"`）
- 依赖包版本约束
- 开发工具配置（如 ruff、mypy 配置）

### 提取示例

```yaml
# 从 CLAUDE.md 提取
checklist:
  - 代码通过 ruff check 和 mypy 检查
  - 所有测试通过（uv run pytest）
  - 文档注释使用中文

# 从 pyproject.toml 提取
estimate: ~250  # 基于 Python 3.10+ 特性的代码量
```

## tasks.yaml 结构说明

### meta 字段

```yaml
meta:
  change_id: cc-spec-v0.1.4       # 变更 ID
  change_name: 四源融合 + 单一真相源  # 变更名称
  max_concurrent: 10               # 最大并发数（SubAgent）
  total_tasks: 17                  # 总任务数
  estimated_lines: ~3765           # 预估总代码行数
```

### waves 字段

```yaml
waves:
  - id: 0                    # Wave ID（0 表示 Gate-0）
    type: gate               # gate（串行）或 wave（并行）
    tasks:
      - id: T01              # 任务 ID（全局唯一）
        name: TEMPLATE-BASE  # 任务名称（简短描述）
        desc: 创建命令模板基础设施  # 详细描述
        deps: []             # 依赖的任务 ID 列表（Gate-0 通常为空）
        files:               # 涉及的文件路径
          - src/cc_spec/core/command_templates/base.py
        refs:                # 参考文件/代码（可选）
          - reference/test-project/...
        estimate: ~80        # 预估代码行数
        checklist:           # 验收标准（3-5 条）
          - CommandTemplateContext 包含必要字段
          - CommandTemplate 定义核心接口
          - render() 支持 markdown 和 toml 格式
```

### execution_order 字段（可选但推荐）

```yaml
execution_order:
  - "Gate-0: T01, T02 (串行)"
  - "Wave-1: T03, T04, T05 (并行)"
  - "Wave-2: T06, T07, T08 (并行)"
```

## 预估上下文计算

**目标：** 确保单个 SubAgent 任务的上下文不超过 150K tokens（约 500 行代码）

**计算要素：**
- 任务描述和检查清单：~200 tokens
- 引用文档（refs）：根据文件大小估算
- 涉及文件（files）：根据需要修改的代码量
- 变更摘要：~200-500 tokens

**estimate 字段指南：**
- 新增单个小模块：~80-150 行
- 实现完整功能/命令：~200-300 行
- 复杂集成/重构：~400-500 行（接近上限）

**示例：**
```yaml
- id: T05
  name: PLAN-TEMPLATE
  estimate: ~280  # 完整命令模板，九段大纲 + 指南
```

## 检查清单编写规范

**原则：** 具体、可测试、可验证

**好的检查清单：**
- ✅ "代码通过 ruff check 和 mypy 检查"（可执行命令验证）
- ✅ "包含 9 个完整执行步骤"（可数数验证）
- ✅ "tasks.yaml 体积 ≤ 原 tasks.md 的 20%"（可测量验证）

**差的检查清单：**
- ❌ "代码质量良好"（主观、无法验证）
- ❌ "功能基本完成"（模糊、无标准）
- ❌ "测试覆盖充分"（没有具体阈值）

**示例：**
```yaml
checklist:
  - 九段大纲完整（9 个 execution_steps）
  - Gate/Wave 规划格式正确（包含 type 和 deps 字段）
  - 技术硬要求说明清晰（从 CLAUDE.md 提取）
  - 无循环依赖（通过依赖图校验）
  - 单个任务上下文 <150K tokens（estimate 字段 <500）
```

## 常见陷阱与避免方法

### 陷阱 1：Wave 分组不当

**错误示例：**
```yaml
- id: 1
  type: wave
  tasks:
    - id: T03
      deps: [T02]
    - id: T04
      deps: [T03]  # ❌ T04 依赖 T03，但它们在同一 Wave
```

**正确做法：** 将 T04 移到 Wave-2

### 陷阱 2：循环依赖

**错误示例：**
```yaml
- id: T05
  deps: [T06]
- id: T06
  deps: [T05]  # ❌ T05 和 T06 相互依赖
```

**正确做法：** 重新分析依赖，拆分任务或调整顺序

### 陷阱 3：检查清单过于笼统

**错误示例：**
```yaml
checklist:
  - 功能正常  # ❌ 无法验证
```

**正确做法：**
```yaml
checklist:
  - tasks.yaml 包含 meta 和 waves 字段
  - 所有任务 ID 唯一且连续（T01-TNN）
  - deps 引用的任务 ID 均存在
```

### 陷阱 4：预估上下文过大

**错误示例：**
```yaml
- id: T10
  name: REFACTOR-ALL
  estimate: ~2000  # ❌ 远超 500 行上限
```

**正确做法：** 拆分为多个任务，每个 <500 行

## 公共模板引用（v0.1.4+）

**语法：** `$templates/<template-name>`

**用途：** 避免在 tasks.yaml 中重复定义检查清单

**示例：**
```yaml
# tasks.yaml
- id: T03
  name: SPECIFY-TEMPLATE
  checklist: $templates/feature-checklist  # 引用公共模板

# .cc-spec/templates/feature-checklist.md
- 代码通过 ruff check 和 mypy 检查
- 所有测试通过（uv run pytest）
- 文档注释完整
```

**注意：** 引用机制在 v0.1.4 中实现，当前版本可暂时使用完整 checklist 字段。"""
