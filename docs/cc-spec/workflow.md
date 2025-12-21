# 工作流详解

本文档说明 cc-spec 的**人类 8 步流程**与**系统 KB 流程**。原则：
- 8 步是给人类的组合指令
- 系统层必须将每一步转成 KB 记录/更新/审阅动作
- 评审主线以 KB records 为准，proposal/tasks 仅供人类阅读

## 工作流概览（人类 8 步）

```
init → kb init/update → specify → clarify → plan → apply → checklist → archive
```

## 人类流程 vs 系统 KB 流程

| 人类步骤 | 系统 KB 动作（必须执行） |
|---|---|
| init | 建立项目结构；若 KB 未建，标记待入库 |
| kb init/update | 生成/更新 code chunks 与 workflow records |
| specify | `kb record`：Why/What/Impact/Success Criteria |
| clarify | `kb record`：返工原因/歧义检测结果/需求补充摘要 |
| plan | `kb record`：任务拆解摘要、依赖、验收点 |
| apply | `kb record`：任务执行上下文与变更摘要；`kb update` 入库变更 |
| checklist | `kb record`：评分、未完成项、改进建议 |
| archive | `kb update/compact`：归档前确保 KB 最新 |

> 评审优先级：**KB records > proposal.md / tasks.yaml**。

---

## 阶段详解

### 1. Init - 项目初始化

**目的**：创建 cc-spec 项目结构。

```bash
cc-spec init
```

**产出**：
```
.cc-spec/
├── config.yaml
├── templates/
└── changes/
```

> 说明：init 只建立结构，不入库。

---

### 2. KB Init/Update - 构建/更新知识库（推荐）

**目的**：保证 KB 中有当前项目现状。

```bash
cc-spec kb init
# 或
cc-spec kb update
```

**系统动作**：写入 code chunks + workflow records，供后续评审与检索。

---

### 3. Specify - 需求规格

**目的**：定义需求与范围。

```bash
cc-spec specify add-user-auth
```

**产出**：`.cc-spec/changes/<change>/proposal.md`

**系统动作**：写入 KB record（Why/What/Impact/Success Criteria）。

---

### 4. Clarify - 返工 / 歧义检测

**目的**：标记返工或检测需求歧义（不做交互式问答回写）。

```bash
cc-spec clarify
cc-spec clarify <task-id>
cc-spec clarify --detect
```

**系统动作**：
- 返工：记录返工原因与任务变更
- 歧义检测：记录检测结果到 KB

---

### 5. Plan - 任务规划

**目的**：将需求拆解为可执行任务。

```bash
cc-spec plan
```

**产出**：`.cc-spec/changes/<change>/tasks.yaml`

**系统动作**：写入任务拆解摘要、依赖与验收点。

**tasks.yaml 示例（摘要）**：
```yaml
version: "1.6"
change: add-user-auth

tasks:
  01-SETUP:
    wave: 0
    name: 初始化与准备
    tokens: "30k"
    deps: []
    docs:
      - .cc-spec/changes/add-user-auth/proposal.md
    code: []
    checklist:
      - 分析需求
      - 设计方案
      - 实现功能
      - 编写测试
```

---

### 6. Apply - 任务执行

**目的**：按 Wave 并发执行任务。

```bash
cc-spec apply --max-concurrent 3
```

**系统动作**：
- 记录任务执行上下文到 KB
- 任务完成后执行 KB update

---

### 7. Checklist - 验收（强 Gate）

**目的**：评分验收，未通过必须回到 apply/clarify。

```bash
cc-spec checklist
```

**权重**：以 `config.yaml` 为准（默认 30/25/25/20）。

**规则**：
- 未通过：不得 archive；写入 KB record（失败项与建议） → 返回 apply/clarify
- 通过：可进入 archive

> checklist 是强 Gate，不允许绕过。

---

### 8. Archive - 归档

**目的**：合并 Delta specs 并归档。

```bash
cc-spec archive
```

**系统动作**：归档前确保 KB 最新（update/compact）。

---

## 快速需求通道（quick-delta）

```bash
cc-spec quick-delta "Fix typo in README"
```

**原则**：
- 快速仅是**文档简化**，系统流程必须完整
- 模式由模型根据 KB 评估决定：
  - **影响文件数 > 5 → 强制标准流程**
  - 用户可用中文明确表达“跳过/强制”，否则默认严格执行

**最小需求集**（必须写入 KB）：Why / What / Impact / Success Criteria

---

## 失败回路

```
checklist 未通过 → 分析失败原因 → clarify（补需求）或 apply（补实现）
```

- 需求不清晰：先 clarify
- 实现不完整：回 apply

---

## 状态转换图

```
SPECIFY → CLARIFY → PLAN → APPLY → CHECKLIST → ARCHIVE
   ↑        ↑                         │
   │        └───────────────┐         │
   └────────────────────────┴─────────┘
```

> 未通过 checklist 必须回到 clarify / apply。
