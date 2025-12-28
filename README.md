# cc-spec

**规范驱动的 AI 辅助开发工作流工具**

[English](./docs/README.en.md) | 中文

[![Version](https://img.shields.io/badge/version-0.2.1-blue.svg)](https://github.com/Waasaabii/cc-spec)

---

## 简介

cc-spec 是一个整合了 [OpenSpec](https://github.com/hannesrudolph/openspec) 和 [Spec-Kit](https://github.com/github/spec-kit) 精华的规范驱动开发工具，面向 **Claude Code 编排 + Codex 执行** 的规格驱动开发工作流。

项目包含两个主要模块：

| 模块 | 路径 | 技术栈 | 说明 |
|------|------|--------|------|
| **CLI 工具** | `src/cc_spec/` | Python (uv + Typer + Rich) | 命令行工作流工具 |
| **桌面应用** | `apps/cc-spec-tool/` | Tauri + React + Rust | GUI 可视化与会话管理 |

### 核心特性

- **8 步标准工作流**: `init → init-index/update-index → specify → clarify → plan → apply → accept → archive`
- **Claude 编排 / Codex 执行（v0.1.6）**: Claude 只负责编排，Codex CLI 负责产出代码/文件
- **多级索引 + 智能上下文（v0.2.x）**: PROJECT_INDEX / FOLDER_INDEX + related_files 手动引用
- **Delta 变更追踪**: ADDED / MODIFIED / REMOVED / RENAMED 格式
- **打分验收机制**: checklist 打分 ≥80 通过，否则打回 apply
- **超简单模式**: `quick-delta` 一步生成变更记录

---

## 桌面应用 (cc-spec-tool)

`apps/cc-spec-tool/` 是基于 Tauri 2.0 构建的桌面 GUI 应用，提供可视化界面管理 Codex/Claude 会话。

### 功能特性

- **项目管理**: 导入、切换、删除项目
- **Codex 会话管理**: 终端/ConPTY relay 模式，支持会话监控与自动重试
- **Claude 集成**: 启动和管理 Claude CLI 会话
- **任务调度**: 并发控制、队列管理
- **实时状态**: SSE 事件流 + sessions.json 双轨状态同步

### 技术架构

```
apps/cc-spec-tool/
├── src/                    # React 前端
│   ├── App.tsx             # 主应用入口
│   ├── components/         # UI 组件
│   │   ├── projects/       # 项目管理组件
│   │   └── icons/          # 图标组件
│   ├── hooks/              # React Hooks
│   └── types/              # TypeScript 类型定义
├── src-tauri/              # Rust 后端
│   ├── src/
│   │   ├── main.rs         # Tauri 入口，注册所有命令
│   │   ├── codex_sessions.rs   # Codex 会话管理（核心）
│   │   ├── codex_runner.rs     # Codex CLI 执行器
│   │   ├── claude.rs           # Claude 会话管理
│   │   ├── projects.rs         # 项目管理
│   │   └── concurrency.rs      # 并发控制
│   └── tauri.conf.json     # Tauri 配置
├── sidecar/                # Python Sidecar（cc-spec CLI 打包）
└── scripts/                # 构建脚本
```

### 开发命令

```bash
cd apps/cc-spec-tool

# 安装依赖
bun install

# 开发模式
bun run tauri dev

# 构建发布版
bun run tauri build

# 构建 Sidecar（打包 cc-spec CLI）
pwsh scripts/build-sidecar.ps1
```

---

## CLI 工具安装

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

# 2. （推荐）初始化/更新多级索引（PROJECT_INDEX/FOLDER_INDEX）
cc-spec init-index --level l1 --level l2
# 或在 Claude Code 中执行：/cc-spec:init

# 3. 创建变更规格
cc-spec specify add-user-auth

# 4. 澄清需求/返工
cc-spec clarify

# 5. 生成执行计划
cc-spec plan

# 6. 执行任务（SubAgent 并发）
cc-spec apply

# 7. 端到端验收（lint/test/build/type-check）
cc-spec accept

# 8. 归档变更
cc-spec archive
```

---

## 工作流（细化）

> 核心原则：**Claude 负责编排与审核，Codex 负责落地代码**；上下文以多级索引与相关文件引用为准。

| 步骤 | 目的 | 主要命令 | 关键产物 |
|------|------|----------|----------|
| 1. init | 初始化项目结构与配置 | `cc-spec init` | `.cc-spec/`、`config.yaml` |
| 2. init-index/update-index | 生成/更新项目多级索引（推荐） | `cc-spec init-index` / `cc-spec update-index` | `PROJECT_INDEX.md`、`FOLDER_INDEX.md`、`.cc-spec/index/status.json` |
| 3. specify | 需求规格与范围 | `cc-spec specify <change>` | `.cc-spec/changes/<change>/proposal.md` |
| 4. clarify | 澄清需求或标记返工 | `cc-spec clarify [task-id]` | proposal 澄清记录 / 任务返工标记 |
| 5. plan | 生成可执行计划 | `cc-spec plan` | `.cc-spec/changes/<change>/tasks.yaml` |
| 6. apply | 并发执行任务 | `cc-spec apply` | 任务状态更新、执行记录 |
| 7. accept | 端到端验收（lint/test/build/type-check） | `cc-spec accept` | `acceptance-report.md`（可选） |
| 8. archive | 归档并合并 Delta specs | `cc-spec archive` | `.cc-spec/changes/archive/...` |

### 每步要点

- **init**：只负责本地结构与配置，不入库。
- **init-index/update-index**：生成/更新多级索引（PROJECT_INDEX/FOLDER_INDEX）。
- **specify**：写清 Why / What Changes / Impact / Success Criteria，避免实现细节。
- **clarify**：对高影响歧义提问并写回 proposal；或对任务标记返工。
- **plan**：输出 `tasks.yaml`（Gate-0 + Wave 并发结构、依赖、checklist）。
- **apply**：按 Wave 并发执行；失败用 `--resume` 继续。
- **accept**：端到端验收；未通过不得归档，必须补齐后回到 apply/clarify。
- **archive**：合并 Delta specs 到主 specs 并归档变更目录。

### 超简单模式

```bash
# 小改动、紧急修复：一步记录
cc-spec quick-delta "修复登录页面样式问题"
```

说明：
- quick-delta 会生成 mini-proposal.md 并直接归档

---

## 测试

默认分层运行（integration 需显式开启）：

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

---

## 在 AI 工具中使用

cc-spec init 会生成 Claude Code 的命令文件到 `.claude/commands/cc-spec/`，在 Claude Code 中可直接调用：

- `/cc-spec:init`（初始化/更新项目索引：生成 PROJECT_INDEX/FOLDER_INDEX）
- `/cc-spec:specify` / `/cc-spec:clarify` / `/cc-spec:plan` / `/cc-spec:apply` / `/cc-spec:accept` / `/cc-spec:archive`

---

## Codex 会话状态管理

cc-spec 提供完整的 Codex 会话状态持久化和可视化机制，支持 Claude 高效监控多个并行 Codex 会话。

### 架构概览

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│   Claude Code   │     │      cc-spec         │     │     Viewer      │
│   (编排者)       │     │   (会话管理)          │     │   (可视化)       │
└────────┬────────┘     └──────────┬───────────┘     └────────┬────────┘
         │                         │                          │
         │  cc-spec chat -m "..."  │                          │
         │ ───────────────────────>│                          │
         │                         │                          │
         │                         │ 写入 sessions.json       │
         │                         │ ─────────────────────>   │
         │                         │                          │
         │                         │ SSE 事件流               │
         │                         │ ═══════════════════════> │
         │                         │                          │
         │  [STATUS] state=done    │                          │
         │ <───────────────────────│                          │
         │                         │                          │
         │  cat sessions.json      │  load_sessions()         │
         │ ───────────────────────>│ <─────────────────────── │
         │                         │                          │
```

### 数据文件

会话状态存储在项目目录下：

```
.cc-spec/
└── runtime/
    └── codex/
        ├── sessions.json    # 会话状态（持久化）
        └── sessions.lock    # 文件锁（并发安全）
```

### sessions.json 结构

```json
{
  "schema_version": 1,
  "updated_at": "2025-01-15T10:30:00+00:00",
  "sessions": {
    "019b459f-2c65-7b83-834c-44e8a721272d": {
      "session_id": "019b459f-2c65-7b83-834c-44e8a721272d",
      "state": "running",
      "task_summary": "修改 App.tsx 添加会话状态显示...",
      "message": null,
      "exit_code": null,
      "elapsed_s": null,
      "pid": 12345,
      "created_at": "2025-01-15T10:25:00+00:00",
      "updated_at": "2025-01-15T10:30:00+00:00"
    }
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | string | Codex 会话唯一标识（UUID v7） |
| `state` | string | 状态：`running` / `done` / `failed` / `idle` |
| `task_summary` | string | 任务摘要（前 200 字符） |
| `message` | string | 完成消息或错误信息 |
| `exit_code` | int | 退出码（0=成功） |
| `elapsed_s` | float | 执行耗时（秒） |
| `pid` | int | Codex 进程 PID（运行中有值，完成后为 null） |
| `created_at` | string | 会话创建时间（ISO 8601） |
| `updated_at` | string | 最后更新时间（ISO 8601） |

### 状态流转

```
                    ┌─────────┐
                    │ running │ ←── 会话开始
                    └────┬────┘
                         │
           ┌─────────────┼─────────────┐
           ↓             ↓             ↓
      ┌────────┐    ┌────────┐    ┌────────┐
      │  done  │    │ failed │    │  idle  │
      └────────┘    └────────┘    └────────┘
       成功完成       执行失败      60s 无输出
```

### Claude 高效监控

Claude 可以通过读取单个 JSON 文件快速获取所有会话状态：

```bash
# 一次性获取所有会话状态
cat .cc-spec/runtime/codex/sessions.json

# 继续未完成的会话
cc-spec chat -m "继续" -r <session_id>
```

### chat 命令结构化输出

非交互模式下，chat 命令输出结构化状态行便于 Claude 解析：

```
[STATUS] state=done elapsed=60s session=019b459f-...
[Codex] 任务完成消息...
```

### Viewer 集成

cc-spec-tool 每 5 秒自动读取 sessions.json 并合并显示：

- **状态标签**: Running / Done / Failed / Idle
- **任务摘要**: 显示 task_summary 前 50 字符
- **执行时间**: 优先显示 sessions.json 的 elapsed_s
- **SSE 流合并**: 实时事件流 + 持久化状态双重保障
- **停止按钮**: 运行中的会话可一键终止

### 停止会话功能

Viewer 支持从界面直接停止正在运行的 Codex 会话：

```
┌─────────────────┐                ┌─────────────────┐
│     Viewer      │   stop_session │    cc-spec      │
│   (点击停止)     │ ─────────────> │  sessions.json  │
└─────────────────┘                └────────┬────────┘
                                            │ 读取 pid
                                            ↓
                                   ┌─────────────────┐
                                   │  taskkill/kill  │
                                   │   终止进程       │
                                   └─────────────────┘
```

**工作原理**：
1. cc-spec 启动 Codex 时将进程 PID 写入 sessions.json
2. Viewer 读取 sessions.json 获取会话的 PID
3. 点击停止按钮时，Viewer 调用系统命令终止进程
   - Windows: `taskkill /PID <pid> /F`
   - Unix/Linux: `kill -9 <pid>`
4. 会话完成后自动清除 PID

### 并发安全

SessionStateManager 使用跨平台文件锁确保并发写入安全：

- **Windows**: `msvcrt.locking()`
- **Unix/Linux**: `fcntl.flock()`
- **原子写入**: 先写临时文件，再 `os.replace()` 原子替换

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

### v0.1.9 (2025-01)

- **Codex 会话状态管理**: SessionStateManager 持久化会话状态到 sessions.json
- **Viewer sessions.json 集成**: 每 5 秒自动读取并合并显示会话状态
- **Viewer 停止会话功能**: 一键终止运行中的 Codex 会话（支持 Windows/Unix）
- **PID 追踪**: 会话记录包含进程 PID，支持精确终止
- **chat 结构化输出**: `[STATUS] state=done elapsed=60s session=...` 格式便于 Claude 解析
- **跨平台文件锁**: Windows msvcrt / Unix fcntl 确保并发写入安全
- **idle 状态检测**: 60 秒无输出自动标记为 idle 状态

### v0.1.8 (2025-01)

- **Smart Chunking**: AST-based 代码切片（0 token，100x 速度提升）
- **配置优化**: 三层策略调度（AST → Line → LLM）
- **规范模板更新**: base-template.yaml v1.0.8

### v0.1.6 (2025-01)

- **智能上下文**: ContextProvider 自动注入相关代码
- **增量更新**: 支持 git diff 检测变更文件

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
