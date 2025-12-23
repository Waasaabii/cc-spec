# workflow-v2-proposal.md

**变更名称**: workflow-v2
**目标版本**: cc-spec v0.2.1
**状态**: Draft
**创建时间**: 2025-12-23

---

## 1. 背景与目标

### 1.1 当前问题

当前 cc-spec 工作流存在三类关键问题：

1. **需求澄清不足**：缺少 CC↔CX 多轮讨论的强制步骤，用户审查与确认也未显式建模
2. **验收标准偏离业务目标**：以 checklist 评分为主，不能保证端到端功能可用
3. **返工路径松散**：失败后缺乏明确回流点和强制更新机制
4. **功能未衔接**：任务标记完成但功能未真正集成，用户需要自己验证

### 1.2 目标

将工作流升级为"8 步新流程"，实现：

- 明确 CC↔CX 多轮讨论与用户确认机制
- 验收基准升级为"端到端可用"
- 每个环节都验证功能是否衔接上
- 用户不需要额外验证，开箱即用

---

## 2. CC↔CX 协作原则

### 2.1 角色定义

| 角色 | 定位 | 职责范围 |
|------|------|----------|
| **CC (Claude Code)** | 编排者 + 精细化执行 | 决策、文档编写、bug 修复、与用户沟通、质量把控 |
| **CX (Codex)** | 顾问 + 粗活执行 | 调研分析、批量实现、代码生成、重复性任务 |

### 2.2 协作规则

1. **CC 是决策者**：对方案最终拍板并与用户沟通
2. **CX 是顾问**：提供分析、调研与实现建议，可充分表达观点
3. **能力不设限**：CC/CX 都可充分发挥各自能力，但最终决策权归 CC
4. **CX 不写文档**：文档编写、需求整理由 CC 负责
5. **快速修复归 CC**：CX 实现有 bug 时，能快速修复的由 CC 直接处理
6. **粗活归 CX**：批量代码生成、重复性实现、大范围调研由 CX 执行

### 2.3 分工示例

| 任务类型 | 执行者 | 原因 |
|----------|--------|------|
| 编写 proposal.md | CC | 文档工作 |
| 分析参考项目 | CX | 调研工作 |
| 批量创建组件文件 | CX | 粗活 |
| 修复类型错误 | CC | 快速修复 |
| 与用户讨论需求 | CC | 决策沟通 |
| 执行测试验证 | CX | 批量执行 |
| 最终方案确定 | CC | 决策 |

---

## 3. 新工作流 8 步

### 3.1 流程概览

```
用户需求
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 1. specify    │ CC↔用户确认需求，输出 proposal.md           │
├─────────────────────────────────────────────────────────────┤
│ 2. clarify    │ CC↔CX 自动讨论改动点（--detail 模式）       │
│    --detail   │ 用户不参与，输出 detail.md                  │
├─────────────────────────────────────────────────────────────┤
│ 3. clarify    │ 用户审查 detail.md，与 CC 讨论歧义          │
│               │ 输出 review.md                              │
├─────────────────────────────────────────────────────────────┤
│ 4. plan       │ 用户确认无歧义，生成确定版 tasks.yaml       │
│    --confirm  │                                             │
├─────────────────────────────────────────────────────────────┤
│ 5. apply      │ 并行或串行执行 task                         │
├─────────────────────────────────────────────────────────────┤
│ 6. accept     │ 端到端验收                                  │
│               │ 通过 → 步骤 8                               │
│               │ 不通过 → 步骤 7                             │
├─────────────────────────────────────────────────────────────┤
│ 7. 返工       │ 需求问题 → 回到步骤 2 或 3                  │
│               │ 实现问题 → 回到步骤 5                       │
│               │ 更新文档/task 后重新执行                    │
├─────────────────────────────────────────────────────────────┤
│ 8. archive    │ 验收通过，归档变更                          │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 命令映射

| 步骤 | 命令 | 用户参与 | 输出 |
|------|------|----------|------|
| 1 | `specify` | ✅ | proposal.md |
| 2 | `clarify --detail` | ❌ 自动 | detail.md |
| 3 | `clarify` | ✅ | review.md |
| 4 | `plan --confirm` | ✅ 确认 | tasks.yaml |
| 5 | `apply` | ❌ 自动 | 代码变更 |
| 6 | `accept` | ❌ 自动验证 | acceptance-report.md |
| 7 | 返工 | - | 更新相关文档 |
| 8 | `archive` | ❌ 自动 | 归档到 archive/ |

---

## 4. 状态模型

### 4.1 Stage 枚举

```python
class Stage(Enum):
    SPECIFY = "specify"
    DETAIL = "detail"      # clarify --detail 完成
    REVIEW = "review"      # clarify 完成
    PLAN = "plan"
    APPLY = "apply"
    ACCEPT = "accept"      # 新增，替代 checklist
    ARCHIVE = "archive"
