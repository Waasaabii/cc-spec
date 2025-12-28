# 工作流详解

本文档说明 cc-spec 的**人类流程**与**系统产物**。原则：
- “流程步骤”是给人类的组合指令
- 系统会生成/维护**项目索引**与**工作流状态**，保证后续步骤可重复、可追踪

## 工作流概览（推荐）

```
init → init-index/update-index → specify → clarify → plan → apply → accept → archive
```

---

## 阶段详解

### 1) Init - 项目初始化

**目的**：创建 cc-spec 项目结构与默认配置，并生成编排层命令文件（如 Claude Code 的 `/cc-spec:*`）。

```bash
cc-spec init
```

**产出（示例）**：
- `.cc-spec/`（changes/specs/archive/templates/config.yaml）
- `.claude/commands/cc-spec/*.md`（如使用 Claude Code）

---

### 2) Index - 初始化/更新项目索引（推荐）

**目的**：生成项目结构索引文件，供后续上下文注入与结构概览使用。

```bash
cc-spec init-index --level l1 --level l2
# 或增量更新（当前等价于 init-index）
cc-spec update-index --level l1 --level l2

# 检查索引是否齐全
cc-spec check-index
```

**产出**：
- `PROJECT_INDEX.md`
- `FOLDER_INDEX.md`（按文件夹生成）
- `.cc-spec/index/manifest.json`、`.cc-spec/index/status.json`

---

### 3) Specify - 需求规格

**目的**：定义需求与范围。

```bash
cc-spec specify <change-name>
```

**产出**：`.cc-spec/changes/<change>/proposal.md`

---

### 4) Clarify - 返工 / 歧义检测

**目的**：标记返工或做轻量歧义检测（不做交互式问答回写）。

```bash
cc-spec clarify
cc-spec clarify <task-id>
cc-spec clarify --detect
```

---

### 5) Plan - 任务规划

**目的**：将需求拆解为可执行任务。

```bash
cc-spec plan
```

**产出**：`.cc-spec/changes/<change>/tasks.yaml`

---

### 6) Apply - 任务执行

**目的**：按 Wave 并发执行任务。

```bash
cc-spec apply --max-concurrent 3
```

说明：
- Wave 内并行、Wave 间串行
- 可用 `--resume` 重试 FAILED/IN_PROGRESS

---

### 7) Accept - 端到端验收

**目的**：执行自动化检查（lint/test/build/type-check），并生成验收报告。

```bash
cc-spec accept
```

**产出**：
- `.cc-spec/changes/<change>/acceptance.md`
- `.cc-spec/changes/<change>/acceptance-report.md`（默认开启）

---

### 8) Archive - 归档

**目的**：归档已完成变更。

```bash
cc-spec archive
```

---

## 快速需求通道（quick-delta）

```bash
cc-spec quick-delta "Fix typo in README"
```

适用场景：小范围改动/热修复。建议仍执行 `cc-spec accept` 做基础验收。

---

## 失败回路（推荐）

```
accept 未通过 → 分析失败原因 → clarify（补需求）或 apply（补实现） → 重新 accept
```

---

## 状态转换图（简化）

```
SPECIFY → CLARIFY → PLAN → APPLY → ACCEPT → ARCHIVE
   ↑        ↑                   │
   │        └───────────┐       │
   └────────────────────┴───────┘
```
