"""SubAgent 执行器模块。

提供 SubAgentExecutor 类用于管理任务的并发执行。
任务按 Wave 分组，同一 Wave 内的任务并行执行，Wave 之间顺序执行。

"""

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from cc_spec.codex.client import CodexClient
from cc_spec.codex.models import CodexResult
from cc_spec.core.config import Config, SubAgentProfile
from cc_spec.core.lock import LockManager
from cc_spec.rag.context_provider import ContextConfig, ContextProvider
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


def _estimate_tokens(text: str) -> int:
    """估算文本的 token 数量。

    使用简单的启发式方法：平均每 4 个字符约 1 个 token。
    中文字符按每字符 1.5 tokens 计算。

    参数：
        text: 要估算的文本

    返回：
        估算的 token 数量
    """
    if not text:
        return 0

    # 统计中文字符
    chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other_chars = len(text) - chinese_chars

    # 中文每字符约 1.5 tokens，其他每 4 字符约 1 token
    return int(chinese_chars * 1.5 + other_chars / 4)


def _infer_project_root(tasks_path: Path) -> Path:
    """从 tasks.yaml 路径推断项目根目录。

    约定：
    - tasks.yaml 位于 `.cc-spec/changes/<change>/tasks.yaml`
    - 项目根目录为 `.cc-spec/` 的父目录
    """
    resolved = tasks_path.resolve()
    for parent in resolved.parents:
        if parent.name == ".cc-spec":
            return parent.parent
    # 兜底：使用 tasks.yaml 所在目录
    return resolved.parent


@dataclass
class ChangeSummary:
    """

    主 Agent 预处理 proposal.md 生成精简摘要，传递给 SubAgent。
    目标是将每个 SubAgent 的上下文从 ~5K 降到 ~500 tokens。

    属性：
        change_name: 变更名称
        objective: 变更目标（1-2 句话）
        scope: 影响范围（简短列表）
        tech_decisions: 技术决策要点
        estimated_tokens: 摘要的估算 token 数
    """

    change_name: str
    objective: str = ""
    scope: list[str] = field(default_factory=list)
    tech_decisions: list[str] = field(default_factory=list)
    estimated_tokens: int = 0

    def to_prompt_section(self) -> str:
        """将摘要转换为 prompt 片段。

        返回：
            格式化的摘要文本（目标 ~200 tokens）
        """
        lines = [
            f"## Change: {self.change_name}",
            "",
            f"**Objective**: {self.objective}",
        ]

        if self.scope:
            lines.append("")
            lines.append("**Scope**: " + ", ".join(self.scope[:3]))  # 最多 3 项

        if self.tech_decisions:
            lines.append("")
            lines.append("**Key Decisions**: " + "; ".join(self.tech_decisions[:2]))  # 最多 2 项

        return "\n".join(lines)


def generate_change_summary(
    change_dir: Path,
    change_name: str,
) -> ChangeSummary:
    """

    主 Agent 调用此函数预处理变更信息，生成精简摘要供 SubAgent 使用。

    参数：
        change_dir: 变更目录路径
        change_name: 变更名称

    返回：
        ChangeSummary 实例
    """
    summary = ChangeSummary(change_name=change_name)

    proposal_path = change_dir / "proposal.md"
    if not proposal_path.exists():
        summary.objective = f"执行变更 {change_name}"
        summary.estimated_tokens = _estimate_tokens(summary.to_prompt_section())
        return summary

    try:
        content = proposal_path.read_text(encoding="utf-8")

        # 提取目标（从 ## 背景与目标 或 ## 目标 章节）
        objective = _extract_section(content, ["背景与目标", "目标", "概述"])
        if objective:
            # 取第一段或前 100 字符
            first_para = objective.split("\n\n")[0].strip()
            summary.objective = first_para[:150] if len(first_para) > 150 else first_para

        # 提取范围（从 ## 范围 或 ## 影响范围 章节）
        scope_text = _extract_section(content, ["范围", "影响范围", "涉及模块"])
        if scope_text:
            # 提取列表项
            for line in scope_text.split("\n"):
                line = line.strip()
                if line.startswith("- ") or line.startswith("* "):
                    summary.scope.append(line[2:].strip()[:50])
                    if len(summary.scope) >= 3:
                        break

        # 提取技术决策（从 ## 技术决策 章节）
        tech_text = _extract_section(content, ["技术决策", "技术方案", "实现方案"])
        if tech_text:
            for line in tech_text.split("\n"):
                line = line.strip()
                if line.startswith("- ") or line.startswith("* "):
                    summary.tech_decisions.append(line[2:].strip()[:80])
                    if len(summary.tech_decisions) >= 2:
                        break

        # 如果没提取到目标，使用默认值
        if not summary.objective:
            summary.objective = f"执行变更 {change_name}"

    except Exception:
        summary.objective = f"执行变更 {change_name}"

    summary.estimated_tokens = _estimate_tokens(summary.to_prompt_section())
    return summary


