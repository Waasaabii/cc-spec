"""SubAgent 执行器模块。

提供 SubAgentExecutor 类用于管理任务的并发执行。
任务按 Wave 分组，同一 Wave 内的任务并行执行，Wave 之间顺序执行。

v1.2: 添加 Profile 支持，实现任务特定的配置。
v1.3: 添加锁集成、agent_id、wave 字段和重试计数。
"""

import asyncio
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from cc_spec.core.config import Config, SubAgentProfile
from cc_spec.core.lock import LockManager
from cc_spec.subagent.task_parser import (
    Task,
    TasksDocument,
    TaskStatus,
    get_tasks_by_wave,
    parse_tasks_yaml,
    update_task_status_yaml,
)


def _generate_agent_id() -> str:
    """生成唯一的 agent ID。

    返回：
        格式为 'agent-<8位随机字符>' 的字符串
    """
    return f"agent-{uuid.uuid4().hex[:8]}"


@dataclass
class ExecutionResult:
    """任务执行结果数据类。

    v1.3 新增字段: agent_id, wave, retry_count

    属性：
        task_id: 执行的任务 ID
        success: 任务是否成功完成
        output: 任务执行的标准输出
        error: 错误信息 (成功时为 None)
        duration_seconds: 任务执行耗时 (秒)
        started_at: 任务开始执行的时间戳
        completed_at: 任务完成执行的时间戳
        agent_id: v1.3 - 执行该任务的 SubAgent ID
        wave: v1.3 - 任务所属的 Wave 编号
        retry_count: v1.3 - 重试次数
    """

    task_id: str
    success: bool
    output: str
    error: str | None = None
    duration_seconds: float = 0.0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    # v1.3 新增字段
    agent_id: str | None = None
    wave: int = 0
    retry_count: int = 0


