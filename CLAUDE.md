# CLAUDE.md

本文件为 Claude Code 在此代码库中工作时提供指导。

## 语言偏好

请使用中文回答问题和编写注释。

## 项目概述

cc-spec 是一个规范驱动的 AI 辅助开发工作流工具，包含两个主要模块：

| 模块 | 路径 | 技术栈 | 说明 |
|------|------|--------|------|
| **桌面应用** | `apps/cc-spec-tool/` | Tauri 2.0 + React + Rust | GUI 可视化与会话管理（**主要开发目标**） |
| **CLI 工具** | `src/cc_spec/` | Python (uv + Typer + Rich) | 命令行工作流工具 |

---

## 桌面应用开发 (apps/cc-spec-tool/)

### 技术栈

- **前端**: React + TypeScript + TailwindCSS
- **后端**: Rust + Tauri 2.0
- **包管理**: bun
- **构建**: Vite + Tauri CLI

### 目录结构

```
apps/cc-spec-tool/
├── src/                        # React 前端
│   ├── App.tsx                 # 主应用入口
│   ├── components/             # UI 组件
│   │   ├── projects/           # 项目管理
│   │   │   ├── ProjectPanel.tsx
│   │   │   ├── ProjectPage.tsx
│   │   │   └── ProjectCodexPanel.tsx  # Codex 会话面板
│   │   ├── icons/Icons.tsx     # 图标组件
│   │   └── chat/               # 聊天组件
│   ├── hooks/                  # React Hooks
│   │   ├── useSettings.ts
│   │   ├── useSkills.ts
│   │   └── useSidecar.ts
│   └── types/                  # TypeScript 类型定义
│       └── viewer.ts
├── src-tauri/                  # Rust 后端
│   ├── src/
│   │   ├── main.rs             # Tauri 入口，注册所有命令
│   │   ├── codex_sessions.rs   # Codex 会话管理（核心模块）
│   │   ├── codex_runner.rs     # Codex CLI 执行器
│   │   ├── claude.rs           # Claude 会话管理
│   │   ├── projects.rs         # 项目管理
│   │   ├── concurrency.rs      # 并发控制
│   │   └── skills.rs           # Skills 配置管理
│   ├── Cargo.toml              # Rust 依赖
│   └── tauri.conf.json         # Tauri 配置
├── sidecar/                    # Python Sidecar
│   └── cc-spec.spec            # PyInstaller 打包配置
├── scripts/                    # 构建脚本
│   ├── build-sidecar.ps1       # 构建 Sidecar
│   ├── build-tauri.mjs         # 构建 Tauri
│   └── dev-frontend.mjs        # 前端开发服务
└── package.json
```

### 开发命令

```bash
cd apps/cc-spec-tool

# 安装依赖
bun install

# 开发模式（前端 + Tauri）
bun run tauri dev

# 仅前端开发
bun run dev

# 类型检查
bun run type-check

# 构建发布版
bun run tauri build

# 构建 Sidecar（打包 cc-spec CLI 为可执行文件）
pwsh scripts/build-sidecar.ps1
```

### 核心模块说明

#### 1. Codex 会话管理 (`codex_sessions.rs`)

负责 Codex 终端会话的生命周期管理：

- **会话创建**: `create_terminal_session()` - 生成终端交互式会话
- **控制消息**: `publish_control_to()` - 发送 pause/resume/kill 控制
- **状态持久化**: `upsert_session_record()` - 写入 sessions.json
- **自动重试**: 崩溃/未知退出时自动重试（最多 3 次）

关键数据结构：
```rust
struct PendingRequest {
    id: String,
    prompt: String,
    requested_by: String,
    created_at_ms: u64,
}

struct SupervisorState {
    project_root: Option<String>,
    pending: Option<PendingRequest>,
    retry_count: u32,
}
```

#### 2. Codex 执行器 (`codex_runner.rs`)

执行 Codex CLI 并管理结果：

- **执行**: `run_codex()` - 同步执行 Codex 命令
- **会话注册**: `register_session()` / `update_session()`
- **结果处理**: `CodexRunResult` 包含 message/exit_code/elapsed_s

#### 3. Claude 会话 (`claude.rs`)

管理 Claude CLI 会话（ConPTY 模式）：

- **启动**: `start_claude()` - 启动 Claude CLI 进程
- **消息发送**: `send_claude_message()`
- **事件广播**: 通过 Tauri 事件系统推送

#### 4. 项目管理 (`projects.rs`)

- `import_project()` - 导入项目
- `list_projects()` - 列出所有项目
- `get_current_project()` / `set_current_project()`

### Tauri 命令注册

所有 Tauri 命令在 `main.rs` 中注册：

