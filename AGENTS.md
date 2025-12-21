<!-- CC-SPEC:START -->
# AGENTS.md (for Codex)

## 角色定位
- 作为执行 Agent，负责实际的代码编写和修改
- 从 KB 获取上下文（需求 + 代码），理解任务目标
- 直接执行任务，修改代码文件
- 遵循项目规范，输出高质量代码

## 产出物
- **业务代码**：功能实现（.py, .ts, .js, .go 等）
- **测试代码**：单元测试、集成测试（test_*.py, *.spec.ts 等）
- **配置文件**：应用配置（非 cc-spec 相关）
- **数据库迁移**：Schema 变更（migrations/）

### 禁止产出
- cc-spec 规范文件（proposal.md, tasks.yaml, base-template.yaml）
- KB 记录（由 Claude 通过 cc-spec kb record 写入）
- 工作流状态文件（status.yaml）

## 执行规则
- 严格按照 prompt 中的任务要求执行
- 遵循项目编码规范（从 KB 上下文获取）
- 最小作用域，只改需求范围内的代码
- 不擅自扩展需求范围

## 项目编码规范
- (none)

## 命令说明
- **specify**：创建新的变更规格说明
  - `cc-spec specify <变更名称>`
- **clarify**：审查任务并标记需要返工的内容
  - `cc-spec clarify`
- **plan**：从提案生成执行计划
  - `cc-spec plan`
- **apply**：使用 SubAgent 并行执行任务
  - `cc-spec apply`
- **checklist**：使用检查清单评分验证任务完成情况
  - `cc-spec checklist`
- **archive**：归档已完成的变更
  - `cc-spec archive`
- **quick-delta**：快速模式，一步创建并归档简单变更
  - `cc-spec quick-delta <变更名称> "<变更描述>"`
- **list**：列出变更、任务、规格或归档
  - `cc-spec list [changes|tasks|specs|archives]`
- **goto**：导航到特定变更或任务
  - `cc-spec goto <变更名称>`
- **update**：更新配置、命令或模板
  - `cc-spec update [config|commands|templates]`
- **kb**：KB（向量库）相关命令
  - `kb init`：全量构建 KB
  - `kb update`：增量更新 KB
  - `kb query`：向量检索
  - `kb context`：输出格式化上下文
<!-- CC-SPEC:END -->


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
