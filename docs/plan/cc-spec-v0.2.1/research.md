# research.md - v0.2.1 调研报告

**调研时间**: 2025-01-22
**调研范围**: 参考项目分析、技术可行性、架构设计讨论

---

## 1. 参考项目分析

### 1.1 opcode

**项目地址**: reference/opcode

**技术栈**:
- 前端：React 18 + TypeScript + Vite 6 + Tailwind CSS v4 + shadcn/ui
- 后端：Rust + Tauri 2
- 数据库：SQLite (rusqlite)
- 包管理：Bun

**核心功能**:
1. 项目/会话管理（读取 ~/.claude/projects/）
2. CC Agents（自定义 Agent 执行任务）
3. 使用统计（API 成本、Token 分析）
4. MCP Server 管理
5. 时间线/检查点（会话版本控制）
6. CLAUDE.md 编辑器

**调用 CC 方式**:
```rust
// src-tauri/src/commands/claude.rs
Command::new(claude_path)
    .args(["--print", "--output-format", "stream-json", ...])
    .spawn()

// 读取 stdout/stderr
let mut lines = stdout_reader.lines();
while let Ok(Some(line)) = lines.next_line().await {
    app.emit("claude-output", &line);
}
```

**可借鉴**:
- UI 交互设计（项目列表、设置页面布局）
- 进程管理（spawn + emit 事件）
- 设置页面结构

### 1.2 claudia

**项目地址**: reference/claudia

**特点**: opcode 的 monorepo 版本，提供 npm 包

**包结构**:
```
packages/
├── claudia-core/    # @claudia/core - React 组件库
├── claudia-cli/     # @claudia/cli - CLI 工具
└── create-claudia-app/  # 脚手架
```

**@claudia/core 提供**:
- UI 组件：Button, Card, Dialog, Input, Select, Tabs, Toast...
- Claude 专用组件：ClaudeVersionSelector, AgentExecution, SessionOutputViewer
- API 封装：通过 `invoke()` 调用 Tauri 后端

**可借鉴**:
- 调用 CC 的 Tauri 命令封装
- 组件化设计思路

**限制**:
- @claudia/core 依赖 Tauri 后端，不能单独在纯 Web 使用

---

## 2. 现有 cc-spec-viewer 分析

**项目地址**: apps/cc-spec-viewer

**技术栈**:
- 前端：React + TypeScript + Vite + Tailwind CSS
- 后端：Rust + Tauri 2

**当前功能**:
1. SSE 服务器接收 Codex 输出
2. 显示 Codex 执行状态和日志
3. 读取 sessions.json 显示会话状态
4. 停止运行中的会话（taskkill/kill）

**架构**:
```
终端 cc-spec chat -> Codex -> SSE -> Viewer(显示)
                          -> sessions.json -> Viewer(读取)
```

**缺口**:
1. 不能直接启动 CC，只能被动接收
2. 无法区分 CC 和 CX 的输出
3. 控制能力有限（只有停止）
4. 无项目管理功能

---

## 3. cc-spec CLI 分析

**会话管理（v0.1.9）**:
```
.cc-spec/runtime/codex/
├── sessions.json    # 会话状态
└── sessions.lock    # 文件锁
```

**sessions.json 结构**:
```json
{
  "schema_version": 1,
  "sessions": {
    "<session_id>": {
      "state": "running|done|failed|idle",
      "task_summary": "...",
      "pid": 12345,
      "elapsed_s": 60.0
    }
  }
}
```

**chat 命令**:
```bash
cc-spec chat -m "消息"           # 单次消息
cc-spec chat -r <session_id> -m  # 继续会话
cc-spec chat -s                  # 显示 session_id
```

**可复用**:
- sessions.json 机制
- chat 命令的 Codex 调用逻辑
- SessionStateManager 会话状态管理

---

## 4. 本地翻译功能调研

详见：[viewer-local-translation-research.md](../../viewer-local-translation-research.md)

### 4.1 HuggingFace API 可行性

