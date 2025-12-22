# cc-spec v0.2.1 - Viewer 主入口改造

## 版本目标

将 cc-spec-viewer 从"只显示"改造为"主入口"，用户在 Viewer 里直接和 Claude Code 对话，实现完整的规范驱动开发工作流。

## 核心变化

```
v0.1.x 架构：
  终端 -> cc -> cc-spec chat -> cx -> sessions.json -> Viewer(只显示)

v0.2.1 架构：
  Viewer(主入口) -> cc -> cc-spec(sidecar) -> cx -> Viewer(显示+控制)
```

## 文档索引

| 文档 | 内容 | 状态 |
|------|------|------|
| [01-背景与目标](./01-背景与目标.md) | 业务目的、核心原则、成功指标 | 🚧 |
| [02-现状分析](./02-现状分析.md) | opcode/claudia 调研、现有 Viewer 分析 | 🚧 |
| [03-设计方案](./03-设计方案.md) | 架构设计、数据存储、进程管理、UI 设计 | 🚧 |
| [04-实施步骤](./04-实施步骤.md) | Phase 分阶段、每阶段验收标准 | 🚧 |
| [05-任务拆分](./05-任务拆分.md) | Wave/Task 规划、依赖关系 | 🚧 |

## 核心功能

### 必须实现

1. **cc 对话区**：在 Viewer 里和 cc (Claude Code) 对话
2. **cx 任务面板**：显示 cx (Codex) 任务状态，手动控制（暂停/继续/停止）
3. **cc-spec sidecar**：打包 cc-spec CLI 随 Viewer 分发
4. **项目管理**：导入项目即获得 cc-spec 工作流

### 可选功能（设置页面）

1. **向量管理**：RAG 知识库，开启后强制 cx 使用向量查询
2. **翻译管理**：Candle + HuggingFace 本地翻译

## 技术来源

| 来源 | 用途 |
|------|------|
| **claudia** | 调用 cc 的底层实现（Tauri + spawn） |
| **opcode** | UI 交互设计、设置页面布局 |

## 约束条件

1. **cc 不打包**：调用用户已安装的 Claude Code
2. **项目目录不污染**：cc-spec 数据存储在 Viewer 本地
3. **CLI 保留**：原有 `uv run cc-spec` 命令行方式照常可用

## 调研报告

- [本地翻译功能调研](../../viewer-local-translation-research.md)

---

*文档创建时间: 2025-01*