```

### 4.2 status.yaml 结构

```yaml
change_id: "C-001"
name: "workflow-v2"
current_stage: "review"

stages:
  specify:
    status: completed
    completed_at: "2025-12-23T10:00:00Z"
  detail:
    status: completed
    completed_at: "2025-12-23T10:30:00Z"
  review:
    status: in_progress
    started_at: "2025-12-23T10:35:00Z"
  plan:
    status: pending
  apply:
    status: pending
  accept:
    status: pending

meta:
  rework:
    count: 0
    history: []
```

---

## 5. 命令变更清单

### 5.1 specify

**职责**：写提案 + CC↔用户确认需求

**变更**：
- 新增多轮对话确认机制
- 完成时需要用户明确确认

**输出**：`proposal.md`

### 5.2 clarify

**职责**：讨论 + 审查（合并 detail 和 review）

**模式**：

| 参数 | 行为 | 用户参与 |
|------|------|----------|
| `--detail` | CC↔CX 自动讨论改动点 | ❌ |
| 无参数 | 用户审查 + 歧义讨论 | ✅ |

**输出**：
- `--detail` → `detail.md`
- 无参数 → `review.md`

**流程约束**：
- `--detail` 必须在 `specify` 完成后执行
- 无参数模式必须在 `--detail` 完成后执行

### 5.3 plan

**职责**：用户确认 + 生成 tasks

**变更**：
- 新增 `--confirm` 参数，锁定需求
- 必须在 `review` 阶段完成后执行
- 生成的 tasks.yaml 包含验收标准字段

**输出**：`tasks.yaml`

### 5.4 apply

**职责**：执行 task

**变更**：
- 执行完成后指向 `accept`（不再指向 checklist）
- 支持 `--resume` 继续执行

**输出**：代码变更

### 5.5 accept（新增）

**职责**：端到端验收

**验收方式**：
1. 自动化检查（lint/test/build/type-check）
2. 功能验证（CC/CX 实际执行新功能，输出运行结果）
3. 链路检查（检查新增文件是否被 import/调用）

**输出**：
- `acceptance.md`（验收标准）
- `acceptance-report.md`（验收结果）

**流程**：
- 通过 → 进入 `archive`
- 不通过 → 触发返工机制

### 5.6 archive

**职责**：归档变更

**变更**：
- 必须在 `accept` 通过后执行
- 合并 delta 到主规格

### 5.7 checklist（废弃）

**状态**：废弃，保留为兼容别名

**行为**：
- 显示废弃警告
- 内部调用 `accept`

---

## 6. 文件结构

### 6.1 变更目录结构

```
.cc-spec/changes/<change>/
├── proposal.md           # specify 输出：需求提案
├── detail.md             # clarify --detail 输出：CC↔CX 讨论记录
├── review.md             # clarify 输出：用户审查记录
├── tasks.yaml            # plan 输出：任务定义
├── acceptance.md         # accept 输入：验收标准（可编辑）
├── acceptance-report.md  # accept 输出：验收结果
└── status.yaml           # 状态跟踪
```

### 6.2 新增文件模板

#### detail.md

```markdown
# Detail - CC↔CX 讨论记录

**变更**: <change-name>
**生成时间**: <timestamp>

## 讨论摘要

<CC↔CX 讨论的核心结论>

## 改动点确认

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| ... | ADDED/MODIFIED | ... |

## 技术决策

1. <决策1>
2. <决策2>

## 待用户确认

- [ ] <需要用户确认的点>
```

#### review.md

```markdown
# Review - 用户审查记录

**变更**: <change-name>
**审查时间**: <timestamp>

## 用户反馈

<用户的反馈和修改意见>

## 歧义澄清

