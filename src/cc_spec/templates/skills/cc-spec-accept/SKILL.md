---
name: cc-spec-accept
description: cc-spec accept 阶段，端到端验收
activation:
  - cc-spec accept
  - 验收
  - 检查功能
---

## 当前阶段：Accept

你是 **CC (Claude Code)**，在 cc-spec 工作流中担任 **决策者和编排者**。

### 本阶段职责

1. 执行自动化检查（lint/test/build/type-check）
2. 验证功能端到端可用
3. 检查新增文件是否被正确集成
4. 生成验收报告

### 验收检查

#### 自动化检查
- lint 通过
- test 通过
- build 通过
- type-check 通过

#### 功能验收
- 核心功能可正常使用
- 错误场景有合理提示

#### 集成验收
- 新增文件已被正确 import
- 功能已集成到入口（UI/CLI/API）
- 不依赖 mock 可运行

### 输出产物

- `acceptance.md`：验收标准（可编辑）
- `acceptance-report.md`：验收结果

### 失败处理

验收失败时：
1. 分析失败原因
2. 建议回退目标（detail/review/apply）
3. 用户确认后回退
4. 记录到 meta.rework

### 下一步

验收通过后执行 `cc-spec archive` 归档变更。
