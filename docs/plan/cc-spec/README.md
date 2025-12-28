# cc-spec 设计文档

## 概述

**cc-spec** 是一个规范驱动的开发 CLI 工具，整合了 OpenSpec、Spec-Kit 和 auto-dev 的精华，支持 Claude Code SubAgent 并发执行。

## 核心价值

| 来源 | 贡献 |
|------|------|
| **OpenSpec** | Delta 变更追踪、归档规范 |
| **Spec-Kit** | CLI 技术栈 (uv + typer + rich)、模板系统 |
| **auto-dev** | SubAgent 并发、Wave 任务规划 |

## 工作流

```
cc-spec init        → 初始化项目
cc-spec init-index  → 初始化项目索引（推荐）
cc-spec specify     → 编写需求规格
cc-spec clarify     → 澄清/返工
cc-spec plan        → 生成执行计划（tasks.yaml）
cc-spec apply       → SubAgent 并发执行 (仅 Claude Code)
cc-spec accept      → 端到端验收（自动化检查 + 报告）
cc-spec archive     → 归档变更

cc-spec quick-delta → 超简单模式：一步记录
```

## 文档索引

| 文档 | 内容 | 状态 |
|------|------|------|
| [01-背景与目标](./01-背景与目标.md) | 业务目的、上线标准、核心原则、成功指标 | ✅ |
| [02-现状分析](./02-现状分析.md) | Spec-Kit/OpenSpec/auto-dev 现有实现、缺口分析 | ✅ |
| [03-设计方案](./03-设计方案.md) | CLI 命令设计、数据结构、模块架构、SubAgent 集成 | ✅ |
| [04-实施步骤](./04-实施步骤.md) | Gate 分阶段、每阶段步骤与验收标准 | ✅ |
| [05-任务拆分](./05-任务拆分.md) | Wave 任务规划、19 个 Task 详情、并发优化 | ✅ |

## 关键指标

| 指标 | 目标 |
|------|------|
| Token 节省 | ≥40% (SubAgent 共享上下文) |
| 并发能力 | 10 个 SubAgent |
| 工具支持 | 17+ AI 工具 |
| 命令数量 | 8 个 |

## 技术栈

```yaml
语言: Python 3.11+
包管理: uv
CLI 框架: typer
终端美化: rich
HTTP 客户端: httpx
配置格式: YAML
分发方式: GitHub 仓库 (git+https://...)
```

## 安装方式

```bash
# 一次性运行（推荐）
uvx --from git+https://github.com/Waasaabii/cc-spec.git cc-spec init

# 全局安装
uv tool install cc-spec --from git+https://github.com/Waasaabii/cc-spec.git
```

## 任务总览

共 **19 个 Task**，分 **8 个 Wave**，预估 **~580k tokens**。

通过 SubAgent 并发可节省 **~290k tokens (50%)**。

```
Wave 0: 01-INIT (项目初始化)
Wave 1: 02~05 (核心模块, 4 并发)
Wave 2: 06~09 (基础命令, 4 并发)
Wave 3: 10~11 (Delta + 打分, 2 并发)
Wave 4: 12~14 (归档命令, 3 并发)
Wave 5: 15~16 (SubAgent 模块)
Wave 6: 17-CMD-APPLY
Wave 7: 18~19 (测试 + 文档, 2 并发)
```

## 参考资源

- `reference/spec-kit/` - Spec-Kit 源码和模板
- `reference/OpenSpec/` - OpenSpec 规范和实现
- `reference/auto-dev.md` - auto-dev Task 规划格式

---

*文档生成时间: 2024-01*