| 原始描述 | 澄清后 |
|----------|--------|
| ... | ... |

## 最终确认

- [x] 需求已明确
- [x] 改动点已确认
- [x] 无遗留歧义
```

#### acceptance.md

```markdown
# Acceptance Criteria - 验收标准

**变更**: <change-name>

## 功能验收

### 核心路径
- [ ] <核心功能1可正常使用>
- [ ] <核心功能2可正常使用>

### 失败路径
- [ ] <错误场景有合理提示>

## 集成验收

- [ ] 新增文件已被正确 import
- [ ] 功能已集成到入口（UI/CLI/API）
- [ ] 不依赖 mock 可运行

## 自动化检查

- [ ] lint 通过
- [ ] test 通过
- [ ] build 通过
- [ ] type-check 通过
```

---

## 7. 验收标准定义

### 7.1 "端到端可用"定义

满足以下全部条件即判定"端到端可用"：

1. **关键用户路径可完整跑通**：核心功能的主路径（Happy Path）可用
2. **关键失败路径有合理反馈**：错误提示明确，可恢复
3. **跨组件链路完整**：UI → API → DB / CLI → Core 的真实联通
4. **真实环境下可运行**：不依赖 mock 才能工作
5. **功能已衔接**：新增代码被实际调用，不是孤立文件
6. **无 P0/P1 级阻断问题**
7. **必要的自动化检测通过**：test/build/lint（若存在）

### 7.2 验收检查方式

| 检查类型 | 执行者 | 方式 |
|----------|--------|------|
| 自动化检查 | CX | 运行 lint/test/build/type-check |
| 功能验证 | CC/CX | 实际执行新功能，输出运行结果或截图 |
| 链路检查 | CC | 检查 import/调用关系，确认功能衔接 |
| 手工验收 | 用户（可选） | 根据 acceptance.md 逐条确认 |

### 7.3 "功能衔接"检查要点

**不能只是创建文件就标记完成**，必须验证：

1. 新增组件是否被 import 到入口文件
2. 新增 API 是否被前端调用
3. 新增功能是否在 UI 可访问
4. 新增命令是否在 CLI 注册

---

## 8. 返工机制

### 8.1 返工触发条件

- `accept` 验收不通过
- 用户主动要求返工

### 8.2 返工目标判定

| 问题类型 | 返工目标 | 说明 |
|----------|----------|------|
| 需求理解错误 | `detail` | 重新 CC↔CX 讨论 |
| 需求有歧义 | `review` | 用户重新审查 |
| 实现不完整 | `apply` | 继续执行 task |
| 功能未衔接 | `apply` | 补充集成代码 |

### 8.3 返工记录

返工时更新 `status.yaml`：

```yaml
meta:
  rework:
    count: 1
    history:
      - timestamp: "2025-12-23T12:00:00Z"
        from_stage: "accept"
        to_stage: "apply"
        reason: "新增组件未集成到 UI"
```

---

## 9. 兼容性与迁移

### 9.1 命令兼容

| 旧命令 | 新行为 |
|--------|--------|
| `clarify` | 保留，新增 `--detail` 模式 |
| `checklist` | 废弃，调用 `accept` 并显示警告 |

### 9.2 历史变更迁移

- 旧 `clarify` 阶段 → 映射为 `review`
- 旧 `checklist` 阶段 → 映射为 `accept`
- 无 `detail` 阶段的变更 → 可跳过，直接进入 `review`

---

## 10. AI 运行时上下文设计

**核心理念**：cc-spec 的价值不只是工具本身，而是让运行时的 CC 和 CX 能够从上下文中理解自己在工作流中的角色和意义。

**设计原则**：优先使用 CC 和 CX 的原生上下文注入能力，而不是每次加载大文档。

### 10.1 原生上下文注入机制

#### CC (Claude Code) 原生能力

参考：[Claude Code Hooks](https://code.claude.com/docs/en/hooks)、[Claude Skills Deep Dive](https://leehanchung.github.io/blogs/2025/10/26/claude-skills-deep-dive/)

| 机制 | 路径 | 用途 |
|------|------|------|
| **CLAUDE.md** | `~/.claude/CLAUDE.md`（用户级）<br>`./CLAUDE.md`（项目级） | 静态项目上下文，层级合并 |
| **Skills** | `.claude/skills/<name>/SKILL.md` | 可复用能力包，按任务自动激活 |
| **Hooks** | `.claude/settings.json` | 动态上下文注入，提交时触发 |

#### CX (Codex CLI) 原生能力

参考：[AGENTS.md Guide](https://developers.openai.com/codex/guides/agents-md/)、[Codex Config](https://developers.openai.com/codex/local-config/)

| 机制 | 路径 | 用途 |
|------|------|------|
| **AGENTS.md** | `./AGENTS.md`（项目根）<br>`./subdir/AGENTS.md`（子目录） | 项目指令，从根到当前目录层级合并 |
| **AGENTS.override.md** | 同上 | 高优先级覆盖 |
| **config.toml** | `~/.codex/config.toml` | 全局配置 |

### 10.2 cc-spec 上下文注入策略

cc-spec 通过以下方式注入上下文，**不依赖大文档**：

#### 10.2.1 CC 上下文注入

**方式1：项目 CLAUDE.md**
```
./CLAUDE.md  ← cc-spec init 时生成/更新
```

cc-spec 在项目 CLAUDE.md 中追加角色定义：

```markdown
## cc-spec 工作流角色

