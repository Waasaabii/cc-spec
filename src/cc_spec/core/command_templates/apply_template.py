"""apply 命令的模板实现。

该模板为 apply 命令提供完整的执行指令,包括:
- SubAgent 并行执行机制说明
- Wave 分组和并发执行流程
- 锁机制使用和冲突防止
- 技术检查和任务状态更新
- tasks.md 状态追踪和报告
"""

from .base import CommandTemplate, CommandTemplateContext


class ApplyTemplate(CommandTemplate):
    """apply 命令的模板实现。

    该模板指导 AI 工具使用 SubAgent 并行执行 tasks.md 中的任务。
    任务按 Wave 分组:同一 Wave 内任务并行执行,Wave 之间串行执行。

    核心功能:
    - 读取并解析 tasks.md 中的任务列表
    - 按 Wave 分组并管理任务依赖关系
    - 使用锁机制防止并发冲突
    - 监控 SubAgent 执行并收集结果
    - 执行技术检查(lint/type-check/test)
    - 更新任务状态并生成执行报告
    """

    def get_outline(self, ctx: CommandTemplateContext) -> str:
        """获取 apply 命令的大纲描述。"""
        return """使用 SubAgent 并行执行 tasks.md 中的任务。

**核心目标:**
- 读取 tasks.md 并解析任务列表(Wave/Task-ID 格式)
- 按 Wave 分组任务:同一 Wave 内并行,Wave 间串行
- 为每个任务生成精简的 SubAgent 上下文
- 监控 SubAgent 执行并收集结果
- 执行技术检查(lint/type-check/test)
- 更新任务状态并生成执行报告

**输入:** tasks.md(任务定义,包含 Wave 分组和依赖关系)
**输出:** 更新的 tasks.md(任务状态变更) + 执行报告

**执行流程:**
1. 解析 tasks.md → 识别 Wave 分组和任务依赖
2. 对每个 Wave:
   - 获取锁 → 启动 SubAgent → 监控执行 → 收集结果 → 释放锁
   - 同一 Wave 内任务并发执行(最多 10 个并发)
   - Wave 之间串行执行(Wave-1 完成后才开始 Wave-2)
3. 执行技术检查 → 更新任务状态 → 生成报告

**锁机制说明:**
- 任务执行前获取锁,防止多个 SubAgent 同时修改同一文件
- 锁超时机制:默认 30 分钟,超时后自动释放
- 支持强制解锁(--force-unlock)和跳过被锁任务(--skip-locked)
- 每个 SubAgent 分配唯一 agent_id 用于追踪和冲突检测"""

    def get_execution_steps(self, ctx: CommandTemplateContext) -> list[str]:
        """获取 apply 命令的执行步骤列表。"""
        return [
            (
                "读取 `.cc-spec/changes/<change-name>/tasks.md` 文件,解析任务列表:"
                "识别每个任务的 ID(W<wave>-T<task> 格式)、状态(待执行/进行中/已完成/失败)、"
                "依赖关系(dependencies 字段)、检查清单"
            ),

            (
                "检查任务依赖关系和执行顺序:验证依赖的任务是否存在,是否有循环依赖,"
                "确认 Wave 分组正确(同一 Wave 内任务互不依赖)。"
                "如果依赖关系有问题,报错并提示用户修改 tasks.md"
            ),

            (
                "为每个任务生成精简的 SubAgent 上下文(prompt):"
                "包括变更摘要(proposal.md 的简要说明)、任务描述(name + 详细说明)、"
                "检查清单(具体的验收标准)、必读文档(required_docs)、代码入口(code_entry_points)。"
                "确保上下文清晰、信息充分但不冗余"
            ),

            (
                "按 Wave 分组任务:从 Wave-0(或 Wave-1)开始,逐个 Wave 执行。"
                "对每个 Wave,获取所有状态为'待执行'的任务(跳过已完成/进行中/失败的任务)。"
                "如果某个 Wave 没有待执行任务,跳过该 Wave 并继续下一个"
            ),

            (
                "对每个 Wave 执行以下流程:\n"
                "   a. 为每个任务尝试获取锁(LockManager.acquire),防止并发冲突\n"
                "   b. 启动 SubAgent:使用生成的上下文 prompt 启动 SubAgent 实例"
                "(最多 10 个并发)\n"
                "   c. 监控执行:实时追踪 SubAgent 执行状态,记录开始时间、agent_id\n"
                "   d. 收集结果:等待 SubAgent 完成,收集输出、错误信息、耗时\n"
                "   e. 释放锁:任务完成后释放锁(LockManager.release),允许其他任务访问相同资源"
            ),

            (
                "执行技术检查(仅在所有任务完成后):按顺序运行以下检查:\n"
                "   - Lint 检查:`uv run ruff check src/`(如有警告,记录但继续)\n"
                "   - 类型检查:`uv run mypy src/cc_spec/`(如有警告,记录但继续)\n"
                "   - 单元测试:`uv run pytest`(如有失败,标记为执行失败,阻断流程)\n"
                "   技术检查失败时,在报告中详细说明失败原因,并提示用户修复"
            ),

            (
                "更新任务状态:根据 SubAgent 执行结果和技术检查结果,更新 tasks.md 中的任务状态:\n"
                "   - 成功:更新为'🟩 完成',记录完成时间(completed_at)和 SubAgent ID\n"
                "   - 失败:更新为'🟥 失败',记录错误信息和失败原因\n"
                "   - 超时:更新为'🟧 超时',记录超时时间和部分输出"
            ),

            (
                "生成执行报告:创建结构化的执行摘要,包括:\n"
                "   - 总 Wave 数和总任务数\n"
                "   - 成功/失败/超时任务数量和成功率\n"
                "   - 每个 Wave 的执行耗时和任务列表\n"
                "   - 技术检查结果(lint/type-check/test)\n"
                "   - 失败任务的详细错误信息\n"
                "   - 下一步建议(如:修复失败任务、运行 checklist 验收)"
            ),
        ]

    def get_validation_checklist(self, ctx: CommandTemplateContext) -> list[str]:
        """获取 apply 命令的验证检查清单。"""
        return [
            "tasks.md 已成功读取并解析,所有任务 ID 和依赖关系识别正确",

            "任务依赖关系检查通过:无循环依赖,Wave 分组符合并行执行要求",

            "SubAgent 上下文(prompt)已为每个任务生成,包含变更摘要、任务描述、检查清单",

            "Wave 分组执行正确:同一 Wave 内任务并发执行,Wave 之间串行执行",

            "锁机制正常工作:任务执行前成功获取锁,执行后正确释放锁,无死锁或锁泄漏",

            "技术检查全部通过:lint 和 type-check 无阻断性错误,test 全部通过",

            "任务状态正确更新:tasks.md 中的状态、完成时间、SubAgent ID 已更新",

            "执行报告已生成:包含完整的执行摘要、成功率、失败详情、下一步建议",
        ]

    def get_guidelines(self, ctx: CommandTemplateContext) -> str:
        """获取 apply 命令的指南。"""
        return """## SubAgent 执行流程详解

### 1. 任务解析和验证

**tasks.md 格式说明:**
```markdown
## Wave 1

### Task W1-T1: 任务名称
状态: 🔵 待执行
依赖: 无
描述: 任务的详细说明...

检查清单:
- [ ] 检查项 1
- [ ] 检查项 2

---

### Task W1-T2: 另一个任务
状态: 🔵 待执行
依赖: W1-T1
...
```

**状态图标说明:**
- 🔵 待执行 (IDLE)
- 🟡 进行中 (IN_PROGRESS)
- 🟩 已完成 (COMPLETED)
- 🟥 失败 (FAILED)
- 🟧 超时 (TIMEOUT)

**依赖关系验证:**
- 检查依赖的任务 ID 是否存在
- 检查是否有循环依赖(A 依赖 B,B 依赖 A)
- 检查 Wave 分组是否合理(同一 Wave 内任务不能相互依赖)

### 2. SubAgent 上下文生成

**上下文结构:**
```markdown
# 任务:W1-T3 - 实现功能 X

你正在执行任务 W1-T3,这是变更 'add-feature-x' 的一部分。

## 变更摘要

<proposal.md 的简要说明,约 200-300 字>

## 任务详情

**任务描述:** 实现功能 X 的核心逻辑...

**依赖(已完成):** W1-T1, W1-T2

**必读文档:**
- proposal.md
- CLAUDE.md

**代码入口:**
- src/cc_spec/core/feature_x.py

**检查清单:**
- [ ] 功能实现完整
- [ ] 代码通过 ruff check 和 mypy 检查
- [ ] 测试用例通过

## 执行说明

1. 仔细阅读所有必读文档
2. 在指定的代码入口处实现所需改动
3. 充分测试你的实现
4. 完成检查清单项后,在 tasks.md 中更新进度
```

**上下文优化原则:**
- 信息充分但不冗余(避免复制整个 proposal.md)
- 突出关键信息(任务目标、检查清单、代码入口)
- 提供清晰的执行指引和状态更新说明

### 3. Wave 并行执行机制

**执行顺序:**
```
Wave-0 (Gate):
  Task W0-T1 → 执行 → 完成
  Task W0-T2 → 执行 → 完成
  (串行执行)

Wave-1:
  Task W1-T1 ---|
  Task W1-T2 ---|- 并行执行(最多 10 个并发)
  Task W1-T3 ---|
  等待所有任务完成

Wave-2:
  Task W2-T1 ---|
  Task W2-T2 ---|- 并行执行
  等待所有任务完成
```

**并发限制:**
- 默认最大并发数:10(可通过 --max-concurrent 调整)
- 使用 asyncio.Semaphore 控制并发
- 避免资源耗尽和系统过载

**失败处理:**
- 遇到失败任务时,立即停止当前 Wave 的执行
- 记录失败详情(错误信息、堆栈跟踪)
- 允许用户修复后使用 --resume 继续执行

### 4. 锁机制使用说明

**锁的作用:**
- 防止多个 SubAgent 同时修改同一文件
- 避免并发冲突和数据竞争
- 确保任务执行的原子性

**锁的生命周期:**
```python
# 1. 获取锁
lock_acquired = lock_manager.acquire(task_id, agent_id)

if not lock_acquired:
    # 锁被占用,根据策略处理:
    # - skip_locked=True: 跳过该任务
    # - skip_locked=False: 报错并停止

# 2. 执行任务
try:
    result = await execute_task(task)
finally:
    # 3. 释放锁
    lock_manager.release(task_id, agent_id)
```

**锁超时机制:**
- 默认超时:30 分钟(可在 config.yaml 中配置)
- 超时后锁自动释放,防止死锁
- 启动时自动清理过期锁(cleanup_on_start=true)

**强制解锁:**
```bash
# 解锁指定任务
cc-spec apply --force-unlock W1-T3

# 跳过被锁定的任务
cc-spec apply --skip-locked
```

**锁冲突检测:**
- 每个 SubAgent 分配唯一 agent_id(格式:agent-<8位随机字符>)
- 锁信息包含:task_id、agent_id、started_at、expires_at
- 释放锁时验证 agent_id,防止误释放其他 SubAgent 的锁

### 5. 技术检查步骤

**检查顺序和策略:**

**1. Lint 检查(非阻断):**
```bash
uv run ruff check src/
```
- 如有警告:记录到报告,但继续执行
- 如有错误:记录到报告,标记为检查失败

**2. 类型检查(非阻断):**
```bash
uv run mypy src/cc_spec/
```
- 如有警告:记录到报告,但继续执行
- 如有错误:记录到报告,标记为检查失败

**3. 单元测试(阻断):**
```bash
uv run pytest
```
- 如有失败:记录详细错误,标记为执行失败,阻断流程
- 用户必须修复测试才能继续

**检查结果记录:**
```yaml
technical_checks:
  lint:
    status: warning
    message: "发现 3 个 lint 警告"
    details: "..."
  type_check:
    status: passed
    message: "类型检查通过"
  test:
    status: failed
    message: "2 个测试用例失败"
    details: "test_apply.py::test_wave_execution FAILED"
```

### 6. 任务状态更新

**状态转换流程:**
```
IDLE → IN_PROGRESS → COMPLETED/FAILED/TIMEOUT
```

**更新 tasks.md 格式:**
```markdown
### Task W1-T3: 实现功能 X
状态: 🟩 已完成
依赖: W1-T1, W1-T2
完成时间: 2025-12-14T10:30:00Z
SubAgent ID: agent-a1b2c3d4

执行日志:
- [2025-12-14 10:25:00] 开始执行 (agent-a1b2c3d4)
- [2025-12-14 10:30:00] 执行完成,耗时 5.2 分钟
```

**失败状态记录:**
```markdown
### Task W1-T5: 实现功能 Y
状态: 🟥 失败
依赖: W1-T4
失败时间: 2025-12-14T11:00:00Z
SubAgent ID: agent-e5f6g7h8

执行日志:
- [2025-12-14 10:55:00] 开始执行 (agent-e5f6g7h8)
- [2025-12-14 11:00:00] 执行失败:ImportError: No module named 'feature_y'

错误详情:
执行 'import feature_y' 时出错,请检查模块是否正确安装。
```

### 7. 错误处理和重试策略

**常见错误类型:**

**1. 任务执行失败:**
- 原因:代码错误、依赖缺失、配置问题
- 处理:记录错误详情,停止当前 Wave,提示用户修复
- 恢复:`cc-spec apply --resume`

**2. 任务超时:**
- 原因:任务执行时间超过限制(默认 5 分钟)
- 处理:记录为超时状态,释放锁,停止执行
- 恢复:增加超时时间 `--timeout 600000`(10 分钟)

**3. 锁冲突:**
- 原因:任务已被其他 SubAgent 锁定
- 处理(skip_locked=false):报错并停止
- 处理(skip_locked=true):跳过该任务,继续执行其他任务
- 恢复:等待锁释放,或使用 --force-unlock 强制解锁

**4. 技术检查失败:**
- 原因:测试用例失败、类型错误
- 处理:记录详细错误,标记为执行失败
- 恢复:修复代码,重新运行 `cc-spec apply`

**重试机制:**
- 每个任务维护 retry_count 计数器
- 失败后重试次数 +1
- 可在报告中查看任务的重试历史

### 8. 执行报告生成

**报告结构:**
```
====================================
执行摘要
====================================

[总览]
- 波次数:3
- 任务数:15
- 成功:13
- 失败:2
- 成功率:86.7%
- 总耗时:45.3 分钟

[Wave 执行详情]
Wave-0 (串行):
  ✓ W0-T1: 任务 A (3.2 分钟)
  ✓ W0-T2: 任务 B (2.8 分钟)

Wave-1 (并行):
  ✓ W1-T1: 任务 C (5.1 分钟)
  ✓ W1-T2: 任务 D (4.9 分钟)
  ✗ W1-T3: 任务 E (失败)

[技术检查]
  ✓ Lint: 3 个警告(非阻断)
  ✓ 类型检查:通过
  ✗ 测试:2 个失败

[失败详情]
W1-T3: ImportError: No module named 'feature_e'
W2-T5: 测试用例 test_feature_f 失败

[下一步建议]
1. 修复 W1-T3 的模块导入问题
2. 修复 W2-T5 的测试用例
3. 运行 `cc-spec apply --resume` 继续执行
```

**报告输出位置:**
- 控制台:实时显示执行进度和摘要
- tasks.md:更新任务状态和执行日志
- status.yaml:更新 apply 阶段状态(IN_PROGRESS/COMPLETED/FAILED)

### 9. Wave 并行执行最佳实践

**合理设置并发数:**
- CPU 密集型任务:并发数 = CPU 核心数
- I/O 密集型任务:并发数 = CPU 核心数 × 2
- Claude Code 默认:10(平衡性能和资源占用)

**任务分组原则:**
- 同一 Wave 内任务应该完全独立,无共享资源
- 避免文件级冲突(多个任务修改同一文件)
- 使用锁机制保护共享资源

**依赖管理:**
- 显式声明任务依赖(deps 字段)
- 避免隐式依赖(如任务 B 需要任务 A 的输出,但未声明依赖)
- 使用 Wave 分组管理复杂依赖链

**失败快速处理:**
- 遇到失败立即停止当前 Wave
- 避免浪费资源执行必定失败的后续任务
- 使用 --resume 从失败点继续执行

### 10. 调试和监控

**实时监控:**
```bash
# 查看执行日志
tail -f .cc-spec/changes/<change-name>/tasks.md

# 查看锁状态
ls -la .cc-spec/.locks/
```

**演练模式:**
```bash
# 预览执行计划,不实际运行
cc-spec apply --dry-run
```

**详细日志:**
- SubAgent 输出:保存到 tasks.md 的执行日志部分
- 锁操作:记录 agent_id、获取时间、释放时间
- 技术检查:记录完整的命令输出

**常用调试选项:**
```bash
# 禁用锁机制(仅用于调试)
cc-spec apply --no-lock

# 增加超时时间
cc-spec apply --timeout 1200000  # 20 分钟

# 跳过被锁定的任务
cc-spec apply --skip-locked

# 强制解锁指定任务
cc-spec apply --force-unlock W1-T3
```"""
