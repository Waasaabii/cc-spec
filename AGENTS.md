# AI工具使用指南

本项目使用 cc-spec 工作流进行规格驱动的开发。

## cc-spec 命令说明

cc-spec 提供以下命令来管理开发工作流：

### 1. specify - 创建新的变更规格说明
创建一个新的变更提案，描述要实现的功能或修复。

**使用方式**：
```bash
cc-spec specify <变更名称>
```

### 2. clarify - 审查任务并标记需要返工的内容
审查现有任务，标记需要重新处理的部分。

**使用方式**：
```bash
cc-spec clarify
```

### 3. plan - 从提案生成执行计划
根据变更提案自动生成详细的执行计划和任务列表。

**使用方式**：
```bash
cc-spec plan
```

### 4. apply - 使用SubAgent并行执行任务
使用多个SubAgent并行执行计划中的任务。

**使用方式**：
```bash
cc-spec apply
```

### 5. checklist - 使用检查清单评分验证任务完成情况
根据检查清单验证任务是否按要求完成。

**使用方式**：
```bash
cc-spec checklist
```

### 6. archive - 归档已完成的变更
将完成的变更归档，清理工作区。

**使用方式**：
```bash
cc-spec archive
```

### 7. quick-delta - 快速模式
一步创建并归档简单变更，适用于小型修改。

**使用方式**：
```bash
cc-spec quick-delta <变更名称> "<变更描述>"
```

### 8. list - 列出变更、任务、规格或归档
列出项目中的各种工作项。

**使用方式**：
```bash
cc-spec list [changes|tasks|specs|archives]
```

### 9. goto - 导航到特定变更或任务
快速导航到指定的变更或任务。

**使用方式**：
```bash
cc-spec goto <变更名称>
```

### 10. update - 更新配置、命令或模板
更新cc-spec的配置文件、命令或模板。

**使用方式**：
```bash
cc-spec update [config|commands|templates]
```

## 工作流程示例

1. 创建新变更：`cc-spec specify add-user-auth`
2. 编辑生成的 `.cc-spec/changes/add-user-auth/proposal.md`
3. 生成执行计划：`cc-spec plan`
4. 执行任务：`cc-spec apply`
5. 验证完成：`cc-spec checklist`
6. 归档变更：`cc-spec archive`

## 配置

项目配置位于 `.cc-spec/config.yaml`，您可以在其中调整：
- 默认AI工具
- SubAgent并发数
- 检查清单阈值
- 技术规范文件路径

---

*本文件由 cc-spec v0.1.0 自动生成*
