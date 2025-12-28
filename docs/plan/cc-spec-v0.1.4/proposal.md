# cc-spec v0.1.4 变更提案

**变更 ID**: cc-spec-v0.1.4
**代号**: 四源融合 + 单一真相源
**状态**: Draft

---

## 1. 背景与目标

### 问题陈述

v0.1.3 版本仅完成了**骨架实现**，存在以下核心问题：
- 命令文件只有 ~20 行（设计应为 150-300 行完整工作流指令）
- clarify 缺少 9 大歧义分类检测
- plan 生成的 proposal.md + design.md 存在内容重复
- SubAgent 上下文浪费（每个 ~5K tokens）

### 业务价值

整合 Spec-Kit、OpenSpec、auto-dev、DOCUMENTATION-GUIDELINES 四个项目精华，实现：
- 完整的 AI 辅助开发工作流
- 高效的文档结构（单一真相源）
- 优化的 SubAgent 执行效率

### 技术约束

| 约束 | 说明 |
|------|------|
| Python 版本 | ≥3.10 |
| 单文件行数 | <500 行 |
| 注释/提示语言 | 中文 |
| 命令命名空间 | `cc-spec` |
| 主 Agent 上下文 | ≤150K tokens |
| SubAgent 上下文 | ≤500 tokens/agent |

---

## 2. 缺口分析

### 核心缺口

| 编号 | 缺口 | 严重程度 | 当前状态 |
|------|------|----------|----------|
| G-01 | 命令文件内容简陋 | 🔴 严重 | ~20 行 vs 设计 ~250 行 |
| G-02 | clarify 缺少歧义检测 | 🔴 严重 | 无自动检测 |
| G-03 | 文档结构重复 | 🟡 中等 | proposal + design 重复 |
| G-04 | SubAgent 上下文浪费 | 🟡 中等 | ~5K vs 设计 ~500 tokens |
| G-05 | 技术检查未统一执行 | 🟡 中等 | 无主 Agent 统一检查 |

### 现有实现状态

**已完整实现 ✅**
- 17+ AI 工具命令生成器框架
- ID 系统（C-001/S-001/A-001）
- Git 分布式锁（LockManager）
- 四维度打分数据结构

**完全缺失 ❌**
- 命令文件完整工作流指令
- clarify 9 大歧义分类检测
- 单一真相源文档结构
- SubAgent 上下文优化

---

## 3. 技术决策

### 3.1 单一真相源

**决策**: 合并 `proposal.md` + `design.md` 为统一的 `proposal.md`

```markdown
# proposal.md (新结构)
## 1. 背景与目标
## 2. 用户故事
## 3. 技术决策    ← 原 design.md 内容
## 4. 成功标准
```

**理由**: 消除文档重复，减少维护成本

### 3.2 结构化任务

**决策**: `tasks.md` → `tasks.yaml`

```yaml
# tasks.yaml (~500 tokens vs 原 ~3000 tokens)
meta:
  change: add-oauth
  max_concurrent: 10
waves:
  - id: 0
    type: gate
    tasks:
      - id: T01
        name: 初始化
        refs: [src/]
        checklist: $templates/setup-checklist
```

**理由**: 结构化易解析，体积降低 80%

### 3.3 SubAgent 上下文优化

**决策**: 主 Agent 预处理 + 精简上下文传递

```
主 Agent: proposal.md → 摘要 (~200 tokens)
SubAgent: 摘要 + 任务定义 + 文件路径 (~500 tokens)
```

**理由**: 从 ~5K 降到 ~500 tokens/agent，10 并发节省 ~45K

### 3.4 公共模板引用

**决策**: `$templates/` 引用机制

```yaml
checklist: $templates/feature-checklist  # 引用公共模板
```

**理由**: 避免检查清单在 tasks.yaml 中重复定义

### 3.5 歧义检测改进

**决策**: 关键词匹配 + 上下文判断

```python
# 避免误报："数据结构已定义" 不应标记为歧义
if "已定义" in line or "已确定" in line:
    return False  # 跳过
```

### 3.6 技术检查失败处理

| 检查类型 | 失败处理 |
|----------|----------|
| lint | 警告继续 |
| type-check | 警告继续 |
| test | **阻断执行** |

---

## 4. 成功标准

### 功能标准

- [ ] 命令文件生成器输出 150-300 行完整工作流指令
- [ ] clarify 命令具备 9 大歧义分类检测（含上下文判断）
- [ ] 单一真相源：proposal.md 包含技术决策章节
- [ ] 结构化任务：plan 生成 tasks.yaml
- [ ] SubAgent 上下文 ≤500 tokens/agent
- [ ] 公共模板引用机制可用
- [ ] 技术检查由主 Agent 统一执行

### 质量标准

```bash
uv run ruff check src/           # 0 errors
uv run mypy src/cc_spec/         # 0 errors
uv run pytest                    # 全部通过
uv run pytest --cov=cc_spec      # 覆盖率 ≥70%
```

---

## 5. 风险与缓解

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 命令模板过长导致上下文溢出 | 中 | 中 | 关键信息前置，提供 `--minimal` 选项 |
| 歧义检测误报 | 高 | 低 | 上下文判断 + 忽略标记 |
| CLAUDE.md 格式不统一 | 中 | 中 | 支持多格式 + 回退到智能检测 |
| 向后兼容 | 低 | 高 | 保留 MANAGED 标记 + 迁移指南 |

---

## 6. 目录结构（更新后）

```
.cc-spec/
├── config.yaml
├── templates/                    # 公共模板（新增）
│   ├── setup-checklist.md
│   ├── feature-checklist.md
│   └── test-checklist.md
├── changes/
│   └── <change-name>/
│       ├── proposal.md           # 单一真相源
│       ├── tasks.yaml            # 结构化任务
│       └── status.yaml
└── archive/
```