class SubAgentExecutor:
    """SubAgent 并行任务执行器。

    处理 tasks.md 文件中的任务，按 Wave 组织并在 Wave 内并发执行任务，
    同时保持 Wave 之间的顺序执行。

    v1.2: 添加 Profile 支持，实现任务特定的配置。
    v1.3: 添加 LockManager 集成，防止并发冲突；添加 agent_id 追踪。

    属性：
        tasks_md_path: tasks.md 文件路径
        max_concurrent: 最大并发任务数
        timeout_ms: 默认任务超时时间 (毫秒)
        config: 可选的 Config 配置对象 (v1.2)
        lock_manager: v1.3 - 锁管理器
        doc: 解析后的 TasksDocument
        tasks_md_content: tasks.md 的原始内容
    """

    def __init__(
        self,
        tasks_md_path: Path,
        max_concurrent: int = 10,
        timeout_ms: int = 300000,  # 5 分钟
        config: Config | None = None,
        lock_manager: LockManager | None = None,  # v1.3 新增
        cc_spec_root: Path | None = None,  # v1.3 新增
    ):
        """初始化执行器。

        参数：
            tasks_md_path: tasks.md 文件路径
            max_concurrent: 最大并发任务数
            timeout_ms: 默认任务超时时间 (毫秒)
            config: 可选的 Config 配置对象 (v1.2)
            lock_manager: v1.3 - 可选的锁管理器
            cc_spec_root: v1.3 - .cc-spec 目录路径 (用于创建锁管理器)

        异常：
            FileNotFoundError: 如果 tasks_md_path 不存在
            ValueError: 如果 tasks.md 格式无效
        """
        if not tasks_md_path.exists():
            raise FileNotFoundError(f"tasks.md 文件不存在: {tasks_md_path}")

        self.tasks_md_path = tasks_md_path
        self.max_concurrent = max_concurrent
        self.timeout_ms = timeout_ms
        self.config = config

        # v1.3: 初始化锁管理器
        if lock_manager is not None:
            self.lock_manager = lock_manager
        elif cc_spec_root is not None:
            lock_timeout = 30  # 默认 30 分钟
            if config and config.lock:
                lock_timeout = config.lock.timeout_minutes
            self.lock_manager = LockManager(cc_spec_root, lock_timeout)
            # 启动时清理过期锁
            if config and config.lock and config.lock.cleanup_on_start:
                self.lock_manager.cleanup_expired()
        else:
            self.lock_manager = None

        # 加载并解析 tasks.yaml
        self.tasks_md_content = tasks_md_path.read_text(encoding="utf-8")
        self.doc = parse_tasks_yaml(self.tasks_md_content)

        # 控制并发的信号量
        self._semaphore = asyncio.Semaphore(max_concurrent)

        # 自定义任务执行器 (用于测试或自定义实现)
        self._task_executor: Callable[[Task], ExecutionResult] | None = None

        # v1.3: 任务重试计数器
        self._retry_counts: dict[str, int] = {}

    def get_task_profile(self, task: Task) -> SubAgentProfile:
        """获取任务的 Profile 配置。

        v1.2: 使用 task.profile 指定的配置，回退到 "common"。

        参数：
            task: 要获取配置的任务

        返回：
            合并后的 SubAgentProfile 配置
        """
        if self.config is None:
            # 未配置时返回默认 Profile
            return SubAgentProfile()

        # 使用任务的 Profile，否则回退到 common
        profile_name = task.profile if task.profile else None
        return self.config.subagent.get_profile(profile_name)

    def load_document(self) -> TasksDocument:
        """加载并解析 tasks.yaml。

        返回：
            解析后的 TasksDocument
        """
        self.tasks_md_content = self.tasks_md_path.read_text(encoding="utf-8")
        self.doc = parse_tasks_yaml(self.tasks_md_content)
        return self.doc

    def set_task_executor(self, executor: Callable[[Task], ExecutionResult]) -> None:
        """设置自定义任务执行器（用于测试或真实实现）。

        参数：
            executor: 接收 Task 并返回 ExecutionResult 的函数
        """
        self._task_executor = executor

    def build_task_prompt(self, task: Task, change_dir: Path) -> str:
        """构建供 SubAgent 执行任务的提示词（prompt）。

        提示词包含：
        - 任务描述与检查清单
        - 需要阅读的必读文档
        - 需要修改的代码入口
        - 在 tasks.md 中更新任务状态与检查清单的说明

        参数：
            task: 需要构建提示词的任务
            change_dir: 变更目录路径

        返回：
            面向 SubAgent 的格式化提示词字符串
        """
        prompt_lines = [
            f"# 任务：{task.task_id} - {task.name}",
            "",
            f"你正在执行任务 {task.task_id}，这是变更 '{self.doc.change_name}' 的一部分。",
            "",
            "## 任务详情",
            "",
        ]

        # 添加依赖信息
        if task.dependencies:
            prompt_lines.extend([
                "**依赖（已完成）：**",
                *[f"- {dep_id}" for dep_id in task.dependencies],
                "",
            ])

        # 添加必读文档
        if task.required_docs:
            prompt_lines.extend([
                "**必读文档：**",
                "",
                "请阅读这些文档以理解上下文与要求：",
                *[f"- {doc}" for doc in task.required_docs],
                "",
            ])

        # 添加代码入口
        if task.code_entry_points:
            prompt_lines.extend([
                "**代码入口：**",
                "",
                "请把实现重点放在这些代码位置：",
                *[f"- {entry}" for entry in task.code_entry_points],
                "",
            ])

        # 添加检查清单
        if task.checklist_items:
            prompt_lines.extend([
                "**检查清单：**",
                "",
                "请完成以下检查清单中的所有条目：",
                *[
                    f"- [{'x' if item.status.value == 'passed' else ' '}] {item.description}"
                    for item in task.checklist_items
                ],
                "",
            ])

        # 添加执行说明
        prompt_lines.extend([
            "## 执行说明",
            "",
            "1. 仔细阅读所有必读文档",
            "2. 在指定的代码入口处实现所需改动",
            "3. 充分测试你的实现",
            "4. 完成检查清单项后，在 tasks.md 中更新进度",
            "",
            "## 状态回报",
            "",
            f"完成任务后，请在 {self.tasks_md_path} 中更新状态：",
            f"- 将任务 {task.task_id} 状态改为 🟩 完成",
            "- 添加执行日志，包含完成时间与 SubAgent ID",
            "- 将所有检查清单项勾选为已完成",
            "",
            "如果遇到错误，请将状态更新为 🟥 失败，并记录问题说明。",
        ])

        return "\n".join(prompt_lines)

    async def execute_task(self, task: Task, wave_num: int = 0) -> ExecutionResult:
        """执行单个任务 (模拟 SubAgent 执行)。

        v1.2: 使用 task.profile 选择配置。
        v1.3: 添加 agent_id、wave、retry_count 字段。

        在实际实现中，这会启动一个 Claude Code SubAgent。
        目前是模拟执行，返回模拟结果。

        参数：
            task: 要执行的任务
            wave_num: v1.3 - 任务所属的 Wave 编号

        返回：
            包含执行详情的 ExecutionResult
        """
        # v1.3: 生成唯一的 agent_id
        agent_id = _generate_agent_id()

        # v1.3: 获取重试计数
        retry_count = self._retry_counts.get(task.task_id, 0)

        # 使用自定义执行器 (如果设置)
        if self._task_executor:
            result = self._task_executor(task)
            # 更新 v1.3 字段
            result.agent_id = agent_id
            result.wave = wave_num
            result.retry_count = retry_count
            return result

        # v1.2: 获取 profile 配置
        profile = self.get_task_profile(task)
        task_timeout_ms = profile.timeout if profile.timeout != 300000 else self.timeout_ms

        # 默认模拟实现
        started_at = datetime.now()
        start_time = time.time()

        try:
            async with self._semaphore:
                # 模拟任务执行延迟
                await asyncio.sleep(0.1)

                # 模拟执行逻辑
                # 实际实现中: 启动 SubAgent, 监控执行, 收集结果

                # 模拟 80% 成功率
                import random
                success = random.random() > 0.2

                duration = time.time() - start_time
                completed_at = datetime.now()

                if success:
                    return ExecutionResult(
                        task_id=task.task_id,
                        success=True,
                        output=f"任务 {task.task_id} 执行成功",
                        duration_seconds=duration,
                        started_at=started_at,
                        completed_at=completed_at,
                        agent_id=agent_id,
                        wave=wave_num,
                        retry_count=retry_count,
                    )
                else:
                    return ExecutionResult(
                        task_id=task.task_id,
                        success=False,
                        output=f"任务 {task.task_id} 执行输出",
                        error="模拟执行失败",
                        duration_seconds=duration,
                        started_at=started_at,
                        completed_at=completed_at,
                        agent_id=agent_id,
                        wave=wave_num,
                        retry_count=retry_count,
                    )

        except asyncio.TimeoutError:
            duration = time.time() - start_time
            completed_at = datetime.now()
            return ExecutionResult(
                task_id=task.task_id,
                success=False,
                output="",
                error=f"任务执行超时 (超过 {self.timeout_ms}ms)",
                duration_seconds=duration,
                started_at=started_at,
                completed_at=completed_at,
                agent_id=agent_id,
                wave=wave_num,
                retry_count=retry_count,
            )
        except Exception as e:
            duration = time.time() - start_time
            completed_at = datetime.now()
            return ExecutionResult(
                task_id=task.task_id,
                success=False,
                output="",
                error=f"执行异常: {e}",
                duration_seconds=duration,
                started_at=started_at,
                completed_at=completed_at,
                agent_id=agent_id,
                wave=wave_num,
                retry_count=retry_count,
            )

    async def _execute_task_with_lock(
        self,
        task: Task,
        wave_num: int = 0,
        skip_locked: bool = False,
    ) -> ExecutionResult:
        """带锁执行任务 (v1.3 新增)。

        在执行任务前尝试获取锁，执行完成后释放锁。
        如果锁被占用，根据 skip_locked 参数决定是跳过还是返回错误。

        参数：
            task: 要执行的任务
            wave_num: 任务所属的 Wave 编号
            skip_locked: 是否跳过被锁定的任务

        返回：
            ExecutionResult，包含执行结果或锁被占用的错误信息
        """
        agent_id = _generate_agent_id()
        retry_count = self._retry_counts.get(task.task_id, 0)

        # 如果没有锁管理器，直接执行
        if self.lock_manager is None:
            result = await self.execute_task(task)
            result.wave = wave_num
            return result

        # 尝试获取锁
        lock_acquired = self.lock_manager.acquire(task.task_id, agent_id)

        if not lock_acquired:
            # 锁被占用
            lock_info = self.lock_manager.get_lock_info(task.task_id)
            holder_info = ""
            if lock_info:
                holder_info = f" (由 {lock_info.agent_id} 在 {lock_info.started_at.isoformat()} 获取)"

            if skip_locked:
                return ExecutionResult(
                    task_id=task.task_id,
                    success=False,
                    output="",
                    error=f"任务被锁定，已跳过{holder_info}",
                    agent_id=agent_id,
                    wave=wave_num,
                    retry_count=retry_count,
                )
            else:
                return ExecutionResult(
                    task_id=task.task_id,
                    success=False,
                    output="",
                    error=f"无法获取任务锁，任务正在被其他实例执行{holder_info}",
                    agent_id=agent_id,
                    wave=wave_num,
                    retry_count=retry_count,
                )

        try:
            # 执行任务
            result = await self.execute_task(task)
            result.wave = wave_num
            # 确保 agent_id 一致
            result.agent_id = agent_id
            return result
        finally:
            # 释放锁
            self.lock_manager.release(task.task_id, agent_id)

    async def execute_wave(
        self,
        wave_num: int,
        use_lock: bool = True,
        skip_locked: bool = False,
    ) -> list[ExecutionResult]:
        """并发执行 Wave 内的所有任务。

        v1.3: 添加锁支持和 agent_id 追踪。

        处理流程:
        1. 获取该 Wave 内所有 IDLE 状态的任务
        2. 更新任务状态为 IN_PROGRESS
        3. 并发执行任务 (带锁保护)
        4. 收集结果并更新状态为 COMPLETED/FAILED

        参数：
            wave_num: 要执行的 Wave 编号
            use_lock: v1.3 - 是否使用锁机制
            skip_locked: v1.3 - 是否跳过被锁定的任务

        返回：
            该 Wave 内所有任务的 ExecutionResult 列表

        异常：
            ValueError: 如果 Wave 编号无效
        """
        # 获取该 Wave 的任务
        tasks = get_tasks_by_wave(self.doc, wave_num)

        if not tasks:
            raise ValueError(f"未找到波次 {wave_num} 的任务")

        # 过滤 IDLE 任务 (只执行未开始的任务)
        idle_tasks = [t for t in tasks if t.status == TaskStatus.IDLE]

        if not idle_tasks:
            # 该 Wave 的所有任务已处理
            return []

        results: list[ExecutionResult] = []

        # 更新任务状态为 IN_PROGRESS
        for task in idle_tasks:
            task.status = TaskStatus.IN_PROGRESS
            self.tasks_md_content = update_task_status_yaml(
                self.tasks_md_content,
                task.task_id,
                TaskStatus.IN_PROGRESS,
            )

        # 写入更新后的状态
        self.tasks_md_path.write_text(self.tasks_md_content, encoding="utf-8")

        # v1.3: 使用带锁的执行器
        if use_lock and self.lock_manager is not None:
            execution_tasks = [
                self._execute_task_with_lock(task, wave_num, skip_locked)
                for task in idle_tasks
            ]
        else:
            execution_tasks = [
                self.execute_task(task)
                for task in idle_tasks
            ]

        results = await asyncio.gather(*execution_tasks)
        for result in results:
            result.wave = wave_num

        # 根据结果更新任务状态
        for result in results:
            task = self.doc.all_tasks.get(result.task_id)
            if not task:
                continue

            # 确定新状态
            if result.success:
                new_status = TaskStatus.COMPLETED
                task.status = TaskStatus.COMPLETED
            else:
                new_status = TaskStatus.FAILED
                task.status = TaskStatus.FAILED
                # v1.3: 更新重试计数
                self._retry_counts[result.task_id] = result.retry_count + 1

            # 更新 tasks.yaml
            log = {
                "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "subagent_id": result.agent_id or f"agent_{result.task_id}",
            }

            self.tasks_md_content = update_task_status_yaml(
                self.tasks_md_content,
                result.task_id,
                new_status,
                log=log if result.success else None,
            )

        # 写入最终状态
        self.tasks_md_path.write_text(self.tasks_md_content, encoding="utf-8")

        return results

    async def execute_all(
        self,
        start_wave: int = 0,
        use_lock: bool = True,
    ) -> dict[int, list[ExecutionResult]]:
        """顺序执行所有 Wave。

        v1.3: 添加锁支持。

        对于每个 Wave (从 start_wave 开始):
        1. 执行该 Wave
        2. 检查是否所有任务都通过
        3. 如果有失败，停止执行并返回结果
        4. 继续下一个 Wave

        参数：
            start_wave: 开始执行的 Wave 编号 (默认: 0)
            use_lock: v1.3 - 是否使用锁机制

        返回：
            Wave 编号到 ExecutionResult 列表的映射字典

        异常：
            ValueError: 如果 start_wave 无效
        """
        if start_wave < 0:
            raise ValueError(f"start_wave 必须 >= 0，实际为：{start_wave}")

        all_results: dict[int, list[ExecutionResult]] = {}

        # 顺序执行每个 Wave
        for wave in self.doc.waves:
            if wave.wave_number < start_wave:
                continue

            # 执行 Wave
            results = await self.execute_wave(wave.wave_number, use_lock=use_lock)

            if results:
                all_results[wave.wave_number] = results

                # 检查是否有任务失败
                failed_tasks = [r for r in results if not r.success]
                if failed_tasks:
                    # 遇到失败时停止执行
                    break

        return all_results

    def get_progress_summary(self) -> dict:
        """获取当前执行进度摘要。

        返回：
            包含进度信息的字典:
            - total_tasks: 任务总数
            - completed_tasks: 已完成任务数
            - failed_tasks: 失败任务数
            - in_progress_tasks: 进行中任务数
            - idle_tasks: 未开始任务数
            - completion_percentage: 完成百分比
        """
        total = len(self.doc.all_tasks)
        completed = sum(1 for t in self.doc.all_tasks.values() if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self.doc.all_tasks.values() if t.status == TaskStatus.FAILED)
        in_progress = sum(
            1 for t in self.doc.all_tasks.values() if t.status == TaskStatus.IN_PROGRESS
        )
        idle = sum(1 for t in self.doc.all_tasks.values() if t.status == TaskStatus.IDLE)

        completion_pct = (completed / total * 100) if total > 0 else 0.0

        return {
            "total_tasks": total,
            "completed_tasks": completed,
            "failed_tasks": failed,
            "in_progress_tasks": in_progress,
            "idle_tasks": idle,
            "completion_percentage": completion_pct,
        }

    def _update_tasks_yaml(self, task_id: str, status: str, log: dict | None = None) -> None:
        """更新 tasks.yaml 文件中的任务状态。

        参数：
            task_id: 要更新的任务 ID
            status: 新状态
            log: 可选的执行日志字典，包含 completed_at, subagent_id, notes 等键
        """
        self.tasks_md_content = update_task_status_yaml(
            self.tasks_md_content,
            task_id,
            status,
            log=log,
        )
        self.tasks_md_path.write_text(self.tasks_md_content, encoding="utf-8")

    def get_retry_count(self, task_id: str) -> int:
        """获取任务的重试次数 (v1.3 新增)。

        参数：
            task_id: 任务 ID

        返回：
            重试次数
        """
        return self._retry_counts.get(task_id, 0)

    def increment_retry_count(self, task_id: str) -> int:
        """增加任务的重试次数 (v1.3 新增)。

        参数：
            task_id: 任务 ID

        返回：
            新的重试次数
        """
        current = self._retry_counts.get(task_id, 0)
        self._retry_counts[task_id] = current + 1
        return self._retry_counts[task_id]

    def cleanup_locks(self) -> list[str]:
        """清理过期的锁 (v1.3 新增)。

        返回：
            被清理的任务 ID 列表
        """
        if self.lock_manager is None:
            return []
        return self.lock_manager.cleanup_expired()

    def release_all_locks(self) -> int:
        """释放所有锁 (v1.3 新增)。

        警告: 这会强制释放所有锁，可能导致并发问题。

        返回：
            释放的锁数量
        """
        if self.lock_manager is None:
            return 0
        return self.lock_manager.force_release_all()