你是 CC (Claude Code)，在 cc-spec 工作流中担任 **决策者和编排者**：
- 与用户沟通，理解需求
- 做最终决策，拍板方案
- 编写文档（proposal、review、acceptance 等）
- 快速修复 CX 产生的 bug
- 质量把控，确保功能端到端可用

CX (Codex) 是你的顾问，负责调研和批量执行。你可以通过 `cc-spec chat` 与 CX 协作。
```

**方式2：Skills 按阶段激活**
```
.claude/skills/
├── cc-spec-specify/SKILL.md    # specify 阶段技能
├── cc-spec-clarify/SKILL.md    # clarify 阶段技能
├── cc-spec-accept/SKILL.md     # accept 阶段技能
```

每个 SKILL.md 包含该阶段的职责和验收标准，按任务上下文自动激活。

**方式3：Hooks 动态注入**

通过 `UserPromptSubmit` hook，在用户提交时注入当前阶段上下文：

```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "command": "cc-spec context --stage"
    }]
  }
}
```

`cc-spec context --stage` 输出当前阶段信息，自动注入到对话中。

#### 10.2.2 CX 上下文注入

**方式1：项目 AGENTS.md**
```
./AGENTS.md  ← cc-spec init 时生成/更新
```

cc-spec 在项目 AGENTS.md 中追加角色定义：

```markdown
## cc-spec 工作流角色

你是 CX (Codex)，在 cc-spec 工作流中担任 **顾问和执行者**：
- 调研分析，提供建议
- 批量代码生成和实现
- 执行测试和验证
- 大范围重复性任务

CC (Claude Code) 是决策者。你可以充分表达观点，但最终决策权归 CC。
不要限制自己的能力，充分分析和表达。
```

**方式2：子目录 AGENTS.md 按阶段注入**
```
.cc-spec/changes/<change>/AGENTS.md  ← 动态生成，包含当前阶段信息
```

当 CX 在变更目录下工作时，自动读取阶段特定指令。

#### 10.2.3 阶段上下文动态生成

`cc-spec` 在每个阶段开始时，生成/更新阶段特定上下文：

| 阶段 | CC 上下文来源 | CX 上下文来源 |
|------|---------------|---------------|
| specify | `cc-spec-specify` skill | 不参与 |
| detail | `cc-spec-clarify` skill | `.cc-spec/changes/<change>/AGENTS.md` |
| review | `cc-spec-clarify` skill | 不参与 |
| plan | `cc-spec-plan` skill | 不参与 |
| apply | `cc-spec-apply` skill | `.cc-spec/changes/<change>/AGENTS.md` + task 上下文 |
| accept | `cc-spec-accept` skill | `.cc-spec/changes/<change>/AGENTS.md` |
| archive | `cc-spec-archive` skill | 不参与 |

### 10.3 运行时 AI 需要理解的问题

当 CC 或 CX 被调用时，必须能从上下文中理解：

| 问题 | 上下文来源 |
|------|------------|
| 我是谁？ | CLAUDE.md / AGENTS.md 中的角色定义 |
| 我在哪个阶段？ | Skill 激活 / 动态生成的 AGENTS.md |
| 我的职责是什么？ | 阶段特定 Skill / AGENTS.md |
| 我和谁协作？ | 阶段上下文中的协作说明 |
| 怎么知道做对了？ | 阶段验收标准（Skill 中定义） |
| 做完了下一步是什么？ | 阶段上下文中的流程指引 |

### 10.4 Skill 示例

#### cc-spec-clarify/SKILL.md

```markdown
---
name: cc-spec-clarify
description: cc-spec clarify 阶段，CC↔CX 讨论或用户审查
activation:
  - cc-spec clarify
  - 讨论改动点
  - 澄清歧义