def _extract_section(content: str, section_names: list[str]) -> str:
    """从 Markdown 内容中提取指定章节。

    参数：
        content: Markdown 内容
        section_names: 可能的章节名称列表

    返回：
        章节内容，未找到返回空字符串
    """
    import re

    for name in section_names:
        # 匹配 ## 章节名 或 # 章节名
        pattern = rf"^#{1,2}\s*{re.escape(name)}\s*\n(.*?)(?=^#{1,2}\s|\Z)"
        match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
        if match:
            return match.group(1).strip()

    return ""


@dataclass
class ExecutionResult:
    """任务执行结果数据类。

    agent_id, wave, retry_count

    属性：
        task_id: 执行的任务 ID
        success: 任务是否成功完成
        output: 任务执行的标准输出
        error: 错误信息 (成功时为 None)
        duration_seconds: 任务执行耗时 (秒)
        started_at: 任务开始执行的时间戳
        completed_at: 任务完成执行的时间戳
        agent_id: 
        wave: 
        retry_count: 
        session_id: Codex 线程/会话 ID（用于 resume）
        exit_code: Codex CLI 退出码
        context_tokens: v0.1.6 - 注入上下文的 token 估算
        context_sources: v0.1.6 - 上下文来源文件列表
    """

    task_id: str
    success: bool
    output: str
    error: str | None = None
    duration_seconds: float = 0.0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    agent_id: str | None = None
    wave: int = 0
    retry_count: int = 0
    session_id: str | None = None
    exit_code: int | None = None
    context_tokens: int = 0
    context_sources: list[str] = field(default_factory=list)