| 能力 | 状态 | 说明 |
|------|------|------|
| 查询翻译模型列表 | ✅ 可用 | `?filter=translation` 参数 |
| 筛选 safetensors 格式 | ✅ 可用 | `?filter=safetensors` 参数 |
| 获取模型文件大小 | ✅ 可用 | 通过 `siblings` 字段获取 |
| 按下载量排序 | ✅ 可用 | `?sort=downloads` 参数 |

### 4.2 Candle 框架支持

| 模型类型 | 支持状态 | 说明 |
|----------|----------|------|
| T5 系列 | ✅ 官方支持 | 包括 t5-small/base/large |
| Marian MT | ✅ 官方支持 | Helsinki-NLP 系列 |
| MADLAD400 | ✅ 官方支持 | 400+ 语言翻译 |

### 4.3 推荐模型

**默认推荐**: `google-t5/t5-small`
- 大小：242 MB（最小）
- Candle 官方支持
- 下载量最高（2.6M）

---

## 5. 与 CX 讨论的架构设计

### 5.1 数据存储位置

```
%LOCALAPPDATA%/cc-spec-viewer/
├── registry.db              # SQLite 项目注册表
├── projects/
│   └── <project_id>/
│       ├── sessions/        # 会话历史
│       ├── vector/          # 向量数据（可选）
│       └── config.json      # 项目配置
├── models/                  # 翻译模型（可选）
└── settings.json            # 全局设置
```

### 5.2 进程通信方案

| 进程 | 通信方式 | 说明 |
|------|----------|------|
| CC (Claude Code) | PTY/ConPTY + stdout/stderr | 交互式终端模拟 |
| CX (Codex) | JSON-RPC over stdin/stdout | 结构化控制命令 |
| cc-spec sidecar | Tauri Command | 同步调用 |

### 5.3 CC 进程管理

```rust
// 探测 CC 路径
fn detect_claude_path() -> Option<PathBuf> {
    // 1. 检查 PATH
    // 2. 检查常见安装位置
    // 3. 检查 npm global
    // 4. 返回 None 让用户手动配置
}

// 启动 CC
Command::new(claude_path)
    .args(["--print", "--output-format", "stream-json"])
    .current_dir(project_path)
    .spawn()
```

### 5.4 CX 控制协议

```json
// 暂停
{"jsonrpc": "2.0", "method": "pause", "id": 1}

// 继续
{"jsonrpc": "2.0", "method": "resume", "id": 2}

// 停止
{"jsonrpc": "2.0", "method": "stop", "id": 3}

// 响应
{"jsonrpc": "2.0", "result": {"status": "paused"}, "id": 1}
```

### 5.5 设置页面结构

**全局设置**:
- cc_path: Claude Code 可执行文件路径
- cx_path: Codex 可执行文件路径（如果需要）
- data_root: 数据存储根目录

**项目设置**:
- vector_enabled: 是否启用向量
- translation_model: 翻译模型 ID
- cx_concurrency: CX 并发数

---

## 6. 技术可行性总结

| 功能 | 可行性 | 方案 |
|------|--------|------|
| CC 进程管理 | ✅ 可行 | 参考 opcode/claudia 的 spawn 实现 |
| CX 输出分离 | ✅ 可行 | 独立面板 + 事件分发 |
| CX 细粒度控制 | ⚠️ 需扩展 | 需在 cc-spec 中实现暂停/继续协议 |
| Sidecar 打包 | ✅ 可行 | PyInstaller + Tauri externalBin |
| 项目管理 | ✅ 可行 | SQLite 注册表 + 本地存储 |
| 向量管理 | ✅ 可行 | 复用现有 cc-spec kb 命令 |
| 本地翻译 | ✅ 可行 | Candle + t5-small |

---

## 7. 差距分析

| 功能 | 现状 | 目标 | 工作量 |
|------|------|------|--------|
| 启动 CC | 终端手动 | Viewer 启动 | 中 |
| CC 输出 | 无 | 主对话区 | 中 |
| CX 输出 | SSE 显示 | 分离显示 | 小 |
| CX 控制 | 停止 | 暂停/继续/停止 | 中 |
| 项目管理 | 无 | 导入/列表 | 中 |
| 设置页面 | 无 | 向量/翻译/CC路径 | 中 |
| cc-spec 分发 | CLI 安装 | sidecar 打包 | 大 |
