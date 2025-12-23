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

### 故事 4 - 多级索引系统 (优先级: P1)

项目导入后引导用户初始化三级分形索引（PROJECT_INDEX.md → FOLDER_INDEX.md → 文件头注释），CX 执行任务时自动读取索引作为上下文。

**为什么是这个优先级**: 核心功能，索引是 CX 理解项目结构的基础，必须在项目导入时完成。

**验收场景**:

1. **给定** 用户导入新项目，**当** 检测到项目无索引，**那么** 提示用户是否初始化索引，并说明会添加 INDEX.md 文件到项目
2. **给定** 用户同意初始化，**当** 运行 `/cc-spec:init-index`，**那么** 扫描项目并生成三级索引，显示将创建的文件列表供用户确认
3. **给定** 索引已初始化，**当** 用户修改代码文件，**那么** 索引自动增量更新（通过 Hook）
4. **给定** CX 执行任务，**当** 需要项目上下文，**那么** 自动读取 PROJECT_INDEX.md 和相关 FOLDER_INDEX.md

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
- 当索引初始化失败时？→ 显示错误信息，允许跳过继续工作
- 当翻译模型未下载时？→ CX 输出显示英文原文，提供翻译按钮提示下载

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

- **Project**: 导入的项目，包含路径、名称、索引开关、翻译配置
- **Session**: CC 对话会话，关联项目
- **Run**: CC/CX 执行实例，包含状态、PID 和输出
- **Event**: Run 的流式输出和状态变化

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
- 数据库：PostgreSQL（Docker 本地 / 远程连接）

**Sidecar**: PyInstaller 打包 cc-spec CLI

**翻译（可选）**: Candle + HuggingFace t5-small (242MB)

---

## 4. 成功标准

### 功能标准

- [ ] Viewer 可启动 CC 进程并显示对话
- [ ] CC 调用 cc-spec 时，CX 任务显示在侧边面板
- [ ] 支持暂停/继续/停止 CX 任务
- [ ] 支持导入和管理项目
- [ ] 设置页面可配置 CC 路径、索引开关、翻译模型

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

---

## 5. 详细设计（CC/CX 讨论成果）

> 以下内容来自 CC（编排者）与 CX（执行者）的架构讨论，日期：2025-01-22

### 5.1 统一数据模型

**概念映射**：
- **Project** = 全局注册表实体
- **Session** = CC 对话会话 / 工作上下文
- **Run** = 一次具体的 Agent 执行（CC/CX 统一）
- **Event** = Run 的流式输出和状态变化

**对象模型**：

```
Project
├── id, root_path, name, created_at, updated_at
└── settings (default_agent, index_enabled, translation_enabled)

Session
├── id, project_id, title, status
├── active_run_id, runs[], cc_thread_id
└── created_at, updated_at

Run (统一执行实例)
├── id, session_id, agent(CC|CX), purpose(conversation|task)
├── task_spec_id (仅 CX 任务)
├── status (idle|starting|running|paused|stopping|exited|failed)
├── pid, started_at, ended_at
├── capabilities (pause, resume, stdin, structured_output)
├── command (bin, args, cwd, env)
├── io (stdout_offset, stderr_offset, last_event_id, last_seq)
└── pause_state (requested, at, reason)

Event (append-only 流式日志)
├── id, run_id, session_id, seq, ts
├── kind (output|state|tool|error|system|checkpoint)
├── channel (stdout|stderr)
└── payload (结构化内容)
```

### 5.2 数据存储位置

**项目内（轻量，必须存在）**：
```
.cc-spec/
├── specs/                # 提案/任务规格
│   ├── proposal.md
│   ├── tasks.yaml
│   └── base-template.yaml
├── config.yaml           # 最小必要配置
├── project.json          # 项目标识，指向全局 ID
├── changes/              # workflow 变更
└── CLAUDE.md             # 项目上下文
```

**PostgreSQL 数据库**（仅存对话内容）：
```
PostgreSQL（Docker 本地 / 远程连接）
│
├── proj_<ulid_1> schema      # 项目 1 对话历史
│   ├── sessions              # 会话
│   ├── runs                  # 执行实例
│   ├── events                # 事件流（append-only）
│   └── messages              # 消息（面向导出）
│
└── proj_<ulid_2> schema      # 项目 2 对话历史
    └── ...
```

