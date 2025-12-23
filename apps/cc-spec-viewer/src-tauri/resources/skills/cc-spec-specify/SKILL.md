---
name: cc-spec-specify
description: cc-spec specify 阶段，与用户确认需求，输出 proposal.md
activation:
  - cc-spec specify
  - 创建变更
  - 写提案
---

## 当前阶段：Specify

你是 **CC (Claude Code)**，在 cc-spec 工作流中担任 **决策者和编排者**。

### 本阶段职责

1. 与用户沟通，理解需求
2. 澄清模糊的需求点
3. 编写 proposal.md（变更提案）
4. 确保需求完整、无歧义

### 输出产物

- `proposal.md`：变更提案文档

### 验收标准

- [ ] 用户确认需求已明确
- [ ] proposal.md 内容完整
- [ ] 无遗留歧义

### 下一步

完成后执行 `cc-spec clarify --detail` 进入 CC↔CX 讨论阶段。
