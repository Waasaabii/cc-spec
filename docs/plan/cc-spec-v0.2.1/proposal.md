# proposal.md - viewer-main-entry

**变更 ID**: viewer-main-entry
**创建时间**: 2025-01-22
**状态**: Draft

---

## 1. 背景与目标

### 问题陈述

1. **终端操作繁琐**：用户需要在终端执行 cc，再通过 cc-spec chat 调用 cx，流程分散
2. **输出分离困难**：cc 和 cx 的输出混在一起，难以区分编排者和执行者的信息
3. **控制能力有限**：现有 Viewer 只能显示和停止会话，缺乏细粒度控制
4. **项目嵌入问题**：.cc-spec 目录嵌入项目，污染项目结构

### 业务价值

- 用户在 Viewer 内完成 80% 的操作，无需切换终端
- cc/cx 输出清晰分离，提升可读性
- 支持暂停/继续/停止 cx 任务，增强控制粒度
- 项目导入即获得 cc-spec 工作流，零配置

### 技术约束

| 约束 | 说明 |
|------|------|
| cc 不打包 | 调用用户已安装的 Claude Code，支持自动探测或手动配置路径 |
| 项目不污染 | cc-spec 数据存储在 Viewer 本地（%LOCALAPPDATA%/cc-spec-viewer/） |
| CLI 保留 | 原有 `uv run cc-spec` 命令行方式照常可用 |
| sidecar 大小 | cc-spec PyInstaller 打包后 < 50MB |

---

## 2. 用户故事

### 故事 1 - Viewer 内与 CC 对话 (优先级: P1)

用户打开 Viewer，选择已导入的项目，在主对话区直接输入需求，与 Claude Code 对话。

**为什么是这个优先级**: 核心功能，Viewer 作为主入口的基础。

**验收场景**:

1. **给定** 已导入项目，**当** 用户在对话区输入消息并发送，**那么** CC 进程启动并返回响应，响应实时显示在对话区
2. **给定** CC 正在响应，**当** 用户点击停止按钮，**那么** CC 进程在 1s 内终止

---

### 故事 2 - CX 任务面板显示与控制 (优先级: P1)

当 CC 调用 cc-spec 执行任务时，CX 任务在侧边面板显示，用户可手动控制。

**为什么是这个优先级**: 核心功能，实现 cc/cx 输出分离和细粒度控制。

**验收场景**:

1. **给定** CC 调用 cc-spec apply 执行任务，**当** CX 启动，**那么** 任务状态和输出显示在侧边面板，不混入主对话区
2. **给定** CX 任务正在执行，**当** 用户点击暂停/继续/停止按钮，**那么** CX 进程在 1s 内响应控制命令

---

### 故事 3 - 项目导入与管理 (优先级: P2)

用户可导入本地项目，导入后自动获得 cc-spec 工作流能力。

**为什么是这个优先级**: 支撑性功能，为 P1 功能提供项目上下文。

**验收场景**:

1. **给定** 用户点击导入项目，**当** 选择本地目录，**那么** 项目添加到项目列表，元数据存储在 Viewer 本地
2. **给定** 已导入项目，**当** 用户选择该项目，**那么** 可直接在 Viewer 内使用 cc-spec 工作流

---

### 故事 4 - 向量知识库管理 (优先级: P3)

用户可在设置页面为项目启用向量知识库，启用后 CX 强制使用向量查询。

**为什么是这个优先级**: 可选增强功能，不影响核心流程。

**验收场景**:

1. **给定** 项目设置页面，**当** 用户开启向量功能并点击初始化，**那么** 调用 cc-spec kb init 创建知识库
2. **给定** 向量功能已开启，**当** CX 执行任务，**那么** CX 被强制使用 cc-spec kb query 查询上下文

---

### 故事 5 - 本地翻译功能 (优先级: P3)

用户可在设置页面下载翻译模型，对 CX 输出进行本地翻译。

**为什么是这个优先级**: 可选增强功能，独立于核心流程。

**验收场景**:

1. **给定** 设置页面翻译选项，**当** 用户选择模型并下载，**那么** 模型下载到本地，显示下载进度
2. **给定** 翻译功能已启用，**当** CX 输出英文内容，**那么** 可点击翻译按钮，使用本地模型翻译为中文

---

### 边界情况

- 当 CC 路径探测失败时会发生什么？→ 提示用户手动配置路径
- 当 CX 进程僵死无响应时如何处理？→ 超时检测 + 强制终止（taskkill/kill -9）
- 当向量初始化失败时？→ 显示错误信息，允许重试

---

## 3. 技术决策

### 3.1 架构设计

```
v0.2.1 架构：
  Viewer(主入口) -> CC(编排者) -> cc-spec(sidecar) -> CX(执行者)
                       ↓                                   ↓
                  主对话区显示                        侧边面板显示
```

**决策**: Viewer 作为统一入口，CC 作为编排者调用 cc-spec，cc-spec 管理 CX 执行。

**理由**:
- 保持 cc-spec 的编排能力不变
- 利用 Tauri 的进程管理能力
- 实现 UI 层面的输出分离

### 3.2 模块划分

```
apps/cc-spec-viewer/
├── src/                    # React 前端
│   ├── components/
│   │   ├── chat/           # CC 对话组件
│   │   ├── tasks/          # CX 任务面板组件
│   │   ├── projects/       # 项目管理组件
│   │   └── settings/       # 设置页面组件
│   └── pages/
├── src-tauri/              # Rust 后端
│   └── src/
│       ├── commands/
│       │   ├── claude.rs   # CC 进程管理
│       │   ├── codex.rs    # CX 进程管理（复用现有）
│       │   ├── project.rs  # 项目管理
│       │   └── settings.rs # 设置管理
│       └── lib.rs
└── bin/                    # Sidecar
    └── cc-spec-{target}.exe
```

### 3.3 数据模型

- **Project**: 导入的项目，包含路径、名称、向量开关、翻译配置
- **Session**: CC 对话会话，关联项目
- **Task**: CX 执行任务，关联会话，包含状态和输出

### 3.4 接口设计

```rust
// CC 进程管理
#[tauri::command]
async fn start_claude(project_path: String, message: String) -> Result<String, String>

#[tauri::command]
async fn stop_claude(session_id: String) -> Result<(), String>

// CX 进程管理（扩展现有）
#[tauri::command]
async fn pause_codex(session_id: String) -> Result<(), String>

#[tauri::command]
async fn resume_codex(session_id: String) -> Result<(), String>

// 项目管理
#[tauri::command]
async fn import_project(path: String) -> Result<Project, String>

#[tauri::command]
async fn list_projects() -> Result<Vec<Project>, String>
```

### 3.5 技术选型

**主要依赖**:
- 前端：React 18 + TypeScript + Vite + Tailwind CSS
- 后端：Rust + Tauri 2
- 数据库：SQLite (rusqlite) 用于项目注册表

**Sidecar**: PyInstaller 打包 cc-spec CLI

**翻译（可选）**: Candle + HuggingFace t5-small (242MB)

---

## 4. 成功标准

### 功能标准

- [ ] Viewer 可启动 CC 进程并显示对话
- [ ] CC 调用 cc-spec 时，CX 任务显示在侧边面板
- [ ] 支持暂停/继续/停止 CX 任务
- [ ] 支持导入和管理项目
- [ ] 设置页面可配置 CC 路径、向量开关、翻译模型

### 质量标准

- [ ] Rust 代码通过 clippy 检查
- [ ] TypeScript 代码通过 ESLint 检查
- [ ] 关键功能有集成测试

### 性能标准

- [ ] Viewer 启动到可用 < 3s
- [ ] 控制命令（暂停/停止）响应 < 1s
- [ ] cc-spec sidecar 大小 < 50MB

### 用户体验标准

- [ ] 用户 80% 操作在 Viewer 内完成
- [ ] cc/cx 输出清晰区分，无混淆