> **注意**：PG 的定位是「对话历史存储」，用于保留和导出历史对话。
> 没有 PG 时，CC/CX 仍可正常工作，只是对话历史不保存。

**本地文件（Viewer 目录）**：
```
%LOCALAPPDATA%/cc-spec-viewer/
├── config.json           # 数据库连接配置
├── models/               # 翻译模型
├── exports/              # 导出文件临时存放
└── logs/                 # 运行日志
```

### 5.2.1 数据库部署方案

**默认（Docker 本地）**：
```bash
docker run -d --name cc-spec-pg \
  -e POSTGRES_PASSWORD=ccspec \
  -p 5432:5432 \
  -v cc-spec-pgdata:/var/lib/postgresql/data \
  postgres:16-alpine
```

**远程连接**：Viewer 设置页配置连接字符串

### 5.2.2 导出/导入功能

**导出格式**（ZIP 包）：
```
export_<timestamp>.zip
├── metadata.json         # 版本、时间、表清单、字段类型
├── sessions.ndjson       # 会话数据
├── runs.ndjson           # 执行实例数据
├── events.ndjson         # 事件流数据
└── messages.ndjson       # 消息数据
```

**导入流程**：
1. 上传导出包 → 预检结构差异
2. 选择模式：全量覆盖 / 增量合并（UPSERT）
3. 选择冲突策略：跳过 / 更新 / 报错
4. 执行导入 → 进度条 → 结果报告

### 5.3 暂停/继续实现方案

**决策**：使用 **OS 级挂起**（SIGSTOP/SuspendThread）

**实现方式**：
- **Windows**: `NtSuspendProcess` / `SuspendThread`（遍历线程）
- **macOS/Linux**: `SIGSTOP` / `SIGCONT`

**需要修改 cc-spec**：
1. `codex.started` 事件增加 `pid` 字段
2. `SessionStateManager` 新增 `run_id → pid` 记录
3. 确保 Viewer 可稳定获取 pid

**错误处理**：
| 场景 | 处理方式 |
|------|----------|
| 进程已退出时暂停 | 返回 `ProcessExited` 错误，UI 提示"任务已结束" |
| 权限不足 | 返回 `PauseDenied`，提示需要管理员权限 |
| 缓冲区溢出 | 输出持久化到 ndjson，内存只保留滚动窗口 |

### 5.4 CC 集成方案

**路径检测优先级**：
1. Viewer 全局设置 `cc_path`
2. 环境变量 `CLAUDE_PATH`
3. PATH 查找（`where claude` / `which claude`）
4. npm 全局目录
5. 常见安装位置：
   - Windows: `%APPDATA%\npm\claude.cmd`
   - macOS: `/usr/local/bin/claude`, `/opt/homebrew/bin/claude`
   - Linux: `/usr/local/bin/claude`, `~/.local/bin/claude`

**启动命令**：
```bash
claude --print --output-format stream-json
```

**输出解析**：
- 行分隔 JSON（ndjson）
- 每行尝试 JSON 解析，失败则作为原始文本
- Event 映射：`type` 字段存在 → Tool/State，其他 → Output

### 5.5 事件分发协议

**Tauri invoke（请求/响应）**：
- `create_session`, `list_sessions`, `get_session`
- `start_run`, `pause_run`, `resume_run`, `stop_run`
- `get_events({runId, cursor, limit, types, channels})`
- `subscribe`, `unsubscribe`

**Tauri event（流式推送）**：
```json
{
  "subId": "sub_0009",
  "event": {
    "id": "evt_000000000245",
    "runId": "run_...",
    "sessionId": "sess_...",
    "seq": 245,
    "ts": "2025-12-22T09:37:44.101Z",
    "type": "output",
    "channel": "stdout",
    "payload": {"text": "...", "partial": true}
  }
}
```

**订阅流程**：
1. `get_events` 拉历史（分页）
2. `subscribe` 获取 `subId` 和 `lastSeq`
3. 实时流，丢弃 `seq <= lastSeq` 的重复事件