class SubAgentExecutor:
    """SubAgent 并行任务执行器。

    处理 tasks.yaml 文件中的任务，按 Wave 组织并在 Wave 内并发执行任务，
    同时保持 Wave 之间的顺序执行。

    
    
    

    属性：
        tasks_md_path: tasks.yaml 文件路径
        max_concurrent: 最大并发任务数
        timeout_ms: 默认任务超时时间 (毫秒)
        config: 可选的 Config 配置对象
        lock_manager: 
        doc: 解析后的 TasksDocument
        tasks_md_content: tasks.yaml 的原始内容
        change_summary: 
    """

    def __init__(
        self,
        tasks_md_path: Path,
        max_concurrent: int = 10,
        timeout_ms: int = 300000,  # 5 分钟
        config: Config | None = None,
        project_root: Path | None = None,
        codex: CodexClient | None = None,
        lock_manager: LockManager | None = None,  
        cc_spec_root: Path | None = None,  
        change_summary: ChangeSummary | None = None,  
    ):
        """初始化执行器。

        参数：
            tasks_md_path: tasks.yaml 文件路径
            max_concurrent: 最大并发任务数
            timeout_ms: 默认任务超时时间 (毫秒)
            config: 可选的 Config 配置对象
            lock_manager: 
            cc_spec_root: 
            change_summary: 

        异常：
            FileNotFoundError: 如果 tasks_md_path 不存在
            ValueError: 如果 tasks.yaml 格式无效
        """
        if not tasks_md_path.exists():
            raise FileNotFoundError(f"tasks.yaml 文件不存在: {tasks_md_path}")

        self.tasks_md_path = tasks_md_path
        self.max_concurrent = max_concurrent
        self.timeout_ms = timeout_ms
        self.config = config
        self.project_root = project_root or _infer_project_root(tasks_md_path)
        self.codex = codex or CodexClient()

        self.change_summary = change_summary

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

        self._retry_counts: dict[str, int] = {}

        # 懒加载智能上下文提供者（用于为 Codex prompt 注入项目/文件上下文）
        self._context_provider: ContextProvider | None = None

    def get_task_profile(self, task: Task) -> SubAgentProfile:
        """获取任务的 Profile 配置。

        

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

    def build_task_prompt(self, task: Task, *, smart_context: str | None = None) -> str:
        """

        使用预处理的变更摘要 + 任务定义 + 检查清单，
        将上下文从 ~5K 降到 ~500 tokens/agent。

        参数：
            task: 需要构建提示词的任务

        返回：
            精简的提示词字符串
        """
        prompt_lines = []

        # 1. 变更摘要（~200 tokens）
        if self.change_summary:
            prompt_lines.append(self.change_summary.to_prompt_section())
            prompt_lines.append("")

        # 2. 任务定义（~150 tokens）
        prompt_lines.extend([
            f"## Task: {task.task_id}",
            f"**Title**: {task.name}",
        ])

        # 依赖
        if task.dependencies:
            prompt_lines.append(f"**Dependencies**: {', '.join(task.dependencies)}")

        # 代码入口（最多 3 个）
        if task.code_entry_points:
            entries = task.code_entry_points[:3]
            prompt_lines.append(f"**Entry Points**: {', '.join(entries)}")

        # 参考文档（最多 3 个）
        if task.required_docs:
            docs = task.required_docs[:3]
            prompt_lines.append(f"**Docs**: {', '.join(docs)}")

        prompt_lines.append("")

        # 3. 智能上下文（由 cc-spec 注入，尽量精简）
        if smart_context:
            prompt_lines.append("## Smart Context")
            prompt_lines.append(smart_context.strip())
            prompt_lines.append("")

        # 4. 检查清单（~100 tokens）
        if task.checklist_items:
            prompt_lines.append("**Checklist**:")
            for item in task.checklist_items[:5]:  # 最多 5 项
                mark = "x" if item.status.value == "passed" else " "
                prompt_lines.append(f"- [{mark}] {item.description[:60]}")
            prompt_lines.append("")

        # 5. 执行说明（~50 tokens）
        prompt_lines.append("**Execution**: Complete all checklist items. Do not edit tasks.yaml (status is managed by the executor).")

        return "\n".join(prompt_lines)

    def get_prompt_stats(self, task: Task) -> dict:
        """

        参数：
            task: 任务

        返回：
            包含 token 估算的字典
        """
        prompt = self.build_task_prompt(task)
        return {
            "task_id": task.task_id,
            "prompt_tokens": _estimate_tokens(prompt),
            "summary_tokens": (
                self.change_summary.estimated_tokens if self.change_summary else 0
            ),
        }

    def _run_codex_for_task(self, task: Task, prompt: str, timeout_ms: int) -> CodexResult:
        """在当前项目根目录下调用 Codex（支持 resume）。"""
        workdir = self.project_root
        session_id = None
        if task.execution_log and task.execution_log.session_id:
            session_id = task.execution_log.session_id

        if session_id:
            return self.codex.resume(session_id, prompt, workdir, timeout_ms=timeout_ms)
        return self.codex.execute(prompt, workdir, timeout_ms=timeout_ms)

    def _get_smart_context_for_task(self, task: Task) -> tuple[str | None, int, list[str]]:
        """v0.1.6: 为任务构建智能上下文（失败则降级为 None）。"""
        try:
            if self._context_provider is None:
                self._context_provider = ContextProvider(self.project_root)
            provider = self._context_provider
        except Exception:
            return (None, 0, [])

        # 1) 读取 tasks.yaml 的 context 配置
        mode = task.context.mode if task.context else "auto"
        max_chunks = task.context.max_chunks if task.context else 10
        queries = list(task.context.queries) if task.context else []
        related_files = list(task.context.related_files) if task.context else []

        # 2) auto/hybrid 且未配置 queries：构造一个最小 query 兜底
        if mode in ("auto", "hybrid") and not queries:
            query_parts: list[str] = [task.name, task.task_id]
            if self.change_summary and self.change_summary.objective:
                query_parts.append(self.change_summary.objective)
            query_parts.extend(task.code_entry_points[:3])
            query_parts.extend(task.required_docs[:3])
            derived = " ".join([p for p in query_parts if p]).strip()
            if derived:
                queries = [derived]

        cfg = ContextConfig(
            queries=queries,
            related_files=related_files,
            max_chunks=max_chunks,
            mode=mode if mode in ("auto", "manual", "hybrid") else "auto",
        )

        try:
            ctx = provider.get_context_for_task(task.task_id, cfg)
        except Exception:
            return (None, 0, [])

        md = ctx.to_markdown()
        if not md.strip():
            return (None, 0, [])
        return (md, int(ctx.total_tokens), list(ctx.sources))

    async def execute_task(self, task: Task, wave_num: int = 0) -> ExecutionResult:
        """执行单个任务（真实调用 Codex CLI）。

        
        

        执行策略：
        - 默认使用 CodexClient.execute()
        - 若 tasks.yaml 中已记录 session_id，则优先使用 CodexClient.resume()
        - 由执行器负责更新 tasks.yaml 状态；Codex 只负责代码/文档产出

        参数：
            task: 要执行的任务
            wave_num: 

        返回：
            包含执行详情的 ExecutionResult
        """
        agent_id = _generate_agent_id()

        retry_count = self._retry_counts.get(task.task_id, 0)

        # 使用自定义执行器 (如果设置)
        if self._task_executor:
            result = self._task_executor(task)
            
            result.agent_id = agent_id
            result.wave = wave_num
            result.retry_count = retry_count
            return result

        profile = self.get_task_profile(task)
        task_timeout_ms = profile.timeout if profile.timeout != 300000 else self.timeout_ms

        started_at = datetime.now()
        start_time = time.time()

        try:
            async with self._semaphore:
                smart_context, context_tokens, context_sources = self._get_smart_context_for_task(task)
                prompt = self.build_task_prompt(task, smart_context=smart_context)

                codex_result: CodexResult = await asyncio.to_thread(
                    self._run_codex_for_task,
                    task,
                    prompt,
                    task_timeout_ms,
                )

                duration = time.time() - start_time
                completed_at = datetime.now()

                error: str | None = None
                output = codex_result.message
                if not codex_result.success:
                    stderr = codex_result.stderr or ""
                    error = stderr.strip() or f"Codex 执行失败（exit_code={codex_result.exit_code}）"

                return ExecutionResult(
                    task_id=task.task_id,
                    success=codex_result.success,
                    output=output,
                    error=error,
                    duration_seconds=duration,
                    started_at=started_at,
                    completed_at=completed_at,
                    agent_id=agent_id,
                    wave=wave_num,
                    retry_count=retry_count,
                    session_id=codex_result.session_id,
                    exit_code=codex_result.exit_code,
                    context_tokens=context_tokens,
                    context_sources=context_sources,
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
                session_id=None,
                exit_code=124,
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
                session_id=None,
                exit_code=None,
            )

    async def _execute_task_with_lock(
        self,
        task: Task,
        wave_num: int = 0,
        skip_locked: bool = False,
    ) -> ExecutionResult:
        """带锁执行任务 。

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
        resume: bool = False,
    ) -> list[ExecutionResult]:
        """并发执行 Wave 内的所有任务。

        

        处理流程:
        1. 获取该 Wave 内所有 IDLE 状态的任务
        2. 更新任务状态为 IN_PROGRESS
        3. 并发执行任务 (带锁保护)
        4. 收集结果并更新状态为 COMPLETED/FAILED

        参数：
            wave_num: 要执行的 Wave 编号
            use_lock: 
            skip_locked: 

        返回：
            该 Wave 内所有任务的 ExecutionResult 列表

        异常：
            ValueError: 如果 Wave 编号无效
        """
        # 获取该 Wave 的任务
        tasks = get_tasks_by_wave(self.doc, wave_num)

        if not tasks:
            raise ValueError(f"未找到波次 {wave_num} 的任务")

        # 过滤可执行任务
        runnable_statuses = (TaskStatus.IDLE, TaskStatus.FAILED, TaskStatus.IN_PROGRESS) if resume else (TaskStatus.IDLE,)
        runnable_tasks = [t for t in tasks if t.status in runnable_statuses]

        if not runnable_tasks:
            # 该 Wave 的所有任务已处理
            return []

        results: list[ExecutionResult] = []

        # 更新任务状态为 IN_PROGRESS
        for task in runnable_tasks:
            task.status = TaskStatus.IN_PROGRESS
            self.tasks_md_content = update_task_status_yaml(
                self.tasks_md_content,
                task.task_id,
                TaskStatus.IN_PROGRESS,
            )

        # 写入更新后的状态
        self.tasks_md_path.write_text(self.tasks_md_content, encoding="utf-8")

        if use_lock and self.lock_manager is not None:
            execution_tasks = [
                self._execute_task_with_lock(task, wave_num, skip_locked)
                for task in runnable_tasks
            ]
        else:
            execution_tasks = [
                self.execute_task(task)
                for task in runnable_tasks
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
                # 
                self._retry_counts[result.task_id] = self._retry_counts.get(result.task_id, 0) + 1

            # 更新 tasks.yaml
            log = {
                "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "subagent_id": result.agent_id or f"agent_{result.task_id}",
            }
            if result.session_id:
                log["session_id"] = result.session_id
            if result.exit_code is not None:
                log["exit_code"] = result.exit_code
            if result.error:
                # 仅保留简短错误，避免 tasks.yaml 膨胀
                log["notes"] = str(result.error)[:200]

            self.tasks_md_content = update_task_status_yaml(
                self.tasks_md_content,
                result.task_id,
                new_status,
                log=log,
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

        

        对于每个 Wave (从 start_wave 开始):
        1. 执行该 Wave
        2. 检查是否所有任务都通过
        3. 如果有失败，停止执行并返回结果
        4. 继续下一个 Wave

        参数：
            start_wave: 开始执行的 Wave 编号 (默认: 0)
            use_lock: 

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
        """获取任务的重试次数 。

        参数：
            task_id: 任务 ID

        返回：
            重试次数
        """
        return self._retry_counts.get(task_id, 0)

    def increment_retry_count(self, task_id: str) -> int:
        """增加任务的重试次数 。

        参数：
            task_id: 任务 ID

        返回：
            新的重试次数
        """
        current = self._retry_counts.get(task_id, 0)
        self._retry_counts[task_id] = current + 1
        return self._retry_counts[task_id]

    def cleanup_locks(self) -> list[str]:
        """清理过期的锁 。

        返回：
            被清理的任务 ID 列表
        """
        if self.lock_manager is None:
            return []
        return self.lock_manager.cleanup_expired()

    def release_all_locks(self) -> int:
        """释放所有锁 。

        警告: 这会强制释放所有锁，可能导致并发问题。

        返回：
            释放的锁数量
        """
        if self.lock_manager is None:
            return 0
        return self.lock_manager.force_release_all()
