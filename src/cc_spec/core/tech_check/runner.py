"""cc-spec 技术检查执行器。

该模块负责执行技术检查并返回结果。
"""

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .detector import TechRequirements


@dataclass
class CheckResult:
    """单个检查的执行结果。"""

    command: str
    success: bool
    output: str
    error: str | None
    duration_seconds: float
    check_type: str  # "test" | "lint" | "type_check" | "build"


def run_tech_checks(
    requirements: TechRequirements,
    project_root: Path,
    check_types: list[str] | None = None,  # None = 全部
) -> list[CheckResult]:
    """执行技术检查。

    执行策略：
    - lint/type-check：失败时记录警告但继续
    - test：失败时阻断后续执行
    - build：失败时阻断

    参数：
        requirements: 技术要求配置
        project_root: 项目根目录
        check_types: 要执行的检查类型列表，None 表示执行全部

    返回：
        所有检查结果列表
    """
    results: list[CheckResult] = []

    # 确定要执行的检查类型
    if check_types is None:
        check_types = ["lint", "type_check", "test", "build"]

    # 定义检查顺序和命令映射
    check_order = [
        ("lint", requirements.lint_commands),
        ("type_check", requirements.type_check_commands),
        ("test", requirements.test_commands),
        ("build", requirements.build_commands),
    ]

    # 按顺序执行检查
    for check_type, commands in check_order:
        # 跳过未选择的检查类型
        if check_type not in check_types:
            continue

        # 执行该类型的所有命令
        for command in commands:
            result = _run_single_check(command, check_type, project_root)
            results.append(result)

            # 检查是否应该阻断后续执行
            if not result.success and should_block(result):
                # 对于阻断性失败，立即返回当前结果
                return results

    return results


def should_block(result: CheckResult) -> bool:
    """判断检查失败是否应该阻断执行。

    阻断规则：
    - test 失败 → 阻断
    - build 失败 → 阻断
    - lint 失败 → 不阻断（警告）
    - type_check 失败 → 不阻断（警告）

    参数：
        result: 检查结果

    返回：
        是否应该阻断后续执行
    """
    return result.check_type in ["test", "build"]


def _run_single_check(command: str, check_type: str, project_root: Path) -> CheckResult:
    """执行单个检查命令。

    参数：
        command: 要执行的命令
        check_type: 检查类型
        project_root: 项目根目录

    返回：
        检查结果
    """
    start_time = time.time()

    try:
        # 执行命令
        process = subprocess.run(
            command,
            shell=True,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            encoding="utf-8",  # 显式指定 UTF-8 编码
            errors="replace",  # 遇到无法解码的字符时替换
            timeout=300,  # 5 分钟超时
        )

        duration = time.time() - start_time

        # 判断命令是否成功
        success = process.returncode == 0

        return CheckResult(
            command=command,
            success=success,
            output=process.stdout,
            error=process.stderr if not success else None,
            duration_seconds=duration,
            check_type=check_type,
        )

    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return CheckResult(
            command=command,
            success=False,
            output="",
            error="Command timeout after 5 minutes",
            duration_seconds=duration,
            check_type=check_type,
        )

    except Exception as e:
        duration = time.time() - start_time
        return CheckResult(
            command=command,
            success=False,
            output="",
            error=f"Failed to execute command: {e!s}",
            duration_seconds=duration,
            check_type=check_type,
        )