### 5.6 Sidecar 打包策略

**目标**：核心版 < 50MB

**裁剪方案**：
- 移除重量级依赖：不再需要 `chromadb`, `fastembed`（已移除向量功能）
- 排除开发依赖：`tree_sitter_language_pack`, `pytest`
- PyInstaller 配置：`--onefile --strip --upx`

**入口脚本**：`src/cc_spec/sidecar.py`（只 import 核心模块）

### 5.7 迁移策略

**Phase 1（MVP）**：
- 新增 `runs/`, `sessions/`, `state/`
- 兼容写入：继续更新 `.cc-spec/runtime/codex/sessions.json`
- CLI 继续使用旧机制

**Phase 2（完整版）**：
- cc-spec CLI 改为"薄壳"：优先调用 Viewer 后端
- 迁移器：旧 sessions.json → 新 sessions/runs
- `meta/schema-version.json` 记录版本

**兼容期策略**：
- 双写机制（新 Run 同时写新/旧结构）
- CLI 命令表面不变
- 旧结构只读，提示可清理

### 5.8 多级索引集成方案

> 基于 `reference/project-multilevel-index` 项目设计

**核心概念**（受《哥德尔、埃舍尔、巴赫》启发）：

| 原则 | 说明 |
|------|------|
| 自相似性 | 每个层级都有相同的索引结构 |
| 自指性 | 每个文档都声明"当我变化时，更新我" |
| 复调性 | 代码与文档相互呼应，局部影响整体 |

**三级索引结构**：

```
PROJECT_INDEX.md (根索引)
  ├─ 项目概览
  ├─ 架构说明
  ├─ 目录结构
  └─ 依赖关系图 (Mermaid)

FOLDER_INDEX.md (文件夹索引)
  ├─ 3行架构说明
  ├─ 文件清单（地位/功能/依赖/被依赖）
  └─ 自指声明

文件头注释 (File Header Comment)
  ├─ Input: 依赖的外部内容
  ├─ Output: 对外提供的内容
  ├─ Pos: 在系统中的定位
  └─ 自指声明
```

**命令映射**：

| Claude 调用 | cc-spec 命令 | 功能 |
|-------------|--------------|------|
| `/cc-spec:init-index` | `cc-spec init-index` | 初始化三级索引 |
| `/cc-spec:update-index` | `cc-spec update-index` | 增量更新索引 |
| `/cc-spec:check-index` | `cc-spec check-index` | 一致性检查 |

**Hook 自动更新**（`.claude/hooks.json`）：

```json
{
  "hooks": {
    "PostToolUse": {
      "tools": ["Write", "Edit"],
      "command": "cc-spec update-index --file \"$FILE\" --silent"
    }
  }
}
```

**用户确认流程**：

1. 项目导入时检测是否存在 `PROJECT_INDEX.md`
2. 不存在时弹窗提示：
   - "检测到项目未初始化索引，索引可帮助 AI 理解项目结构"
   - "将在项目中创建以下文件："
   - 显示文件列表预览
   - [初始化索引] [跳过]
3. 用户点击[初始化索引]后执行 `init-index`
4. 用户可随时通过命令手动初始化

**i18n 支持**：

- Skills 模板支持多语言（locales/zh-CN, locales/en-US）
- CLI 输入：用户输入中文，大模型自动理解
- CX 输出：英文输出通过本地翻译（P3）转为中文

---

## 6. 实现阶段

### Phase 1：基础架构（P1 核心）
- [ ] 项目注册表（SQLite）
- [ ] Session/Run/Event 数据模型
- [ ] CC 路径检测和进程启动
- [ ] CX 暂停/继续（OS 级）
- [ ] 基础 UI（对话区 + 任务面板）

### Phase 2：完整功能（P1/P2）
- [ ] 项目导入和管理 UI
- [ ] 多级索引系统（init-index / update-index / check-index）
- [ ] 索引文件确认机制（用户同意后才创建 INDEX.md 文件）
- [ ] 事件分发和订阅
- [ ] 历史回放和分页
- [ ] Sidecar 打包

