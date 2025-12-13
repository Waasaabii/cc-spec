# cc-spec v0.1.4 开发计划

**版本**: 0.1.4
**代号**: 四源融合 (Four-source Fusion)
**预估改动**: ~2900 行代码

---

## 概述

本版本实现"四源融合"设计理念，整合 Spec-Kit、OpenSpec、auto-dev 和 DOCUMENTATION-GUIDELINES
的设计精华，重点解决命令文件过于简陋（~20行 vs 设计要求的~250行）的核心问题。

### 核心目标

| 目标 | 说明 |
|------|------|
| 命令模板系统 | 每个命令生成 150-300 行完整工作流指令 |
| 歧义检测器 | 支持 9 大歧义分类自动检测 |
| 技术检查模块 | 从 CLAUDE.md 读取或智能检测技术栈 |
| clarify 增强 | 新增 `--detect` 选项 |
| apply 增强 | 主 Agent 统一执行技术检查 |

### 技术约束

| 约束 | 说明 |
|------|------|
| Python 版本 | ≥3.10 |
| 单文件行数 | <500 行 |
| **注释语言** | **中文自然语言** |
| **提示文本** | **中文自然语言** |
| **命令命名空间** | **cc-spec** |
| **主 Agent 上下文** | **≤150K tokens** |
| **SubAgent 并发数** | **读取 config.yaml** |

> **中文化要求**：所有新增代码的注释、文档字符串、日志消息、错误提示和模板内容必须使用中文自然语言编写。

> **命令命名规范**：所有生成的 slash commands 统一使用 `cc-spec` 命名空间（如 `/cc-spec:specify`、`/cc-spec:apply`）。

> **并发规划约束**：plan 命令从 `config.yaml` 的 `subagent.max_concurrent` 读取并发数量，每个 Wave 的任务数 ≤ max_concurrent，主 Agent 上下文 ≤ 150K tokens。

---

## 文档索引

| 序号 | 文档 | 说明 |
|------|------|------|
| 01 | [背景与目标](./01-背景与目标.md) | 业务目的、版本定位、发版标准 |
| 02 | [现状分析](./02-现状分析.md) | 当前实现状态（含精确行号引用） |
| 03 | [缺口分析](./03-缺口分析.md) | 7 大差距识别与影响分析 |
| 04 | [设计方案](./04-设计方案.md) | 详细实现设计（含代码示例） |
| 05 | [实施步骤](./05-实施步骤.md) | Gate/Wave 任务规划（13 个任务） |
| 06 | [测试与验收](./06-测试与验收.md) | 测试文件、命令、验收标准 |
| 07 | [风险与依赖](./07-风险与依赖.md) | 风险评估、依赖列表、回滚方案 |
| 08 | [里程碑](./08-里程碑.md) | 6 个里程碑定义与验收标准 |
| 09 | [附录](./09-附录.md) | 必读文件、改动行数、强制命令 |

---

## 实施总览

### Gate/Wave 结构

```
Gate-0 (串行)     T01-TEMPLATE-BASE, T02-AMBIGUITY-BASE
    │
    ▼
Wave-1 (并行)     T03-SPECIFY-TEMPLATE, T04-CLARIFY-TEMPLATE, T05-PLAN-TEMPLATE
    │
    ▼
Wave-2 (并行)     T06-AMBIGUITY-DETECTOR, T07-APPLY-TEMPLATE, T08-CHECKLIST-TEMPLATE
    │
    ▼
Wave-3 (并行)     T09-TECH-CHECK, T10-GENERATOR-REFACTOR
    │
    ▼
Wave-4 (并行)     T11-CLARIFY-INTEGRATION, T12-APPLY-TECH-CHECK, T13-INIT-PROMPT
```

### 任务清单

| 任务 ID | 名称 | 预估行数 |
|---------|------|----------|
| T01 | TEMPLATE-BASE | ~80 |
| T02 | AMBIGUITY-BASE | ~120 |
| T03 | SPECIFY-TEMPLATE | ~250 |
| T04 | CLARIFY-TEMPLATE | ~200 |
| T05 | PLAN-TEMPLATE | ~280 |
| T06 | AMBIGUITY-DETECTOR | ~200 |
| T07 | APPLY-TEMPLATE | ~220 |
| T08 | CHECKLIST-TEMPLATE | ~180 |
| T09 | TECH-CHECK | ~250 |
| T10 | GENERATOR-REFACTOR | ~100 |
| T11 | CLARIFY-INTEGRATION | ~80 |
| T12 | APPLY-TECH-CHECK | ~60 |
| T13 | INIT-PROMPT | ~50 |

---

## 里程碑

| 里程碑 | 内容 | 状态 |
|--------|------|------|
| M1 | 基础设施完成 | ⬜ 未开始 |
| M2 | 核心模板完成 | ⬜ 未开始 |
| M3 | 检测器和续模板完成 | ⬜ 未开始 |
| M4 | 技术检查和集成完成 | ⬜ 未开始 |
| M5 | 测试和文档完成 | ⬜ 未开始 |
| M6 | 发布 v0.1.4 | ⬜ 未开始 |

---

## 快速参考

### 核心代码文件

| 文件 | 关键行号 | 说明 |
|------|----------|------|
| `command_generator.py` | 160-182, 184-201 | 命令生成核心（需重构） |
| `clarify.py` | 65-101, 182-278 | clarify 命令（需增强） |
| `apply.py` | 326-427 | apply 命令（需集成技术检查） |
| `scoring.py` | 324-363, 443-513 | 四维度打分（已完善） |

### 强制命令

```bash
# 开发阶段
uv run ruff check src/
uv run mypy src/cc_spec/
uv run pytest tests/core/ tests/commands/ -v

# 提交前
uv run pytest --cov=cc_spec --cov-report=term-missing
uv run ruff format --check src/
```

---

## 变更日志预览

```
## [0.1.4] - 四源融合

### Added
- 命令模板系统：每个命令生成 150-300 行完整工作流指令
- 歧义检测器：支持 9 大歧义分类自动检测
- 技术检查模块：从 CLAUDE.md 读取或智能检测技术栈
- clarify 命令新增 `--detect` 选项
- apply 命令新增主 Agent 统一技术检查
- init 命令完成后显示中文配置提示

### Changed
- 重构 command_generator.py 使用模板系统
- checklist 命令使用完整的四维度打分
```

---

## 参考资料

- [Spec-Kit 命令示例](../../../reference/test-project/speckitProject/.codex/prompts/speckit.specify.md)
- [DOCUMENTATION-GUIDELINES](../../../reference/DOCUMENTATION-GUIDELINES.md)
- [历史设计讨论](../../../reference/历史聊天/12488661-ea75-42fd-8cf8-7541721d75a3.md)
