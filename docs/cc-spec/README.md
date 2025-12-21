# cc-spec

**Spec-driven AI-assisted development workflow CLI**

cc-spec 是一个帮助开发者管理 AI 辅助开发工作流的命令行工具。它提供了从需求定义到任务执行的完整流程管理。

## 特性

- 🚀 **结构化工作流** - 从 specify 到 archive 的完整开发流程
- 🤖 **SubAgent 并发执行** - 支持多任务并行处理，显著提升效率
- 📋 **任务管理** - Wave 分组、依赖管理、进度追踪
- ✅ **质量保障** - 内置 checklist 验证机制
- 📦 **变更归档** - 自动归档已完成的变更

## 快速开始

### 安装

```bash
# 使用 uv (推荐)
uv pip install cc-spec

# 或使用 pip
pip install cc-spec
```

### 基本工作流

```bash
# 1. 初始化项目
cc-spec init

# 2. （推荐）构建/更新知识库
cc-spec kb init

# 3. 创建变更规范
cc-spec specify add-user-auth

# 4. 澄清需求/返工
cc-spec clarify

# 5. 生成任务计划
cc-spec plan add-user-auth

# 6. 执行任务 (SubAgent 并发)
cc-spec apply add-user-auth

# 7. 验证 checklist
cc-spec checklist add-user-auth

# 8. 归档变更
cc-spec archive add-user-auth
```

### 快速修复

对于小型修改，可以使用 quick-delta 命令：

```bash
cc-spec quick-delta "Fix typo in README"
```

## 测试

分层运行（integration 需显式开启）：

```bash
pytest -m unit
pytest -m cli
pytest -m rag
pytest -m codex
```

集成测试（不默认跑）：

```bash
pytest -m integration
```

## 项目结构

初始化后，项目会创建以下结构：

```
.cc-spec/
├── config.yaml          # 配置文件
├── templates/           # 模板文件
│   ├── proposal.md
│   └── tasks.yaml
└── changes/             # 变更目录
    ├── add-user-auth/   # 活跃变更
    │   ├── proposal.md
    │   ├── tasks.yaml
    │   └── status.yaml
    └── archive/         # 已归档变更
```

## 命令概览

| 命令 | 说明 |
|------|------|
| `init` | 初始化 cc-spec 项目 |
| `specify` | 创建新的变更规范 |
| `clarify` | 查看任务列表或标记任务返工 |
| `plan` | 生成任务计划 |
| `apply` | 执行任务 (SubAgent 并发) |
| `checklist` | 验证任务完成情况 |
| `archive` | 归档已完成的变更 |
| `quick-delta` | 快速创建并归档小型变更 |

## 更多文档

- [安装指南](installation.md)
- [命令参考](commands.md)
- [工作流详解](workflow.md)

## 系统要求

- Python 3.12+
- 推荐使用 [uv](https://github.com/astral-sh/uv) 包管理器

## 许可证

MIT License