### Phase 3：增强功能（P3）
- [ ] 本地翻译功能（Candle + t5-small）
- [ ] 迁移工具

---

## 7. 技术决策汇总（按业界标准确定）

> 以下技术选型由 CC/CX 讨论确定，遵循业界最佳实践

| 决策项 | 选型 | 理由 |
|--------|------|------|
| 数据库 | PostgreSQL | 支持导出历史对话、跨数据库迁移 |
| DB 部署 | Docker 本地（默认）+ 远程连接 | 开箱即用 + 团队协作 |
| 项目隔离 | 单实例多 Schema（`proj_<ulid>`） | 隔离清晰、管理成本低 |
| 主键格式 | ULID | 有序 + 全局唯一，便于分页和排序 |
| Event 格式 | ndjson + `v:1` 版本字段 | 便于流式解析和未来升级 |
| 导出格式 | ZIP（metadata.json + *.ndjson） | 跨数据库迁移友好 |
| 依赖解析 | 正则优先 | 体积约束 < 50MB，多语言覆盖 |
| 缓存策略 | LRU + 磁盘持久化，200MB | 平衡性能和存储 |
| 翻译镜像源 | hf-mirror 优先，自动回退官方 | 国内网络友好 |
| Hook 位置 | `.claude/hooks.json` | Claude 官方约定 |
| 索引存放 | PROJECT_INDEX.md 在根目录（极简入口），详细索引在 `.claude/index/` | 最小污染 + 可见性 |
| 文件头注释 | 不自动写入代码，仅 JSON/MD 索引 | 避免代码污染 |

---

## 8. clarify 命令规范（需求澄清 - 强制步骤）

> `clarify` 是 `plan` 前的强制步骤，用于形成可执行、可验证的需求澄清记录

### 8.1 运行时机

- **必须**在 `plan` 之前执行
- 若存在阻塞问题，将阻断后续 `plan/apply`

### 8.2 输入

- 变更提案（proposal.md）
- KB 上下文（可选）
- 现有任务清单（如已存在）

### 8.3 输出

生成 `.cc-spec/changes/<change>/clarify.md`，内容结构：

```markdown
# 需求澄清：<change-name>

## 背景与目标
（1-3 句话）

## 范围
- **In Scope**: ...
- **Out of Scope**: ...

## 关键决策
| 决策点 | 选择 | 理由 |
|--------|------|------|
| ... | ... | ... |

## 依赖与约束
- ...

## 风险与回滚
- ...

## 验收标准
- [ ] ...

## 未决问题
### 阻塞问题（必须解决）
- [ ] ...

### 非阻塞问题（可记录假设）
- [ ] ...
```

### 8.4 判定规则

- **存在阻塞问题** → `clarify` 失败（退出码非 0）
- **无阻塞问题** → `clarify` 通过（退出码 0）

### 8.5 默认检查项

- 功能边界是否清晰
- 是否有验收标准
- 数据结构/格式是否明确
- 外部依赖是否可用
- 是否存在兼容/迁移风险
- 是否需要测试/回滚方案

### 8.6 细化需求（detail - 强制步骤）

> `detail` 是 `clarify` 后、`plan` 前的强制步骤，CC 与 CX 深入讨论技术细节

**目的**：充分发挥 CC（编排者）和 CX（执行者）两个大模型的能力，通过多轮对话深入挖掘需求细节、发现潜在问题。

**执行方式**：
1. CC 基于 proposal 向 CX 提出问题
2. CX 以执行者视角挑战 CC 的方案，指出漏洞、风险、边界情况
3. CC 回应挑战，完善方案或提出新问题
4. 持续对话直到双方认为方案足够完善

**核心原则**：
- 不预设讨论范围，由模型根据具体需求自由探索
- CX 应主动挑战，而非被动回答
- CC 应深入追问，而非浅尝辄止
- 技术细节按业界标准决定，只有核心体验问题才需用户定夺

**输出**：
- 更新 `clarify.md`，记录讨论成果
- 生成「MVP 决策表」，区分「必须做」和「可延后」

