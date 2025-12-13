# cc-spec archive 命令使用指南

## 概述

`cc-spec archive` 命令用于归档已完成的变更，它会：

1. 验证 checklist 阶段已完成
2. 显示将要合并的 Delta specs 预览
3. 将 Delta specs 合并到主 specs/ 目录
4. 将变更目录移动到 archive/YYYY-MM-DD-{name}/

## 基本用法

### 归档当前活动的变更

```bash
cc-spec archive
```

这会归档当前活动的变更（自动检测）。

### 归档指定的变更

```bash
cc-spec archive add-oauth
```

归档名为 `add-oauth` 的变更。

### 跳过确认提示

```bash
cc-spec archive add-oauth --force
# 或
cc-spec archive add-oauth -f
```

使用 `--force` 或 `-f` 选项可以跳过确认提示，直接执行归档。

## 前置条件

归档变更之前，必须满足以下条件：

1. **Checklist 阶段已完成**：必须先运行 `cc-spec checklist` 并通过验收
2. **变更目录存在**：变更必须在 `.cc-spec/changes/` 目录中
3. **status.yaml 有效**：状态文件必须存在且格式正确

## 归档流程

### 1. 验证前置条件

命令会首先检查：
- 项目是否初始化（存在 `.cc-spec/` 目录）
- 变更是否存在
- Checklist 阶段是否已完成

如果不满足条件，命令会报错并退出。

### 2. 查找 Delta Specs

命令会在变更的 `specs/` 目录中查找所有 Delta spec 文件：

```
.cc-spec/changes/add-oauth/
└── specs/
    ├── auth/
    │   └── spec.md  (Delta spec)
    └── api/
        └── spec.md  (Delta spec)
```

### 3. 显示合并预览

对于找到的每个 Delta spec，命令会显示：
- Delta 变更的 capability 名称
- ADDED Requirements（新增的需求）
- MODIFIED Requirements（修改的需求）
- REMOVED Requirements（删除的需求）
- RENAMED Requirements（重命名的需求）
- 验证结果

示例输出：

```
Merge Preview:
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                   auth/spec.md                    ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

# Merge Preview for Delta: auth

Total changes: 2

## ADDED Requirements (1)
  + OAuth2 Authentication

## MODIFIED Requirements (1)
  ~ User Session Management

## Validation
  ✓ All validations passed
```

### 4. 用户确认

除非使用了 `--force` 选项，命令会询问用户确认：

```
The following actions will be performed:
  1. Merge 2 Delta spec(s) into main specs/
  2. Move change directory to archive/2024-01-15-add-oauth/

Do you want to continue? [y/N]:
```

### 5. 执行合并

命令会将每个 Delta spec 合并到主 specs/ 目录：

```
Merging Delta specs...
✓ Merged auth/spec.md
✓ Merged api/spec.md
```

合并规则：
- **ADDED**：在 spec 文件末尾添加新的 Requirement
- **MODIFIED**：完全替换现有 Requirement 的内容
- **REMOVED**：从 spec 文件中删除 Requirement
- **RENAMED**：修改 Requirement 的标题，保留内容

### 6. 移动到 Archive

变更目录会被移动到 `archive/` 目录，文件名格式为 `YYYY-MM-DD-{name}`：

```
Moving change to archive...
✓ Moved to archive/2024-01-15-add-oauth/
```

如果同名的 archive 已存在，会自动添加时间后缀（HHMMSS）。

### 7. 完成

显示成功消息和归档位置：

```
Archive completed successfully!

Merged 2 spec(s) to .cc-spec/specs
Archived to .cc-spec/changes/archive/2024-01-15-add-oauth
```

## 归档后的目录结构

### Before（归档前）

```
.cc-spec/
├── specs/
│   └── auth/
│       └── spec.md (现有的 spec)
└── changes/
    └── add-oauth/
        ├── proposal.md
        ├── tasks.md
        ├── design.md
        ├── status.yaml
        └── specs/
            └── auth/
                └── spec.md (Delta spec)
```

### After（归档后）

```
.cc-spec/
├── specs/
│   └── auth/
│       └── spec.md (已合并 Delta 变更)
└── changes/
    └── archive/
        └── 2024-01-15-add-oauth/
            ├── proposal.md
            ├── tasks.md
            ├── design.md
            ├── status.yaml
            └── specs/
                └── auth/
                    └── spec.md (Delta spec)
```

## 错误处理

### 错误：Not a cc-spec project

```
Error: Not a cc-spec project. Run 'cc-spec init' first.
```

**解决方法**：在项目根目录运行 `cc-spec init` 初始化项目。

### 错误：Change not found

```
Error: Change 'add-oauth' not found.
```

**解决方法**：检查变更名称是否正确，或使用不带参数的 `cc-spec archive` 来归档当前活动变更。

### 错误：Checklist stage must be completed

```
Error: Checklist stage must be completed before archiving.
Hint: Run cc-spec checklist to complete the checklist validation.
```

**解决方法**：先运行 `cc-spec checklist` 完成验收检查。

### 错误：Delta spec validation failed

```
Error: Delta spec validation failed for auth/spec.md:
  - Item 1 (added): content is required for ADDED/MODIFIED operations
```

**解决方法**：检查 Delta spec 格式，确保所有必需字段都已填写。

## 警告信息

### 警告：No specs/ directory found

```
Warning: No specs/ directory found in change. Nothing to merge.
```

这不会阻止归档，变更仍会被移动到 archive 目录。

### 警告：Archive already exists

```
Warning: Archive already exists, using 2024-01-15-add-oauth-143025
```

当目标 archive 名称已存在时，会自动添加时间后缀以避免冲突。

## 最佳实践

1. **归档前检查**：确保所有任务已完成，checklist 已通过
2. **审查合并预览**：仔细检查将要合并的变更是否正确
3. **定期归档**：完成一个变更后及时归档，保持工作目录整洁
4. **备份重要变更**：归档前可以手动备份重要的变更记录

## 示例工作流

完整的变更流程示例：

```bash
# 1. 创建变更规格
cc-spec specify add-oauth

# 2. 编辑 proposal.md 填写需求
# ...

# 3. 生成执行计划
cc-spec plan

# 4. 编辑 tasks.md 和 design.md
# ...

# 5. 执行任务（如果支持）
cc-spec apply

# 6. 完成后进行验收
cc-spec checklist

# 7. 归档变更
cc-spec archive

# 或者跳过确认直接归档
cc-spec archive --force
```

## 相关命令

- `cc-spec specify` - 创建新的变更规格
- `cc-spec plan` - 生成执行计划
- `cc-spec checklist` - 验收打分
- `cc-spec init` - 初始化项目

## 注意事项

1. **不可逆操作**：归档操作会移动变更目录，虽然文件仍然保留在 archive/ 中，但要恢复需要手动操作
2. **合并冲突**：如果 Delta spec 引用的 Requirement 在主 spec 中不存在（MODIFIED/REMOVED/RENAMED），会报错
3. **文件权限**：确保对 `.cc-spec/` 目录有写权限