```rust
tauri::Builder::default()
    .invoke_handler(tauri::generate_handler![
        // 设置
        get_settings, set_settings,
        // 并发控制
        get_concurrency_status, cancel_queued_task, update_concurrency_limits,
        // 会话管理
        save_history, load_history, load_sessions, stop_session,
        // Codex 终端
        codex_terminal_start, codex_terminal_send_input,
        codex_terminal_pause, codex_terminal_kill,
        // Codex 执行
        codex_pause, codex_resume,
        // 项目
        projects::import_project, projects::list_projects, ...
        // Claude
        claude::start_claude, claude::send_claude_message, ...
    ])
```

### 前端状态管理

主要状态在 `App.tsx` 中管理：

- `projects` / `currentProject` - 项目列表与当前项目
- `runs` - 运行记录
- `activeView` - 当前视图 (projects/project)
- `theme` / `lang` - 主题与语言

### 事件系统

双轨事件通路：
1. **SSE**: `codex.*` 事件（实时流）
2. **Tauri Event**: `agent.*` 事件（Claude 相关）

---

## CLI 工具开发 (src/cc_spec/)

### 开发命令

```bash
# 安装依赖
uv sync --dev

# 运行 CLI
uv run cc-spec --help

# 运行测试
uv run pytest
uv run pytest -k "test_name"

# 代码检查
uv run ruff check src/
uv run mypy src/cc_spec/
```

### 源码结构

- **`commands/`** - CLI 命令实现
- **`core/`** - 核心业务逻辑（config, state, delta, scoring）
- **`subagent/`** - SubAgent 并行执行系统
- **`rag/`** - 智能上下文与增量变更检测（索引/文件片段）
- **`codex/`** - Codex 客户端（通过 cc-spec-tool HTTP API 调用）

### 项目多级索引（v0.2.x）

```bash
# 初始化索引（推荐 L1+L2）
uv run cc-spec init-index --level l1 --level l2

# 更新索引
uv run cc-spec update-index --level l1 --level l2

# 检查索引是否齐全
uv run cc-spec check-index
```

### Codex 调用架构（v0.2.x）

所有 Codex 调用必须通过 cc-spec-tool 的 HTTP API，不再支持直接调用：

```
┌─────────────────────────────────────────────────────┐
│  cc-spec-tool (Tauri)                               │
│  HTTP Server @ 127.0.0.1:38888                      │
│                                                     │
│  POST /api/codex/run       异步提交任务             │
│  GET  /api/codex/sessions  获取会话列表             │
│  POST /api/codex/pause     暂停会话                 │
│  POST /api/codex/kill      终止会话                 │
│  GET  /events              SSE 订阅（接收结果）     │
└─────────────────────────────────────────────────────┘
         ▲
         │ HTTP
┌────────┴────────────────────────────────────────────┐
│  Python CLI (cc-spec)                               │
│                                                     │
│  ToolClient      统一的 Codex 调用入口              │
│  cc-spec cx      CLI 命令封装                       │
│  cc-spec chat    多轮对话模式                       │
│  SubAgentExecutor 并行任务执行                      │
└─────────────────────────────────────────────────────┘
```

**关键模块**：

| 模块 | 位置 | 说明 |
|------|------|------|
| `ToolClient` | `src/cc_spec/codex/tool_client.py` | Python 客户端，调用 tool HTTP API |
| `CodexResult` | `src/cc_spec/codex/models.py` | 执行结果数据类 |
| HTTP API | `apps/cc-spec-tool/src-tauri/src/main.rs` | Rust HTTP 服务 |

**重要约束**：

- ❌ 不再支持直接调用 Codex CLI
- ✅ 必须通过 `get_tool_client()` 获取客户端
- ❌ tool 未运行时直接报错退出，无 fallback

**CLI 命令**：

```bash
# 直接执行任务
cc-spec cx "任务描述"

# 使用子命令
cc-spec cx run "任务描述" --timeout 600

# 管理会话
cc-spec cx list
cc-spec cx pause <session_id>
cc-spec cx kill <session_id>

# 多轮对话
cc-spec chat -m "你好"
cc-spec chat -m "继续" -r <session_id>
```

---

## 关键约定

### Tauri 开发

- Rust 后端使用 `#[tauri::command]` 暴露命令
- 前端通过 `invoke()` 调用后端命令
- 会话状态持久化到 `.cc-spec/runtime/codex/sessions.json`
- 使用 `serde_json` 序列化/反序列化

### CLI 开发

- 使用 Typer + Rich 构建 CLI
- 配置文件格式为 YAML
- Delta 格式：`ADDED:`、`MODIFIED:`、`REMOVED:`、`RENAMED: old → new`
- 任务 ID：`W<wave>-T<task>` 格式

---

## 调试技巧

### Tauri 后端调试

```bash
# 查看 Rust 日志
RUST_LOG=debug bun run tauri dev

# 查看 Codex 日志
cat .cc-spec/runtime/codex/*.log
```

### 前端调试

- 使用 Chrome DevTools (Tauri 开发模式自动打开)
- React DevTools 扩展

### 会话状态

```bash
# 查看当前会话状态
cat .cc-spec/runtime/codex/sessions.json | jq
```