**判定规则**：
- CC/CX 完成充分的深入对话（无固定轮数限制）
- 方案无明显漏洞或遗留的阻塞性问题

---

## 9. 核心决策（已确认）

> 2025-01-22 产品负责人确认

| # | 决策点 | 最终决策 |
|---|--------|----------|
| 1 | 索引初始化时机 | 导入项目后，首次在 Viewer 执行 CC 时提醒初始化索引 |
| 2 | 翻译触发方式 | 点击翻译（手动触发，省资源） |
| 3 | 翻译结果呈现 | 点击切换元素内容（原文/译文切换） |
| 4 | 翻译模型下载 | 用户手动在 Viewer 设置页下载（不自动下载） |
| 5 | 翻译失败提示 | 明确提示错误原因 + 提供重试/查看原文选项 |

### 决策详解

**决策 1 - 索引初始化时机**
- 用户导入项目时不弹窗
- 首次在 Viewer 中对该项目执行 CC 对话时，检测是否有索引
- 无索引则弹窗提醒："检测到项目未初始化索引，是否现在初始化？"
- 提供 [初始化] [跳过] [不再提醒] 选项

**决策 3 - 翻译结果呈现**
- 默认显示原文
- 每个翻译单元（段落/消息）旁有翻译按钮
- 点击后在原位切换显示译文
- 再次点击切换回原文
- 不使用侧边栏或双栏对照

**决策 4 - 翻译模型下载**
- 设置页面提供"翻译模型"选项
- 显示模型信息：名称、大小（242MB）、状态（未下载/已下载/下载中）
- 用户点击"下载"按钮后开始下载
- 显示下载进度，支持暂停/继续/取消

---

## 10. CC/CX 深度讨论成果（2025-12-23）

> 以下内容来自 CC 与 CX 的多轮技术讨论

### 10.1 统一事件协议

**设计原则**：
- 统一 `agent.*` 前缀，通过 `source` 字段区分 CC/CX
- 保留原始事件细节（`raw` 字段，debug 模式）
- 支持前端组件复用和未来扩展（如接入 Aider）

**事件信封（通用字段）**：

```json
{
  "id": "evt_xxx",
  "ts": "2025-12-23T...",
  "type": "agent.stream",
  "source": "claude | codex | system | viewer",
  "session_id": "sess_xxx",
  "run_id": "run_xxx",
  "seq": 245,
  "payload": {},
  "raw": {}
}
```

**事件类型枚举**：

| 类型 | 说明 |
|------|------|
| `agent.started` | Agent 启动 |
| `agent.stream` | 流式输出 |
| `agent.completed` | 执行完成 |
| `agent.error` | 执行错误 |
| `agent.heartbeat` | 保活心跳（可选） |
| `agent.tool.request` | 工具调用请求 |
| `agent.tool.approval` | 用户确认（危险操作） |
| `agent.tool.result` | 工具执行结果 |
| `agent.tool.error` | 工具执行错误 |

**CC stream-json 映射规则**：

| CC 原始类型 | 映射事件 |
|-------------|----------|
| `type: system` | `agent.started` + `agent.stream (channel=system)` |
| `type: assistant` | `agent.stream (channel=assistant)` |
| `type: assistant` 含 tool_use | `agent.tool.request` |
| `type: result (success)` | `agent.completed` |
| `type: result (error)` | `agent.error` |

**工具命名空间**：

- CC 内置工具：`claude.read`, `claude.write`, `claude.bash`
- CX 内置工具：`codex.shell_command`, `codex.apply_patch`
- cc-spec 工具：`cc-spec.init-index`, `cc-spec.apply`

### 10.2 多级索引集成最终方案

**决策：Skill 为主 + CLI 薄封装**

1. **Skill 安装**
   - cc-spec 把 fork 项目的 Skill 文件打包到 Viewer 资源目录
   - 首次运行时复制到 `.claude/skills/cc-spec-index/`
   - 支持版本校验和更新

2. **CLI 职责（薄封装）**
   - `cc-spec init-index`：安装 Skill + 提示使用方式 + 守卫逻辑
   - `cc-spec index-status`：查询索引状态 + 向 Viewer 发送通知
   - **不执行 LLM 逻辑**，Skill 由 CC 自己解读并执行

