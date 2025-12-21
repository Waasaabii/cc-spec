"""SubAgent 执行结果收集器。

本模块提供用于收集与聚合任务执行结果的类，
按 Wave 组织，并生成执行报告。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from cc_spec.subagent.executor import ExecutionResult


@dataclass
class WaveResult:
    """单个 Wave 执行的聚合结果。

    属性：
        wave_num: Wave 编号
        started_at: Wave 开始执行时间戳
        completed_at: Wave 执行完成时间戳（执行中则为 None）
        results: 本 Wave 内的任务执行结果列表
    """

    wave_num: int
    started_at: datetime
    completed_at: datetime | None = None
    results: list[ExecutionResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        """检查该 Wave 中的任务是否全部通过。

        返回：
            全部成功则为 True；任意失败则为 False
        """
        return all(result.success for result in self.results)

    @property
    def failed_tasks(self) -> list[str]:
        """获取失败任务 ID 列表。

        返回：
            执行失败的任务 ID 列表
        """
        return [result.task_id for result in self.results if not result.success]

    @property
    def duration_seconds(self) -> float:
        """计算该 Wave 的总耗时。

        返回：
            秒数；若 Wave 未完成则为 0.0
        """
        if self.completed_at is None:
            return 0.0
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def success_rate(self) -> float:
        """计算该 Wave 内任务的成功率。

        返回：
            成功率百分比（0-100）
        """
        if not self.results:
            return 0.0
        successful = sum(1 for r in self.results if r.success)
        return (successful / len(self.results)) * 100


class ResultCollector:
    """收集并聚合执行结果。

    该类管理任务执行结果的收集与聚合，按 Wave 组织，
    并提供汇总统计与报告生成功能。

    属性：
        wave_results: Wave 编号到 WaveResult 的映射
        start_time: 总体执行开始时间
        end_time: 总体执行结束时间（执行中则为 None）
    """

    def __init__(self) -> None:
        """初始化结果收集器。"""
        self.wave_results: dict[int, WaveResult] = {}
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None

    def start_execution(self) -> None:
        """记录总体执行开始时间。"""
        self.start_time = datetime.now()

    def end_execution(self) -> None:
        """记录总体执行结束时间。"""
        self.end_time = datetime.now()

    def start_wave(self, wave_num: int) -> None:
        """记录某个 Wave 的开始执行时间。

        参数：
            wave_num: 开始的 Wave 编号
        """
        if wave_num not in self.wave_results:
            self.wave_results[wave_num] = WaveResult(
                wave_num=wave_num,
                started_at=datetime.now(),
            )

    def add_result(self, wave_num: int, result: ExecutionResult) -> None:
        """添加一个任务执行结果。

        参数：
            wave_num: 该结果所属的 Wave 编号
            result: 要添加的任务执行结果

        异常：
            ValueError: Wave 尚未开始时抛出
        """
        if wave_num not in self.wave_results:
            raise ValueError(
                f"波次 {wave_num} 尚未开始，请先调用 start_wave()。"
            )

        self.wave_results[wave_num].results.append(result)

    def end_wave(self, wave_num: int) -> None:
        """记录某个 Wave 的结束执行时间。

        参数：
            wave_num: 结束的 Wave 编号

        异常：
            ValueError: Wave 尚未开始时抛出
        """
        if wave_num not in self.wave_results:
            raise ValueError(f"波次 {wave_num} 尚未开始")

        self.wave_results[wave_num].completed_at = datetime.now()

    def get_summary(self) -> dict:
        """获取执行汇总信息。

        返回：
            包含汇总统计信息的字典，包括：
            - total_waves: 执行的 Wave 总数
            - total_tasks: 执行的任务总数
            - successful_tasks: 成功任务数
            - failed_tasks: 失败任务数
            - total_duration_seconds: 总执行耗时（秒）
            - success_rate: 总体成功率百分比
        """
        total_tasks = sum(len(wave.results) for wave in self.wave_results.values())
        successful_tasks = sum(
            sum(1 for r in wave.results if r.success)
            for wave in self.wave_results.values()
        )
        failed_tasks = total_tasks - successful_tasks

        total_duration = 0.0
        if self.start_time and self.end_time:
            total_duration = (self.end_time - self.start_time).total_seconds()

        success_rate = (successful_tasks / total_tasks * 100) if total_tasks > 0 else 0.0

        return {
            "total_waves": len(self.wave_results),
            "total_tasks": total_tasks,
            "successful_tasks": successful_tasks,
            "failed_tasks": failed_tasks,
            "total_duration_seconds": total_duration,
            "success_rate": success_rate,
        }

    @staticmethod
    def build_progress_entry(result: ExecutionResult) -> dict[str, Any]:
        """将执行结果转换为 progress.yaml 可写入的条目结构。"""
        status = "completed" if result.success else "failed"
        if result.exit_code == 124:
            status = "timeout"

        entry: dict[str, Any] = {
            "id": result.task_id,
            "status": status,
            "retry_count": int(result.retry_count or 0),
        }
        if result.agent_id:
            entry["agent_id"] = result.agent_id
        if result.started_at:
            entry["started_at"] = result.started_at.isoformat()
        if result.completed_at:
            entry["completed_at"] = result.completed_at.isoformat()
        if result.error:
            entry["notes"] = str(result.error)[:200]
        return entry

    def generate_report(self) -> str:
        """生成 Markdown 格式的执行报告。

        返回：
            格式化后的 Markdown 报告字符串
        """
        lines = [
            "# SubAgent 执行报告",
            "",
        ]

        # 总体摘要
        summary = self.get_summary()

        lines.extend([
            "## 汇总",
            "",
            f"- **波次数**：{summary['total_waves']}",
            f"- **任务数**：{summary['total_tasks']}",
            f"- **成功**：{summary['successful_tasks']}",
            f"- **失败**：{summary['failed_tasks']}",
            f"- **成功率**：{summary['success_rate']:.1f}%",
            f"- **总耗时**：{summary['total_duration_seconds']:.2f} 秒",
            "",
        ])

        # 添加执行时间线
        if self.start_time:
            lines.extend([
                "## 时间线",
                "",
                f"- **开始**：{self.start_time.isoformat()}",
            ])
            if self.end_time:
                lines.append(f"- **结束**：{self.end_time.isoformat()}")
            lines.append("")

        # Wave 详情
        lines.extend([
            "## 波次详情",
            "",
        ])

        for wave_num in sorted(self.wave_results.keys()):
            wave = self.wave_results[wave_num]

            status_icon = "√" if wave.all_passed else "×"
            lines.extend([
                f"### 波次 {wave_num} {status_icon}",
                "",
                f"- **开始**：{wave.started_at.isoformat()}",
            ])

            if wave.completed_at:
                lines.append(f"- **结束**：{wave.completed_at.isoformat()}")
                lines.append(f"- **耗时**：{wave.duration_seconds:.2f} 秒")

            lines.extend([
                f"- **任务数**：{len(wave.results)}",
                f"- **成功率**：{wave.success_rate:.1f}%",
                "",
            ])

            # 任务结果表
            lines.extend([
                "| 任务 ID | 状态 | 耗时（秒） | 错误 |",
                "|---------|------|-----------|------|",
            ])

            for result in wave.results:
                status = "√ 成功" if result.success else "× 失败"
                error = result.error or "-"
                lines.append(
                    f"| {result.task_id} | {status} | {result.duration_seconds:.2f} | {error} |"
                )

            lines.append("")

        # 失败任务摘要
        failed_tasks_list = []
        for wave in self.wave_results.values():
            for result in wave.results:
                if not result.success:
                    failed_tasks_list.append((wave.wave_num, result))

        if failed_tasks_list:
            lines.extend([
                "## 失败任务",
                "",
            ])

            for wave_num, result in failed_tasks_list:
                lines.extend([
                    f"### {result.task_id}（波次 {wave_num}）",
                    "",
                    f"**错误**：{result.error}",
                    "",
                    "**输出**：",
                    "```",
                    result.output,
                    "```",
                    "",
                ])

        return "\n".join(lines)

    def has_failures(self) -> bool:
        """检查执行过程中是否有任务失败。

        返回：
            任意任务失败则为 True，否则为 False
        """
        return any(not wave.all_passed for wave in self.wave_results.values())

    def get_failed_waves(self) -> list[int]:
        """获取存在失败任务的 Wave 编号列表。

        返回：
            含失败任务的 Wave 编号列表
        """
        return [
            wave_num
            for wave_num, wave in self.wave_results.items()
            if not wave.all_passed
        ]
