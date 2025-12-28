# 命令参考

> 说明：cc-spec 的“人类流程”是组合指令；系统会生成/维护**项目索引**与**工作流状态**（如 `status.yaml`），用于保证后续步骤可重复、可追踪。

**人类步骤 vs 系统产物**

| 人类步骤 | 系统动作/关键产物 |
|---|---|
| init | 初始化 `.cc-spec/` 目录结构与默认配置；生成各 AI 工具的命令文件（如 `.claude/commands/cc-spec/*.md`） |
| init-index / update-index | 生成/更新 `PROJECT_INDEX.md`、`FOLDER_INDEX.md`；写入 `.cc-spec/index/manifest.json`、`.cc-spec/index/status.json` |
| specify | 生成 `proposal.md` 并创建变更目录 |
| clarify | 标记返工/补充信息（更新 `status.yaml`） |
| plan | 基于 `proposal.md` 生成 `tasks.yaml` |
| apply | 按 Wave 并发执行 `tasks.yaml`，更新任务状态与执行记录 |
| accept | 生成/维护 `acceptance.md`；运行自动化检查并输出 `acceptance-report.md` |
| archive | 归档变更产物到 `.cc-spec/archive/` |

## 全局选项

```bash
cc-spec --version    # 显示版本号
cc-spec --help       # 显示帮助信息
```

---

## init

初始化 cc-spec 项目结构与默认配置。

```bash
cc-spec init [OPTIONS]
```

常用选项：
- `--force`, `-f`：强制覆盖已存在的 `.cc-spec/` 目录

---

## init-index / update-index / check-index

初始化/更新/检查项目多级索引（用于上下文注入与结构概览）。

```bash
cc-spec init-index [--path <DIR>] [--level l1|l2|l3 ...]
cc-spec update-index [--path <DIR>] [--level l1|l2|l3 ...]
cc-spec check-index [--path <DIR>]
```

说明：
- L1：`PROJECT_INDEX.md`（项目根索引）
- L2：`FOLDER_INDEX.md`（每个文件夹的文件清单）
- L3：预留（默认不修改源码，仅记录到 manifest/status）

---

## specify

创建新的变更规格。

```bash
cc-spec specify <CHANGE_NAME>
```

---

## clarify

查看任务列表或标记任务返工；可选歧义检测。

```bash
cc-spec clarify
cc-spec clarify <TASK_ID>
cc-spec clarify --detect
```

说明：
- 无参数：显示当前变更的任务列表
- 指定任务：标记返工并更新 `status.yaml`
- `--detect`：对 `proposal.md` 做轻量歧义检测并写回提示信息（不做交互式问答回写）

---

## plan

生成执行计划（`tasks.yaml`）。

```bash
cc-spec plan [CHANGE_NAME]
```

说明：
- 读取 `proposal.md`
- 生成 `tasks.yaml`（Wave + deps + checklist）

---

## apply

执行任务（SubAgent 并发）。

```bash
cc-spec apply [CHANGE_NAME] [OPTIONS]
```

常用选项：
- `--max-concurrent`, `-c`
- `--resume`, `-r`
- `--dry-run`

---

## accept

端到端验收：执行自动化检查并生成报告。

```bash
cc-spec accept [CHANGE_NAME|CHANGE_ID] [--skip-checks] [--write-report/--no-write-report]
```

说明：
- 生成/维护 `acceptance.md`
- 运行配置的检查命令（默认 `lint/test/build/type-check`）
- 输出 `acceptance-report.md`（默认开启）

---

## archive

归档已完成变更。

```bash
cc-spec archive <CHANGE_NAME>
```

---

## quick-delta

快速变更通道（用于小改动/热修复）。

```bash
cc-spec quick-delta "<描述>"
```

说明：
- 自动解析 `git diff` 生成最小化的变更描述（仍建议走 `accept` 验证）

---

## list / goto / update / chat / context

```bash
cc-spec list changes|tasks|specs|archives
cc-spec goto <ID>
cc-spec update [config|commands|templates]
cc-spec chat
cc-spec context
```

---

## 环境变量

| 变量 | 说明 |
|------|------|
| `CC_SPEC_CONFIG` | 自定义配置文件路径 |
| `CC_SPEC_TEMPLATES` | 自定义模板目录路径 |
| `CC_SPEC_NO_COLOR` | 禁用颜色输出 |