3. **索引状态双轨通知**
   - **主路径（文件哨兵）**：Skill 执行完成后写入 `.cc-spec/index/status.json`
   - **加速路径（CLI 通知）**：`cc-spec index-status --notify` 向 Viewer 发送 SSE 事件
   - Viewer 通过文件监视 + SSE 双轨感知索引状态

4. **幂等性机制**
   - 检测 `PROJECT_INDEX.md` + `status.json` 中的版本/时间戳
   - 默认跳过，`--force` 强制，`--verify` 触发 `check-index`
   - 加锁避免并发覆盖

**状态文件格式**：

```json
{
  "status": "ok | partial | failed",
  "generated_at": "2025-12-23T...",
  "skill_version": "2.0.0",
  "project_hash": "sha256:...",
  "project_root": "/path/to/project",
  "files_indexed": 57,
  "folders_indexed": 8
}
```

### 10.3 嵌套调用解决方案

**问题**：CC 通过 Bash 调用 cc-spec，如果 cc-spec 再启动 CC 会导致递归

**解决方案**：

1. **环境变量标记**：Viewer 启动 CC 时注入 `CC_SPEC_IN_AGENT=1`
2. **内部模式检测**：cc-spec 检测到该变量后进入内部模式
3. **内部模式行为**：
   - 只执行守卫逻辑（检查、校验）
   - 不启动 CC/CX
   - 返回结构化指令，由 CC 自己执行

### 10.4 前端展示布局

**决策：统一时间线（方案 C）**

- 所有 CC/CX 事件按时间顺序显示在同一列表
- 通过 `source` 徽标 + 颜色区分
- 支持筛选（只看 CC / 只看 CX / 全部）
- 按 `run_id` 折叠或加分隔线
- 工具事件默认折叠，展开看细节

**理由**：
- 开发成本最低
- 天然有时间顺序
- 避免双列同步的复杂性

### 10.5 翻译功能细节

**翻译粒度**：
- 先做"整段消息翻译"（按消息块）
- 句级对齐成本高且易破坏上下文
- 代码块保持原样，只翻译纯文本段

**选择翻译**：
- 用户选中文字时，翻译选中内容
- 未选中时，翻译整段消息

**模型加载策略**：
- 按需加载 + 保活 5-15 分钟
- 空闲后卸载释放内存
- 加简单缓存（hash → 译文）避免重复翻译

### 10.6 Sidecar 打包策略（补充）

**Skill 文件打包**：
- 随 Viewer 资源打包（体积极小、离线可用）
- 首次运行从资源目录复制到项目 `.claude/skills/`
- 版本不一致时提示覆盖
- 支持从网络拉取新版本（可选，hash 校验）

### 10.7 会话关联设计

**多层 ID 设计**：

| ID | 说明 |
|----|------|
| `conversation_id` | 全局对话 ID，跨 CC/CX 统一 |
| `session_id` | 各引擎的会话 ID（CC 有自己的 thread_id） |
| `parent_session_id` | 父会话 ID（CC 触发 CX 时关联） |
| `run_id` | 单次执行 ID（用户一次请求对应一个 run） |
| `initiator_tool_id` | 触发该会话的工具调用 ID |

---

## 11. 讨论步骤规范（已纳入工作流要求）

> 以下步骤是 cc-spec 工作流的强制要求

### 11.1 需求澄清（clarify）

**触发时机**：`specify` 完成后

**执行要求**：
1. CC 阅读 proposal.md
2. 识别不明确的需求点
3. 向用户或 CX 提出澄清问题
4. 记录决策到 clarify.md

### 11.2 深度讨论（detail）

**触发时机**：`clarify` 完成后、`plan` 之前

**执行要求**：
1. CC 基于 proposal + clarify 向 CX 发起讨论
2. 讨论必须基于实际代码上下文（先调研再讨论）
3. CX 主动挑战方案，指出漏洞和边界情况
4. 持续对话直到方案足够完善
5. 讨论成果更新到 proposal.md

