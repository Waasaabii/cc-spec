# cc-spec v1.3 规划文档

## 版本定位

**v1.3 - 全流程完善版**

基于历史设计文档的深度审计，补齐所有未实现的核心功能，实现完整的规范驱动开发工作流。

## 当前状态

🟦 **规划完成，待实施**

## v1.3 核心特性

### 1. 四维度打分机制

```yaml
打分维度:
  功能完整性: 30%  # 是否满足 spec 需求
  代码质量: 25%    # 符合项目规范
  测试覆盖: 25%    # 测试充分性
  文档同步: 20%    # 注释、类型、文档
```

**输出示例**:
```
| Task-ID | 总分 | 功能 | 质量 | 测试 | 文档 | 状态 |
|---------|------|------|------|------|------|------|
| 01-SETUP | 92 | 95 | 90 | 88 | 95 | ✅ PASS |
| 02-MODEL | 65 | 70 | 60 | 55 | 80 | ❌ FAIL |
```

### 2. Git 分布式锁

```yaml
锁机制:
  文件锁: .cc-spec/locks/<task-id>.lock
  超时: 30 分钟自动释放
  用途: 防止多实例并发冲突
```

### 3. 执行状态增强

```yaml
# status.yaml v1.3
tasks:
  - id: "01-SETUP"
    status: completed
    agent_id: "agent-a1b2c3"  # 新增
    started_at: "..."
    completed_at: "..."
    retry_count: 0
```

### 4. quick-delta 增强

```yaml
功能增强:
  - 解析 git diff --staged
  - 自动判断 ADDED/MODIFIED/REMOVED
  - 生成文件变更表格
```

## 文档索引

| 文档 | 描述 |
|------|------|
| [01-背景与目标](./01-背景与目标.md) | 版本定位、历史设计来源、v1.2 遗留问题 |
| [02-现状分析](./02-现状分析.md) | v1.2 代码审计、历史对比、缺口汇总 |
| [03-设计方案](./03-设计方案.md) | 完整工作流、四维度打分、Git 锁、数据结构 |
| [04-实施步骤](./04-实施步骤.md) | Gate 划分、Wave 规划、验收标准 |
| [05-任务拆分](./05-任务拆分.md) | 16 个任务详细定义、依赖关系、Checklist |

## 工作流概览

```
┌─────────────────────────────────────────────────────────────┐
│                      cc-spec 工作流                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  超简单模式:                                                 │
│    cc-spec quick-delta "描述" → 解析 git diff → 归档         │
│                                                             │
│  标准模式 (7 步):                                            │
│                                                             │
│    规划阶段 (任意 AI 工具):                                   │
│      init → specify → clarify → plan                        │
│                                  ↓                          │
│    执行阶段 (仅 Claude Code):                                │
│      apply (主 Agent + 10 SubAgent 并发 + Git 锁)           │
│                                  ↓                          │
│    验收阶段 (任意 AI 工具):                                   │
│      checklist (四维度打分, ≥80分通过)                        │
│           ↓ <80分: 打回 apply                                │
│           ↓ ≥80分                                            │
│      archive (Delta 合并 + 归档)                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 任务概览

| Wave | 任务数 | 主题 | 预估 |
|------|--------|------|------|
| 0 | 1 | 项目准备 | 20k |
| 1 | 2 | 配置扩展 | 55k |
| 2 | 3 | 核心模块 | 140k |
| 3 | 2 | 执行器集成 | 65k |
| 4 | 2 | 命令更新 | 85k |
| 5 | 1 | 增强功能 | 35k |
| 6 | 3 | 测试补充 | 85k |
| 7 | 2 | 文档发布 | 60k |

**总计**: 16 个任务, ~545k tokens, 8 个 Wave

## 关键变更文件

### 修改文件

| 文件 | 变更内容 |
|------|----------|
| `core/config.py` | ScoringConfig, LockConfig |
| `core/scoring.py` | 四维度打分重构 |
| `core/state.py` | TaskInfo 添加 agent_id 等 |
| `subagent/executor.py` | 锁集成, agent_id |
| `commands/checklist.py` | 维度打分输出 |
| `commands/apply.py` | 锁集成 |
| `commands/quick_delta.py` | git diff 解析 |

### 新增文件

| 文件 | 内容 |
|------|------|
| `core/lock.py` | LockInfo, LockManager |
| `tests/test_scoring_v13.py` | 打分测试 |
| `tests/test_lock.py` | 锁测试 |
| `tests/test_quick_delta_v13.py` | quick-delta 测试 |

## 执行入口

```bash
# 查看任务列表
cat docs/plan/cc-spec-v1.3/05-任务拆分.md

# 开始执行 (在 Claude Code 中)
/cc-spec:apply cc-spec-v1.3
```

## 前置条件

- [x] v1.2 功能稳定
- [x] 历史设计文档审计完成
- [x] v1.3 规划文档完整

## 相关链接

- [v1.0 规划](../cc-spec/README.md)
- [v1.1 规划](../cc-spec-v1.1/README.md)
- [v1.2 规划](../cc-spec-v1.2/README.md)
- [历史设计聊天记录](../../reference/历史聊天/12488661-ea75-42fd-8cf8-7541721d75a3.md)
