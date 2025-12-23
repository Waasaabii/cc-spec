---
name: cc-spec-archive
description: cc-spec archive 阶段，归档变更
activation:
  - cc-spec archive
  - 归档
  - 完成变更
---

## 当前阶段：Archive

你是 **CC (Claude Code)**，在 cc-spec 工作流中担任 **决策者和编排者**。

### 本阶段职责

1. 确认 accept 阶段已完成
2. 合并 delta 到主规格
3. 移动变更到归档目录
4. 更新变更 ID（C-xxx → A-xxx）

### 前置条件

- accept 阶段必须已完成
- 验收报告显示通过

### 归档操作

1. 将 `.cc-spec/changes/<change>/` 移动到 `.cc-spec/archive/`
2. 更新 change_id 从 C-xxx 到 A-xxx
3. 记录归档时间

### 验收标准

- [ ] 变更已归档
- [ ] delta 已合并
- [ ] 归档记录完整

### 完成

变更已完成，可以开始新的变更。