**核心原则**：
- **先调研后讨论**：CC 必须先读取相关代码再发起讨论
- **有上下文联系**：每轮讨论要引用之前的讨论成果
- **复用不自研**：优先使用 fork 项目已有实现
- **技术问题自决**：技术细节按业界标准决定，不需用户定夺
- **体验问题上报**：只有核心用户体验问题才需用户确认

### 11.3 判定标准

**clarify 通过条件**：
- 无阻塞性问题
- 关键决策已记录

**detail 通过条件**：
- CC/CX 完成充分讨论
- 方案无明显漏洞
- 技术决策已确定
- 讨论成果已写入 proposal.md

### 11.4 CC/CX 能力分工

**CX（Codex）擅长**：
- 代码调研（Glob/Grep/Read）
- 具体实现（Write/Edit）
- 测试执行
- 批量文件操作

**CC（Claude Code）擅长**：
- 复杂推理和设计
- 文档编写
- 需求分析
- CX 调研不了的内容（如 CC 自身的能力、API 调用）

**任务分配原则**：
- 调研任务优先交给 CX
- CX 调研不了的（如 CC 原生能力）由 CC 补充
- 文档编写由 CC 完成
- 每个 task 都要明确写清楚 CC 或 CX 执行

---

## 12. 补充需求（2025-12-23）

### 12.1 并发限制

**需求**：设置页面增加并发任务数限制

- 总并发限制：默认 6（CC + CX 共享）
- CC 默认并发：1（通常只需要一个编排者）
- CX 默认并发：5（执行者可并行）
- 超过限制时，新任务进入队列等待
- 显示当前运行数 / 队列数

### 12.2 clarify 命令合并 checklist 功能

**需求**：将 `checklist` 命令废弃，功能合并到 `clarify`

**背景**：
- 当前流程：`apply` → `checklist`（评分）→ 不通过 → `clarify`（返工）→ 重复
- 问题：checklist 和 clarify 功能重叠，增加用户认知负担

**合并后流程**：
```
apply → clarify（评分 + 审查）→ 通过 → archive
                              → 不通过 → 更新验收标准 + 返工
```

**clarify 新增功能**：
1. **验收评分**：读取 tasks.yaml 中的 checklist，计算四维度得分
2. **验收标准更新**：返工时可更新任务的验收标准（checklist 项）
3. **通过判定**：得分 ≥ 阈值时标记通过，可直接进入 archive

**命令变更**：
```bash
# 新用法
cc-spec clarify                    # 显示任务列表 + 验收评分
cc-spec clarify <task-id>          # 标记返工 + 可更新验收标准
cc-spec clarify --detect           # 检测歧义（保留）
cc-spec clarify --threshold 90     # 自定义通过阈值（从 checklist 继承）

# 废弃
cc-spec checklist                  # 废弃，功能已合并到 clarify
```

**验收标准更新流程**：
1. 运行 `cc-spec clarify <task-id>` 标记任务返工
2. 提示"是否更新该任务的验收标准？"
3. 用户选择 [是] → 进入交互式编辑模式
4. 可添加/修改/删除 checklist 项
5. 保存到 tasks.yaml

**兼容性**：
- `cc-spec checklist` 命令保留但标记为废弃（deprecated）
- 执行时提示"请使用 cc-spec clarify 代替"
- 内部调用 clarify 的评分逻辑

---

### 12.3 设置持久化

**需求**：设置页面所有配置项必须持久化

**持久化项**：
- CC 路径配置
- 并发限制
- 索引开关
- 翻译模型状态
- 数据库连接配置
- 主题/外观偏好

**存储位置**：`%LOCALAPPDATA%/cc-spec-viewer/config.json`

**格式示例**：
```json
{
  "version": 1,
  "claude": {
    "path": "auto",
    "custom_path": null
  },
  "codex": {
    "max_concurrent": 3
  },
  "index": {
    "enabled": true,
    "auto_update": true
  },
  "translation": {
    "model_downloaded": false,
    "model_path": null,
    "cache_enabled": true
  },
  "database": {
    "type": "docker",
    "connection_string": null
  },
  "ui": {
    "theme": "system",
    "language": "zh-CN"
  }
}
