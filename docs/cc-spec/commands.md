# 命令参考

> 说明：8 步流程是人类组合指令；系统层会将每步转换为 KB 记录/更新动作。

**人类步骤 vs 系统 KB 动作**

| 人类步骤 | 系统 KB 动作（必须执行） |
|---|---|
| init | 建立项目结构；若 KB 未建，标记待入库 |
| kb init/update | 生成/更新 code chunks 与 workflow records |
| specify | `kb record`：Why/What/Impact/Success Criteria |
| clarify | `kb record`：返工原因/歧义检测结果/需求补充摘要 |
| plan | `kb record`：任务拆解摘要、依赖、验收点 |
| apply | `kb record`：任务执行上下文与变更摘要；`kb update` 入库变更 |
| checklist | `kb record`：评分、未完成项、改进建议 |
| archive | `kb update/compact`：归档前确保 KB 最新 |

## 全局选项

```bash
cc-spec --version    # 显示版本号
cc-spec --help       # 显示帮助信息
```

---

## init

初始化 cc-spec 项目结构。

```bash
cc-spec init [OPTIONS]
```

常用选项：
- `--force`, `-f`：强制覆盖已存在配置

说明：
- 创建 `.cc-spec/` 目录结构
- 生成默认 `config.yaml`

---

## kb

构建/更新知识库（推荐）。

```bash
cc-spec kb init
cc-spec kb update
cc-spec kb status
cc-spec kb query "关键词"
```

说明：
- KB 是评审主线，包含 code chunks 与 workflow records
- 未建 KB 会影响后续评审质量

---

## specify

创建新的变更规格。

```bash
cc-spec specify <CHANGE_NAME>
```

说明：
- 生成 `proposal.md`
- 写入 KB record（Why/What/Impact/Success Criteria）

---

## clarify

查看任务列表或标记任务返工；可选歧义检测。

```bash
cc-spec clarify
cc-spec clarify <TASK_ID>
cc-spec clarify --detect
```

说明：
- 无参数：显示当前变更任务列表
- 指定任务：标记返工并写入 KB
- `--detect`：检测 proposal.md 歧义并写入 KB

---

## plan

生成执行计划（tasks.yaml）。

```bash
cc-spec plan <CHANGE_NAME>
```

说明：
- 读取 `proposal.md`
- 生成 `tasks.yaml`（Gate/Wave + deps + checklist）
- 不再默认生成 `design.md`

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

说明：
- 按 Wave 顺序执行；Wave 内并发
- 每个任务会写入 KB record
- 任务完成后执行 KB update

---

## checklist

验收评分（强 Gate）。

```bash
cc-spec checklist <CHANGE_NAME> [OPTIONS]
```

常用选项：
- `--threshold`：通过阈值（默认 80）
- `--write-report`：生成 `checklist-result.md`

说明：
- 解析 `tasks.yaml` 中 checklist
- 权重以 `config.yaml` 为准（默认 30/25/25/20）
- 未通过：不得归档；写入 KB record 并回到 apply/clarify
- 默认不落盘报告；需 `--write-report`

---

## archive

归档已完成变更。

```bash
cc-spec archive <CHANGE_NAME> [OPTIONS]
```

说明：
- checklist 未通过不可归档
- 归档前确保 KB 已更新/compact

---

## quick-delta

快速变更通道（简化文档，但系统流程完整）。

```bash
cc-spec quick-delta "Fix typo in README"
```

说明：
- 必须写入 KB record（最小需求集）
- 模式由模型基于 KB 评估决定；影响文件数 >5 强制标准流程
- 用户可中文明确表达跳过/强制快速

---

## list

列出变更、任务、规范或归档。

```bash
cc-spec list changes|tasks|specs|archive
```

---

## goto

导航到变更或任务。

```bash
cc-spec goto <ID>
```

---

## update

更新配置、命令或模板。

```bash
cc-spec update [commands|subagent|all] [OPTIONS]
```

---

## 环境变量

| 变量 | 说明 |
|------|------|
| `CC_SPEC_CONFIG` | 自定义配置文件路径 |
| `CC_SPEC_TEMPLATES` | 自定义模板目录路径 |
| `CC_SPEC_NO_COLOR` | 禁用颜色输出 |
