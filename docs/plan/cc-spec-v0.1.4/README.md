# cc-spec v0.1.4 开发计划

**版本**: 0.1.4
**代号**: 四源融合 + 单一真相源
**预估改动**: ~3765 行代码

---

## 概述

本版本实现"四源融合"设计理念，整合 Spec-Kit、OpenSpec、auto-dev 和 DOCUMENTATION-GUIDELINES 的设计精华。

### 核心目标

| 类别 | 目标 |
|------|------|
| 命令模板 | 每个命令生成 150-300 行完整工作流指令 |
| 歧义检测 | 9 大歧义分类自动检测（含上下文判断） |
| 技术检查 | 主 Agent 统一执行，从 CLAUDE.md 读取或智能检测 |
| **单一真相源** | 合并 proposal.md + design.md |
| **结构化任务** | tasks.md → tasks.yaml（体积 -80%） |
| **SubAgent 优化** | 上下文从 ~5K 降到 ~500 tokens/agent |
| **模板引用** | `$templates/` 公共检查清单复用 |

### 技术约束

- Python ≥3.10，单文件 <500 行
- 注释/提示：中文
- 命令命名空间：`cc-spec`
- 主 Agent 上下文 ≤150K tokens
- SubAgent 并发数从 config.yaml 读取

---

## 文档结构

| 文档 | 说明 |
|------|------|
| **README.md** | 概述 + 里程碑（本文件） |
| **proposal.md** | 背景 + 缺口分析 + 技术决策 + 成功标准 |
| **tasks.yaml** | 结构化任务定义（17 个任务） |

---

## 里程碑

| 里程碑 | 内容 | 状态 |
|--------|------|------|
| M1 | 基础设施完成（T01-T02） | ⬜ |
| M2 | 核心模板完成（T03-T05） | ⬜ |
| M3 | 检测器和续模板完成（T06-T08） | ⬜ |
| M4 | 技术检查和集成完成（T09-T13） | ⬜ |
| M5 | 新架构实现完成（T14-T17） | ⬜ |
| M6 | 测试和发布 v0.1.4 | ⬜ |

---

## 快速参考

### 核心代码文件

| 文件 | 关键行号 | 说明 |
|------|----------|------|
| `command_generator.py` | 160-182 | 命令生成核心 |
| `clarify.py` | 65-101 | clarify 命令 |
| `apply.py` | 326-427 | apply 命令 |
| `scoring.py` | 443-513 | 四维度打分 |

### 强制命令

```bash
# 开发阶段
uv run ruff check src/
uv run mypy src/cc_spec/
uv run pytest tests/ -v

# 提交前
uv run pytest --cov=cc_spec --cov-report=term-missing
uv run ruff format --check src/
```

---

## 变更日志预览

```
## [0.1.4] - 四源融合 + 单一真相源

### Added
- 命令模板系统：150-300 行完整工作流指令
- 歧义检测器：9 大歧义分类（含上下文判断）
- 技术检查模块：从 CLAUDE.md 读取或智能检测
- 单一真相源：合并 proposal.md + design.md
- 结构化任务：tasks.yaml（体积 -80%）
- SubAgent 上下文优化（~5K → ~500 tokens）
- 公共模板引用机制（$templates/）

### Changed
- 重构 command_generator.py 使用模板系统
- plan 命令生成 tasks.yaml 而非 tasks.md
- apply 命令预处理上下文后再分发给 SubAgent
```
