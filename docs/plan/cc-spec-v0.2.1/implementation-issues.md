# 当前实现问题分析

> 分析日期: 2025-12-24
> 关联: skills-vs-commands-research.md

---

## 问题概述

当前 cc-spec-tool 的实现存在严重的概念混淆，需要修正。

---

## 问题 1：命名和概念混淆

### 现状

| 文件 | 名字说的是 | 实际做的是 |
|------|-----------|-----------|
| `skills.rs` | Skills 管理 | **Commands 安装** |
| `types/skills.ts` | Skills 类型 | **Commands 类型** |
| `SKILL_NAMES` 常量 | Skill 列表 | **Command 列表** |
| `install_skills()` | 安装 Skills | **安装 Commands** |
| `check_skills_status()` | 检查 Skills | **检查 Commands** |

### 代码证据

```rust
// skills.rs:53-57 - 安装目标明显是 commands 目录
fn get_project_skills_dir(project_path: &str) -> PathBuf {
    PathBuf::from(project_path)
        .join(".claude")
        .join("commands")  // ← 这里！
}
```

### 修正方案

- [x] 记录问题分析（本文档）
- [ ] 重命名 `skills.rs` → `commands.rs`
- [ ] 重命名 `types/skills.ts` → `types/commands.ts`
- [ ] 修正所有相关命名（函数名、变量名、注释）

---

## 问题 2：Commands 不需要复杂管理

### 现状

当前 `skills.rs` 有复杂的版本管理、安装检查、复制逻辑，但：

- **Commands 是固定的**，跟随工具版本
- **不需要用户配置**
- **只需要在 tools 里提示用户怎么用**

### 修正方案

- [ ] 简化 Commands 管理逻辑（或直接内置）
- [ ] 新增 **Commands 使用技巧页面**：
  - 展示可用 commands 列表
  - 每个 command 的用途和示例
  - 使用技巧和最佳实践

---

## 问题 3：缺失真正的 Skills 管理

### 现状

真正需要管理的 Skills（自动触发的专业知识包）完全没有实现。

### Skills vs Commands 区别

| | **Commands** | **Skills** |
|---|---|---|
| **触发方式** | 用户显式调用 `/cc-spec-plan` | 自动触发（基于用户意图） |
| **配置** | 固定，不需要配置 | 需要持久化到 tools |
| **用户操作** | 直接用 | 可添加、选择安装、跨项目复用 |

### 修正方案

- [ ] 设计 Skills 管理架构
- [ ] 实现 `tools.yaml` 配置结构
- [ ] 实现 Skills 管理功能：
  - 内置 Skills（预设）
  - 用户 Skills（添加/导入）
  - 持久化配置
  - 选择性安装到项目
  - 跨项目复用

---

## 修正任务清单

### Phase 1: 命名修正

1. [ ] 重命名 `skills.rs` → `commands.rs`
2. [ ] 重命名 `types/skills.ts` → `types/commands.ts`
3. [ ] 修正 Rust 代码中的相关命名
4. [ ] 修正 TypeScript 代码中的相关命名
5. [ ] 更新 `main.rs` 中的模块引用

### Phase 2: Commands 使用技巧页面

1. [ ] 创建 `CommandsGuidePage.tsx` 组件
2. [ ] 展示可用 commands 列表
3. [ ] 添加使用示例和技巧
4. [ ] 集成到设置页面或独立页面

### Phase 3: Skills 管理架构

1. [ ] 设计 `tools.yaml` 配置结构
2. [ ] 实现新的 `skills.rs`（真正的 Skills 管理）
3. [ ] 实现 Skills 管理 UI

---

## 目标架构

```
Tools 层 (cc-spec-tool)
├── Commands（固定，提示用法）
│   ├── /cc-spec-specify
│   ├── /cc-spec-clarify
│   ├── /cc-spec-plan
│   ├── /cc-spec-apply
│   ├── /cc-spec-accept
│   └── /cc-spec-archive
│
└── Skills（需要管理）
    ├── 内置 Skills（预设，自动触发）
    └── 用户 Skills（可添加，跨项目复用）
            ↓
        tools.yaml 持久化
            ↓
        可选择安装到项目
```
