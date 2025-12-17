"""plan 命令模板。

该模板用于在 Claude Code 中编排 `cc-spec plan` 工作流，核心目标是产出可执行的
`.cc-spec/changes/<change>/tasks.yaml`（Gate/Wave 分解，九段大纲）。

定位（v0.1.5 兼容）：
- Claude Code：只负责编排（Bash/Read/Glob/Grep/AskUserQuestion/TodoWrite），不直接写文件。
- Codex：产出/修改文件（主要是 tasks.yaml，必要时补充最小文档）。
- KB：作为上下文与追溯来源（records/chunks），避免在 prompt 里塞大段全文。
"""

from .base import CommandTemplate, CommandTemplateContext


class PlanTemplate(CommandTemplate):
    def get_outline(self, ctx: CommandTemplateContext) -> str:
        return """
为当前变更生成**可执行的** `.cc-spec/changes/<change>/tasks.yaml`（Gate/Wave 结构）。

**核心目标**
- 读取 `proposal.md`，把“需求/约束/验收”转成可执行任务。
- 抽取**技术硬要求**（尤其是 `CLAUDE.md` / repo 规范 / CI 约束），避免后续返工。
- 用 **Gate-0**（串行）处理全局前置条件，再用 **Wave-1..N**（并行/并发）推进实现。
- 生成 `tasks.yaml`，包含 `meta`、`waves`、任务 `deps`、以及每个任务的 `checklist`。

**输入**
- `.cc-spec/changes/<change>/proposal.md`（proposal.md）

**输出**
- `.cc-spec/changes/<change>/tasks.yaml`（tasks.yaml）

**tasks.yaml 结构要求（摘要）**
```yaml
version: "1.0"
change: <change-name>

meta:
  change_id: C-XXX
  change_name: <human readable>
  max_concurrent: 4

waves:
  - id: 0
    type: gate   # type: gate
    tasks: [T01]
  - id: 1
    type: wave   # type: wave
    tasks: [T02, T03]

tasks:
  T01:
    name: <action-noun>
    status: idle
    deps: []
    docs: [proposal.md, CLAUDE.md]
    code: [src/...]
    estimate: ~200
    checklist:
      - 可验证的验收点（避免空话）
```

**分工（必须遵守）**
- Claude Code：编排（不 Write/Edit）
- Codex：生成/修改 `tasks.yaml`
""".strip()

    def get_execution_steps(self, ctx: CommandTemplateContext) -> list[str]:
        return [
            """**1) 读取输入：proposal.md**

- 打开并通读：
  - `.cc-spec/changes/<change>/proposal.md`（proposal.md）
- 把内容按：Why / What Changes / Impact / Success Criteria 做摘要笔记（不写文件也行）。
""",
            """**2) 识别技术硬要求（技术硬要求）**

- 必须读取并提取约束：
  - `CLAUDE.md`（代码规范/流程约束/命令约束）
  - `pyproject.toml`（Python 版本、依赖、lint/test 工具）
  - CI/脚本（如 `script/`、GitHub Actions 等，若存在）
- 输出：一份“硬要求清单”，用于驱动任务拆分与检查清单编写。
""",
            """**3) 分析依赖关系（依赖关系）**

- 识别下列依赖并记录到 tasks.yaml：
  - 任务间依赖：先基础设施/接口，再功能实现，再收尾（测试/文档/迁移）
  - 外部依赖：新包/新服务/向量库/本地进程（若有）
  - 目录依赖：哪些模块必须先改，哪些可以并行
- 原则：同一个 Wave 内尽量无 deps；有 deps 的拆到后续 Wave。
""",
            """**4) 建立 Gate-0（串行）**

- 创建 **Gate-0**：必须**串行**完成、且能阻断后续实现的前置任务，例如：
  - 建新目录/配置骨架
  - 定义核心数据结构/协议
  - 跑通最小示例或 smoke test
- Gate-0 的 `checklist` 必须可验证（命令/文件/行为）。
""",
            """**5) 划分 Wave-1..N（并行/并发）**

- 将实现任务拆到 **Wave-1** 起的多个 Wave：
  - Wave 内任务尽量**并行/并发**执行（无互相 deps）
  - 每个 Wave 完成后应能给出一个“可验证里程碑”
- 如果任务很多：优先拆“按模块/按垂直切片”的 Wave，而不是按文件类型拆。
""",
            """**6) 预估上下文与工作量（预估上下文 / estimate）**

- 给每个任务填写 `estimate`（大致行数/复杂度/风险点）与 `tokens`（可选）。
- 标记需要额外上下文的任务（例如需要扫描 reference/、需要读取外部协议等）。
- 原则：estimate 用于并发度与分 Wave 的权衡，不追求精确。
""",
            """**7) 为每个任务编写检查清单（检查清单 / checklist）**

- 每个任务必须有 `checklist`，且每一条都满足：
  - 可验证：能通过测试/命令/文件存在/行为变化来确认
  - 颗粒度适中：避免“完成 XXX”这种空话
  - 覆盖：功能 + 质量（lint/类型）+ 测试 + 文档（如需要）
""",
            """**8) 生成/更新 tasks.yaml（由 Codex 产出）**

- Claude 不写文件；用 Bash 调用 Codex，仅允许改：
  - `.cc-spec/changes/<change>/tasks.yaml`（tasks.yaml）

```bash
codex exec --skip-git-repo-check --cd . --json - <<'EOF'
目标：只编辑 .cc-spec/changes/<change>/tasks.yaml
输入：读取 proposal.md + CLAUDE.md 等硬要求
要求：
- 必须包含 meta / waves / tasks 三段，并按 Gate-0 + Wave-1..N 组织
- waves: Gate-0 用 type: gate；后续用 type: wave
- deps 不允许循环；同 Wave 内尽量无 deps
- 每个任务包含 docs/code/checklist/estimate（尽量短但可执行）
EOF
```
""",
            """**9) 校验计划可执行性（校验 / 依赖）**

- 本地校验 tasks.yaml：
  ```bash
  cc-spec apply $ARGUMENTS --dry-run
  ```
- 校验点：
  - Gate/Wave 分组是否符合 deps
  - deps 是否存在、是否循环
  - 关键任务是否覆盖了技术硬要求
- （可选）写入追溯 record：
  ```bash
  cc-spec kb record --step plan --change "<change>" --notes "tasks.yaml generated"
  ```
""",
        ]

    def get_validation_checklist(self, ctx: CommandTemplateContext) -> list[str]:
        return [
            "tasks.yaml 已生成，且 `cc-spec apply --dry-run` 可解析",
            "Gate-0 已存在且符合串行前置（type: gate）",
            "Wave-1..N 分组合理，可并行/并发推进（type: wave）",
            "依赖关系 deps 无循环且只指向已存在任务",
            "每个任务都有可验证的检查清单 checklist 与 estimate",
            "Claude 未直接 Write/Edit 任何文件（文件产出来自 Codex/CLI）",
        ]

    def get_guidelines(self, ctx: CommandTemplateContext) -> str:
        return """
### Gate/Wave 规划原则（Gate/Wave）

**Gate-0（串行）**
- 只放“阻断项”：不做完就无法安全开始并行实现的内容。
- 常见内容：关键数据结构/协议、项目骨架、最小可运行路径、关键配置。
- Gate-0 必须标注为 `type: gate`，并放在 Wave 0；严格串行。

**Wave-1..N（并行/并发）**
- Wave 是并行执行单元：同一个 Wave 内尽量不互相依赖（deps）。
- 若存在明确依赖关系：拆到后续 Wave，而不是靠同 Wave 内排序“碰运气”。
- 每个 Wave 应该有一个“可验证里程碑”（例如某条命令可跑、某个 API 可用）。

**依赖（deps）**
- deps 只能指向已定义的任务 ID（如 T01、T02）。
- 不允许循环依赖；避免长链依赖（会拖慢并行效率）。
- 依赖关系要反映真实技术顺序：先基础设施/契约，再功能实现，再测试与收尾。

---

### 技术硬要求提取（技术硬要求）

计划阶段必须抽取“硬约束”，否则是高返工风险：
- `CLAUDE.md`：流程/编排限制、质量门槛、工具使用边界。
- `pyproject.toml` / `uv.lock`：Python 版本、依赖、测试框架、lint 工具（如 ruff）。
- 现有脚本/CI：测试命令、格式化、静态检查要求。

**至少写进 checklist 的硬项（示例）**
- 运行测试：`pytest`（或项目约定的 test 命令）
- 运行 lint：`ruff`（或项目约定的 lint 命令）
- 若有类型检查：mypy/pyright（按项目约定）

---

### tasks.yaml 结构规范（tasks.yaml）

tasks.yaml 必须“可读 + 可执行 + 可追溯”，建议包含：

**meta**
- `change_id` / `change_name`：用于人读与追踪
- `max_concurrent`：apply 并发度
- 其他：规模预估、默认模型等（可选）

**waves**
- 每个 wave 至少包含：`id`、`type`、`tasks`
- `type: gate` 只用于 Gate-0；`type: wave` 用于并行 Wave

**tasks**
- 任务字段建议包含：`name`、`status`、`deps`、`docs`、`code`、`estimate`、`checklist`
- 字段示例（不是固定 schema）：
  - `id:`（隐含为键名，如 T01）
  - `name:`（action-noun）
  - `desc:`（可选，1-2 句）

---

### 预估上下文（预估上下文 / estimate）

- `estimate` 不是精确工时，是复杂度/风险标签：用于分 Wave 与控并发。
- 哪些任务需要“额外上下文”（大量 repo 扫描、参考资料、协议）要提前标注。
- 如果引入向量库/RAG：把“入库/更新/compact”作为可执行任务或 checklist 条目。

---

### 检查清单编写规范（检查清单 / checklist）

- checklist 写“验收点”，不是写“要做什么”。
- 优先使用可运行命令/可观察行为作为验收（测试、lint、输出文件、CLI 返回）。
- 覆盖四类：功能 / 质量 / 测试 / 文档（按项目需要取舍）。

---

### 常见陷阱（避免/错误/陷阱）

- **陷阱：** 把大段文档塞进 tasks.yaml → 应把上下文放到 KB，tasks.yaml 只保留索引与验收点。
- **错误：** Gate-0 放了太多实现细节 → Gate-0 只做阻断项，其余放 Wave。
- **错误：** deps 写“想当然”导致循环 → 生成后必须 `cc-spec apply --dry-run` 校验。
- **避免：** 只写“完成 XXX”这种空 checklist → 改为可验证的命令/行为验收。
""".strip()