---

## 当前阶段：Clarify

### --detail 模式（CC↔CX 自动讨论）

你需要与 CX 讨论以下内容：
1. proposal.md 中的需求如何实现？
2. 需要改动哪些文件？
3. 每个改动的技术方案是什么？
4. 有什么风险或疑问？

讨论完成后，整理结论到 detail.md。

### 默认模式（用户审查）

引导用户审查 detail.md，澄清歧义：
1. 展示 CC↔CX 讨论的结论
2. 询问用户是否有疑问
3. 记录用户反馈到 review.md

### 验收标准

- [ ] 改动点已明确
- [ ] 技术方案已确认
- [ ] 用户确认无歧义
```

### 10.5 CC↔CX 协作协议

当 CC 需要与 CX 协作时（如 `clarify --detail`），通过 `cc-spec chat` 进行：

**1. CC 发起讨论**（cc-spec chat 自动注入上下文）
```
CC → CX: 这是 proposal.md 的内容，请分析：
1. 需要改动哪些文件？
2. 每个改动的技术方案是什么？
3. 有什么风险或疑问？
```

**2. CX 回复分析**（AGENTS.md 已注入角色上下文）
```
CX → CC: 我的分析如下：
1. 改动文件列表：...
2. 技术方案：...
3. 风险和疑问：...
4. 我的建议：...
```

**3. CC 追问或确认**
```
CC → CX: 关于第2点，我有疑问...
或
CC → CX: 分析完整，我决定采用方案A，理由是...
```

**4. 达成共识**
```
CC: 整理讨论结果到 detail.md
```

### 10.6 每阶段验收标准

每个阶段完成时，都有明确的验收标准（定义在对应 Skill 中）：

| 阶段 | 验收标准 |
|------|----------|
| specify | 用户确认需求已明确，proposal.md 完整 |
| detail | CC↔CX 讨论完成，改动点已确认，detail.md 生成 |
| review | 用户确认无歧义，review.md 记录澄清结果 |
| plan | tasks.yaml 包含所有任务和验收标准 |
| apply | 所有 task 执行完成，代码已提交 |
| accept | 端到端验收通过，功能已衔接，acceptance-report.md 生成 |
| archive | 变更已归档，delta 已合并 |

### 10.7 边界情况处理

| 情况 | 处理方式 |
|------|----------|
| CX 卡住或超时 | CC 接管，直接执行或简化任务 |
| CC↔CX 无法达成共识 | CC 做最终决策，记录分歧原因 |
| 验收多次不通过 | 回退到 detail 重新讨论，或升级给用户决策 |
| 用户中途修改需求 | 回退到 specify，重新走流程 |

---

## 11. 成功判定

### 11.1 功能层面

- [ ] 新 workflow 8 步均有对应命令/状态
- [ ] `accept` 成为唯一归档前验收入口
- [ ] 验收标准为"端到端可用"，非"文件存在"
- [ ] 返工可明确回退到 detail/review/apply
- [ ] 与现有 cc-spec 旧流程兼容

### 11.2 AI 上下文层面

- [ ] CC 运行时能理解自己是决策者/编排者
- [ ] CX 运行时能理解自己是顾问/执行者
- [ ] CC 能正确发起与 CX 的协作讨论
- [ ] CX 能充分表达观点，不自我限制
- [ ] 每个阶段的验收标准能被 AI 理解和执行
- [ ] 边界情况有明确的处理机制

### 11.3 用户体验层面

- [ ] 用户不需要自己验证功能是否可用
- [ ] 用户能清晰看到当前进度和下一步
- [ ] 用户参与的环节（specify/review/plan）有明确的交互
- [ ] 用户不参与的环节能自动完成
