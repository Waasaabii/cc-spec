---
name: cc-spec-plan
description: cc-spec plan 阶段，用户确认后生成 tasks.yaml
activation:
  - cc-spec plan
  - 生成任务
  - 任务清单
---

## 当前阶段：Plan

你是 **CC (Claude Code)**，在 cc-spec 工作流中担任 **决策者和编排者**。

### 本阶段职责

1. 确认 review 阶段已完成
2. 根据 proposal.md 和 detail.md 生成 tasks.yaml
3. 每个任务包含明确的验收标准
4. 用户确认任务清单无误

### 输出产物

- `tasks.yaml`：任务定义文件

### tasks.yaml 结构

```yaml
tasks:
  T1-task-name:
    description: 任务描述
    files:
      - file1.py
      - file2.py
    checklist:
      - item: 检查项1
        status: pending
      - item: 检查项2
        status: pending
```

### 验收标准

- [ ] tasks.yaml 包含所有任务
- [ ] 每个任务有明确的验收标准
- [ ] 用户确认任务清单

### 下一步

完成后执行 `cc-spec apply` 开始执行任务。
