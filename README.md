# cc-spec

**规范驱动的 AI 辅助开发工作流 CLI 工具**

[English](./docs/README.en.md) | 中文

[![Version](https://img.shields.io/badge/version-0.1.8-blue.svg)](https://github.com/Waasaabii/cc-spec)

---

## 简介

cc-spec 是一个整合了 [OpenSpec](https://github.com/hannesrudolph/openspec) 和 [Spec-Kit](https://github.com/github/spec-kit) 精华的规范驱动开发 CLI 工具，面向 **Claude Code 编排 + Codex 执行** 的规格驱动开发工作流。

## ps
```typescript
openspec缺少打分环节。speckit又对模型的改造太大，完全忽略了模型能力，所以两个都不喜欢用
你们说我是不是贱
虽然一开始就是从自己的工作流优化的，但自己的工作流又缺少openspec和speckit的牛逼之处

```

### 核心特性

- **8 步标准工作流**: `init → kb init/update → specify → clarify → plan → apply → checklist → archive`
- **Claude 编排 / Codex 执行（v0.1.6）**: Claude 只负责编排，Codex CLI 负责产出代码/文件
- **智能上下文 + RAG 知识库（v0.1.6）**: ChromaDB 向量库 + fastembed embeddings + workflow records
- **Smart Chunking（v0.1.8）**: AST / Line / LLM 三层切片策略，速度提升、token 成本降低
- **Delta 变更追踪**: ADDED / MODIFIED / REMOVED / RENAMED 格式
- **打分验收机制**: checklist 打分 ≥80 通过，否则打回 apply
- **超简单模式**: `quick-delta` 一步生成变更记录

---

## 安装

需要先安装 [uv](https://docs.astral.sh/uv/)。

```bash
# 方式 1: 一次性运行（推荐）
uvx --from git+https://github.com/Waasaabii/cc-spec.git cc-spec init

# 方式 2: 全局安装
uv tool install cc-spec --from git+https://github.com/Waasaabii/cc-spec.git

# 升级到最新版本
uv tool install cc-spec --force --from git+https://github.com/Waasaabii/cc-spec.git
```

---

## 快速开始

```bash
# 1. 初始化项目（生成 Claude Code 的 /cc-spec:* 命令）
cc-spec init

# 2. （推荐）构建/更新知识库（任选其一）
cc-spec kb init
# 或在 Claude Code 中执行：
# /cc-spec:init

# 3. 创建变更规格
cc-spec specify add-user-auth

# 4. 澄清需求/返工
cc-spec clarify

# 5. 生成执行计划
cc-spec plan

# 6. 执行任务（SubAgent 并发）
cc-spec apply

# 7. 验收打分
cc-spec checklist

# 8. 归档变更
cc-spec archive
```

---

## 工作流（细化）

> 核心原则：**Claude 负责编排与审核，Codex 负责落地代码**；KB 作为上下文桥梁。

| 步骤 | 目的 | 主要命令 | 关键产物 |
|------|------|----------|----------|
| 1. init | 初始化项目结构与配置 | `cc-spec init` | `.cc-spec/`、`config.yaml` |
| 2. kb init/update | 构建/更新知识库（推荐） | `cc-spec kb init` / `cc-spec kb update` | `.cc-spec/vectordb/`、workflow records |
| 3. specify | 需求规格与范围 | `cc-spec specify <change>` | `.cc-spec/changes/<change>/proposal.md` |
| 4. clarify | 澄清需求或标记返工 | `cc-spec clarify [task-id]` | proposal 澄清记录 / 任务返工标记 |
| 5. plan | 生成可执行计划 | `cc-spec plan` | `.cc-spec/changes/<change>/tasks.yaml` |
| 6. apply | 并发执行任务 | `cc-spec apply` | 任务状态更新、执行记录 |
| 7. checklist | 验收打分（默认 ≥80 通过） | `cc-spec checklist` | checklist 报告 |
| 8. archive | 归档并合并 Delta specs | `cc-spec archive` | `.cc-spec/changes/archive/...` |

### 每步要点

- **init**：只负责本地结构与配置，不入库。
- **kb init/update**：生成/更新 KB；推荐先 `kb preview` 再入库。
- **specify**：写清 Why / What Changes / Impact / Success Criteria，避免实现细节。
- **clarify**：对高影响歧义提问并写回 proposal；或对任务标记返工。
- **plan**：输出 `tasks.yaml`（Gate-0 + Wave 并发结构、依赖、checklist）。
- **apply**：按 Wave 并发执行；失败用 `--resume` 继续。
- **checklist**：按四维度打分（功能/质量/测试/文档），低于阈值会回到 apply/clarify。
- **archive**：合并 Delta specs 到主 specs 并归档变更目录。

### 超简单模式

```bash
# 小改动、紧急修复：一步记录
cc-spec quick-delta "修复登录页面样式问题"
```

---

## 在 AI 工具中使用

cc-spec init 会生成 Claude Code 的命令文件到 `.claude/commands/cc-spec/`，在 Claude Code 中可直接调用：

- `/cc-spec:init`（构建/更新 KB：先 scan，再入库，默认使用 Smart Chunking）
- `/cc-spec:specify` / `/cc-spec:clarify` / `/cc-spec:plan` / `/cc-spec:apply` / `/cc-spec:checklist` / `/cc-spec:archive`

---

## 文档与规范产物

- `docs/plan/` 仅供人类阅读的规划文档，不作为运行时配置来源。
- `base-template.yaml` 的 `template_mapping` 仅用于实现指引，运行时使用内置模板渲染。
- `SKILL.md` / `AGENTS.md` 是 `cc-spec init` 生成的 CLI/Agent 指令产物。

---

## 设计来源与技术参考

cc-spec 整合了以下项目的设计精华：

### 工作流设计

| 来源 | 贡献 |
|------|------|
| **[OpenSpec](https://github.com/hannesrudolph/openspec)** | Delta 变更追踪、归档规范、多 AI 工具配置、AGENTS.md 标准 |
| **[Spec-Kit](https://github.com/github/spec-kit)** | CLI 技术栈 (uv + typer + rich)、模板系统、clarify 澄清流程、打分机制 |
| **auto-dev** | SubAgent 并发执行、Wave 任务规划格式 |

### RAG / 代码切片（v0.1.6）

| 来源 | 贡献 |
|------|------|
| **[astchunk](https://github.com/yilinjz/astchunk)** | AST-based 代码切片核心算法，保留语法结构边界 |
| **[tree-sitter-language-pack](https://github.com/AEFeinstein/tree-sitter-language-pack)** | 100+ 编程语言的 tree-sitter parser 支持 |

### 模板来源

cc-spec 使用的模板基于 OpenSpec 和 Spec-Kit 的模板设计：

- **规格模板 (spec-template.md)**: 基于 Spec-Kit 的 User Story + Given/When/Then 格式
- **计划模板 (plan-template.md)**: 基于 Spec-Kit 的 Phase 分阶段设计
- **任务模板 (tasks-template.md)**: 基于 auto-dev 的 Wave/Task-ID 格式
- **Delta 格式**: 基于 OpenSpec 的 ADDED/MODIFIED/REMOVED/RENAMED 规范
- **命令文件**: 基于 OpenSpec 的多工具适配器模式

---

## 文档

详细设计文档请参见 [docs/plan/cc-spec/](./docs/plan/cc-spec/README.md)。

---

## 致谢

本项目深受 **[John Lam](https://github.com/jflam)** 的工作和研究的影响，并以他的作品和研究为基础。

特别感谢：

- **[OpenSpec](https://github.com/hannesrudolph/openspec)** - Hannes Rudolph 创建的规范驱动开发框架，提供了优秀的 Delta 变更追踪和多工具支持设计
- **[Spec-Kit](https://github.com/github/spec-kit)** - GitHub 团队（Den Delimarsky、John Lam 等）创建的规范驱动开发工具包，提供了成熟的 CLI 框架和模板系统
- **[astchunk](https://github.com/yilinjz/astchunk)** - Yilin Zhang 等人创建的 AST-based 代码切片库，基于 [cAST 论文](https://arxiv.org/abs/2506.15655)，为 cc-spec 的 Smart Chunking 提供了核心算法
- **[tree-sitter-language-pack](https://pypi.org/project/tree-sitter-language-pack/)** - 提供 100+ 编程语言的 tree-sitter parser 支持

---

## 更新日志

### v0.1.8 (2025-01)

- **Smart Chunking**: AST-based 代码切片（0 token，100x 速度提升）
- **KB 配置优化**: 三层策略调度（AST → Line → LLM）
- **规范模板更新**: base-template.yaml v1.0.8

### v0.1.6 (2025-01)

- **智能上下文**: ContextProvider 自动注入相关代码
- **增量更新**: KB 支持 git diff 检测变更文件

### v0.1.4 (2025-01)

- **四维度打分机制**: 功能完整性 (30%)、代码质量 (25%)、测试覆盖 (25%)、文档同步 (20%)
- **任务锁机制**: 防止多 agent 同时执行同一任务导致冲突
- **Agent ID 追踪**: 执行结果中包含 agent_id、wave、retry_count 等字段
- **quick-delta 增强**: 自动解析 git diff，显示文件变更列表和统计信息

### v0.1.3 (2025-01)

- **多工具配置**: `agents.enabled[]` 支持同时启用多个 AI 工具
- **17+ AI 工具**: 新增 tabnine, aider, devin, replit, cody, supermaven, kilo, auggie
- **模板下载**: `update --templates` 支持从远程更新模板

### v0.1.2 (2024-12)

- **导航命令**: `list`, `goto`, `update` 三个新命令
- **ID 系统**: C-001, S-001, A-001 格式的变更/规范/归档 ID
- **Profile 系统**: SubAgent 配置支持 quick/heavy/explore 等多种配置

### v0.1.0 (2024-11)

- 初始版本
- 7 步标准工作流
- SubAgent 并发执行
- Delta 变更追踪
- 打分验收机制

---

## 许可证

MIT License
