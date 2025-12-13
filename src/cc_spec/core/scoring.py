"""打分机制模块。

提供 checklist 解析、分数计算和失败报告生成功能。
v1.3 新增: 四维度打分机制 (功能完整性、代码质量、测试覆盖、文档同步)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from .config import Dimension, DimensionConfig, ScoringConfig, DEFAULT_DIMENSION_CONFIGS


class CheckStatus(Enum):
    """检查项状态枚举。"""

    PASSED = "passed"   # [x] 已完成
    FAILED = "failed"   # [ ] 未完成
    SKIPPED = "skipped"  # [-] 已跳过


@dataclass
class CheckItem:
    """单个检查项数据类。

    属性：
        description: 检查项描述文本
        status: 当前状态 (PASSED/FAILED/SKIPPED)
        score: 该项获得的分数 (0-10)
        max_score: 该项的满分值
        notes: 可选的备注说明
        dimension: v1.3 新增 - 该项所属的维度
    """

    description: str
    status: CheckStatus
    score: int = 0
    max_score: int = 10
    notes: str | None = None
    dimension: Dimension | None = None  # v1.3 新增


@dataclass
class ScoreResult:
    """打分结果数据类 (v1.2 兼容)。

    属性：
        items: 所有检查项列表
        total_score: 获得的总分
        max_score: 满分值
        percentage: 百分比得分 (0-100)
        passed: 是否通过阈值
        threshold: 通过阈值
        failed_items: 未通过的检查项列表
    """

    items: list[CheckItem]
    total_score: int
    max_score: int
    percentage: float
    passed: bool
    threshold: int
    failed_items: list[CheckItem]


# ============================================================================
# v1.3 新增: 四维度打分数据结构
# ============================================================================

@dataclass
class DimensionScore:
    """单个维度的得分 (v1.3 新增)。

    属性：
        dimension: 维度类型
        earned: 获得的分数
        max_score: 该维度的满分值
        percentage: 得分百分比
        items: 该维度下的检查项列表
        weight: 该维度的权重
    """

    dimension: Dimension
    earned: int
    max_score: int
    percentage: float
    items: list[CheckItem]
    weight: int = 25  # 默认权重


@dataclass
class TaskScore:
    """单个任务的打分结果 (v1.3 新增)。

    属性：
        task_id: 任务 ID
        dimension_scores: 各维度得分字典
        total_score: 加权总分 (0-100)
        passed: 是否通过阈值
        failed_dimensions: 未通过的维度列表
        items: 该任务的所有检查项
    """

    task_id: str
    dimension_scores: dict[Dimension, DimensionScore]
    total_score: float
    passed: bool
    failed_dimensions: list[Dimension]
    items: list[CheckItem] = field(default_factory=list)


@dataclass
class ChecklistResult:
    """完整的 checklist 打分结果 (v1.3 新增)。

    属性：
        task_scores: 各任务的打分结果列表
        overall_score: 整体加权平均分
        overall_passed: 是否整体通过
        threshold: 通过阈值
        failed_tasks: 未通过的任务 ID 列表
        recommendations: 改进建议列表
        dimension_summary: 各维度的汇总得分
    """

    task_scores: list[TaskScore]
    overall_score: float
    overall_passed: bool
    threshold: int
    failed_tasks: list[str]
    recommendations: list[str] = field(default_factory=list)
    dimension_summary: dict[Dimension, DimensionScore] = field(default_factory=dict)


# ============================================================================
# 解析函数
# ============================================================================

def parse_checklist(content: str) -> list[CheckItem]:
    """解析 markdown 内容中的检查项。

    支持的格式:
    - [x] 描述 -> PASSED
    - [ ] 描述 -> FAILED
    - [-] 描述 -> SKIPPED

    参数：
        content: 包含检查项的 markdown 内容

    返回：
        解析后的 CheckItem 列表
    """
    items: list[CheckItem] = []

    # 匹配模式: - [x], - [ ], 或 - [-] 后跟描述
    pattern = r"^[-*]\s+\[([ x\-])\]\s+(.+)$"

    for line in content.split("\n"):
        line = line.strip()
        match = re.match(pattern, line, re.IGNORECASE)

        if not match:
            continue

        checkbox = match.group(1).lower()
        description = match.group(2).strip()

        if checkbox == "x":
            status = CheckStatus.PASSED
            score = 10
        elif checkbox == "-":
            status = CheckStatus.SKIPPED
            score = 0
        else:  # checkbox 为空格
            status = CheckStatus.FAILED
            score = 0

        items.append(
            CheckItem(
                description=description,
                status=status,
                score=score,
                max_score=10,
            )
        )

    return items


def extract_checklists_from_tasks_md(tasks_content: str) -> dict[str, list[CheckItem]]:
    """从 tasks.md 内容中提取各任务的检查项。

    解析 tasks.md 文件，提取每个任务的检查项列表。
    任务通过带有任务 ID 的 markdown 标题识别。

    预期格式:
        ### 01-SETUP - 项目设置
        ...
        **Checklist**: 或 **检查清单**:
        - [x] 创建项目结构
        - [ ] 配置依赖

    参数：
        tasks_content: tasks.md 文件的内容

    返回：
        任务 ID 到检查项列表的映射字典
        示例: {"01-SETUP": [CheckItem(...), ...]}
    """
    result: dict[str, list[CheckItem]] = {}

    # 按任务标题分割 (### XX-NAME 格式)
    task_pattern = r"^\s*###\s+([A-Z0-9]+[A-Z0-9]*-[A-Z0-9]+)\s*-"
    current_task_id: str | None = None
    current_section: list[str] = []

    for line in tasks_content.split("\n"):
        task_match = re.match(task_pattern, line, re.IGNORECASE)

        if task_match:
            # 处理上一个任务的检查项
            if current_task_id and current_section:
                _process_task_checklist(current_task_id, current_section, result)

            # 开始新任务
            current_task_id = task_match.group(1).upper()
            current_section = [line]
        else:
            # 累积当前任务的行
            if current_task_id:
                current_section.append(line)

    # 处理最后一个任务
    if current_task_id and current_section:
        _process_task_checklist(current_task_id, current_section, result)

    return result


def _process_task_checklist(
    task_id: str, section_lines: list[str], result: dict[str, list[CheckItem]]
) -> None:
    """处理任务区块并提取检查项。

    参数：
        task_id: 任务标识符
        section_lines: 任务区块的行列表
        result: 存储结果的字典
    """
    section_content = "\n".join(section_lines)

    if "**Checklist**" not in section_content and "**检查清单**" not in section_content:
        return

    # 提取 "**Checklist**:" / "**检查清单**:" 后的内容
    checklist_match = re.search(
        r"\*\*(?:Checklist|检查清单)\*\*:?\s*\n((?:\s*[-*]\s+\[[ xX\-]\].+\n?)+)",
        section_content,
        re.MULTILINE,
    )

    if checklist_match:
        checklist_content = checklist_match.group(1)
        items = parse_checklist(checklist_content)
        if items:
            result[task_id] = items


# ============================================================================
# v1.2 兼容: 简单打分函数
# ============================================================================

def calculate_score(
    items: list[CheckItem],
    threshold: int = 80,
) -> ScoreResult:
    """计算检查项的得分 (v1.2 兼容)。

    打分规则:
    - 每个 PASSED 项获得满分 (默认 10 分)
    - 每个 FAILED 项获得 0 分
    - SKIPPED 项不计入总分和满分

    参数：
        items: 要评分的检查项列表
        threshold: 通过所需的最低百分比 (0-100)

    返回：
        包含计算结果的 ScoreResult 对象
    """
    # 过滤掉跳过的项
    scored_items = [item for item in items if item.status != CheckStatus.SKIPPED]

    # 计算总分
    total_score = sum(item.score for item in scored_items)
    max_score = sum(item.max_score for item in scored_items)

    # 计算百分比 (处理除零)
    percentage = (total_score / max_score * 100) if max_score > 0 else 0.0

    # 判断是否通过
    passed = percentage >= threshold

    # 获取失败项
    failed_items = [item for item in items if item.status == CheckStatus.FAILED]

    return ScoreResult(
        items=items,
        total_score=total_score,
        max_score=max_score,
        percentage=percentage,
        passed=passed,
        threshold=threshold,
        failed_items=failed_items,
    )


# ============================================================================
# v1.3 新增: 四维度打分函数
# ============================================================================

def _classify_item(
    item: CheckItem,
    dimension_configs: dict[Dimension, DimensionConfig] | None = None,
) -> Dimension:
    """根据关键词将检查项分类到维度。

    遍历各维度的关键词列表，找到第一个匹配的维度。
    如果没有匹配，默认归类到功能完整性维度。

    参数：
        item: 要分类的检查项
        dimension_configs: 维度配置字典，None 使用默认配置

    返回：
        匹配的维度
    """
    if dimension_configs is None:
        dimension_configs = DEFAULT_DIMENSION_CONFIGS

    description_lower = item.description.lower()

    # 按权重从高到低的顺序检查 (功能 > 质量 > 测试 > 文档)
    check_order = [
        Dimension.TEST_COVERAGE,    # 先检查测试相关
        Dimension.DOCUMENTATION,    # 再检查文档相关
        Dimension.CODE_QUALITY,     # 然后检查质量相关
        Dimension.FUNCTIONALITY,    # 最后是功能 (默认)
    ]

    for dim in check_order:
        config = dimension_configs.get(dim)
        if config is None:
            continue

        for keyword in config.keywords:
            if keyword.lower() in description_lower:
                return dim

    # 默认归类到功能完整性
    return Dimension.FUNCTIONALITY


def classify_items(
    items: list[CheckItem],
    scoring_config: ScoringConfig | None = None,
) -> dict[Dimension, list[CheckItem]]:
    """将检查项列表分类到各维度。

    参数：
        items: 检查项列表
        scoring_config: 打分配置，None 使用默认配置

    返回：
        维度到检查项列表的映射字典
    """
    # 获取维度配置
    if scoring_config is not None:
        dimension_configs = {
            Dimension(name): config
            for name, config in scoring_config.dimensions.items()
        }
    else:
        dimension_configs = DEFAULT_DIMENSION_CONFIGS

    # 初始化结果字典
    result: dict[Dimension, list[CheckItem]] = {dim: [] for dim in Dimension}

    # 分类每个检查项
    for item in items:
        dim = _classify_item(item, dimension_configs)
        item.dimension = dim  # 更新检查项的维度属性
        result[dim].append(item)

    return result


def calculate_dimension_score(
    dimension: Dimension,
    items: list[CheckItem],
    weight: int = 25,
) -> DimensionScore:
    """计算单个维度的得分。

    参数：
        dimension: 维度类型
        items: 该维度下的检查项列表
        weight: 维度权重

    返回：
        维度得分对象
    """
    # 过滤掉跳过的项
    scored_items = [item for item in items if item.status != CheckStatus.SKIPPED]

    if not scored_items:
        return DimensionScore(
            dimension=dimension,
            earned=0,
            max_score=0,
            percentage=100.0,  # 没有检查项时视为通过
            items=items,
            weight=weight,
        )

    # 计算得分
    earned = sum(item.score for item in scored_items)
    max_score = sum(item.max_score for item in scored_items)
    percentage = (earned / max_score * 100) if max_score > 0 else 0.0

    return DimensionScore(
        dimension=dimension,
        earned=earned,
        max_score=max_score,
        percentage=percentage,
        items=items,
        weight=weight,
    )


def calculate_task_score(
    task_id: str,
    items: list[CheckItem],
    scoring_config: ScoringConfig | None = None,
    threshold: int = 80,
) -> TaskScore:
    """计算单个任务的四维度加权得分 (v1.3 核心函数)。

    算法:
    1. 根据关键词将检查项分类到各维度
    2. 计算每个维度的得分率
    3. 按权重计算加权总分
    4. 判断是否通过阈值

    参数：
        task_id: 任务 ID
        items: 该任务的检查项列表
        scoring_config: 打分配置，None 使用默认配置
        threshold: 通过阈值

    返回：
        任务打分结果
    """
    # 获取配置
    if scoring_config is None:
        scoring_config = ScoringConfig()

    # 获取维度配置
    dimension_configs = {
        Dimension(name): config
        for name, config in scoring_config.dimensions.items()
    }

    # 1. 分类检查项到各维度
    dimension_items = classify_items(items, scoring_config)

    # 2. 计算每个维度得分
    dimension_scores: dict[Dimension, DimensionScore] = {}
    for dim, dim_items in dimension_items.items():
        config = dimension_configs.get(dim) or DimensionConfig()
        dimension_scores[dim] = calculate_dimension_score(
            dimension=dim,
            items=dim_items,
            weight=config.weight,
        )

    # 3. 计算加权总分
    weighted_sum = 0.0
    total_weight = 0
    for dim, score in dimension_scores.items():
        if score.max_score > 0:  # 只计算有检查项的维度
            weighted_sum += score.percentage * score.weight
            total_weight += score.weight

    total_score = weighted_sum / total_weight if total_weight > 0 else 0.0

    # 4. 判断通过状态
    passed = total_score >= threshold
    failed_dimensions = [
        dim for dim, score in dimension_scores.items()
        if score.max_score > 0 and score.percentage < threshold
    ]

    return TaskScore(
        task_id=task_id,
        dimension_scores=dimension_scores,
        total_score=total_score,
        passed=passed,
        failed_dimensions=failed_dimensions,
        items=items,
    )


def calculate_checklist_result(
    task_checklists: dict[str, list[CheckItem]],
    scoring_config: ScoringConfig | None = None,
    threshold: int = 80,
) -> ChecklistResult:
    """计算完整的 checklist 打分结果 (v1.3 核心函数)。

    参数：
        task_checklists: 任务 ID 到检查项列表的映射
        scoring_config: 打分配置
        threshold: 通过阈值

    返回：
        完整的打分结果
    """
    if scoring_config is None:
        scoring_config = ScoringConfig()

    # 计算每个任务的得分
    task_scores: list[TaskScore] = []
    for task_id, items in task_checklists.items():
        task_score = calculate_task_score(
            task_id=task_id,
            items=items,
            scoring_config=scoring_config,
            threshold=threshold,
        )
        task_scores.append(task_score)

    # 计算整体得分 (所有任务的平均分)
    if task_scores:
        overall_score = sum(ts.total_score for ts in task_scores) / len(task_scores)
    else:
        overall_score = 0.0

    overall_passed = overall_score >= threshold
    failed_tasks = [ts.task_id for ts in task_scores if not ts.passed]

    # 汇总各维度得分
    dimension_summary = _calculate_dimension_summary(task_scores, scoring_config)

    # 生成改进建议
    recommendations = _generate_recommendations(task_scores, threshold)

    return ChecklistResult(
        task_scores=task_scores,
        overall_score=overall_score,
        overall_passed=overall_passed,
        threshold=threshold,
        failed_tasks=failed_tasks,
        recommendations=recommendations,
        dimension_summary=dimension_summary,
    )


def _calculate_dimension_summary(
    task_scores: list[TaskScore],
    scoring_config: ScoringConfig,
) -> dict[Dimension, DimensionScore]:
    """计算各维度的汇总得分。

    参数：
        task_scores: 任务得分列表
        scoring_config: 打分配置

    返回：
        维度汇总得分字典
    """
    summary: dict[Dimension, DimensionScore] = {}

    for dim in Dimension:
        total_earned = 0
        total_max = 0
        all_items: list[CheckItem] = []

        for task_score in task_scores:
            dim_score = task_score.dimension_scores.get(dim)
            if dim_score:
                total_earned += dim_score.earned
                total_max += dim_score.max_score
                all_items.extend(dim_score.items)

        config = scoring_config.get_dimension_config(dim)
        percentage = (total_earned / total_max * 100) if total_max > 0 else 100.0

        summary[dim] = DimensionScore(
            dimension=dim,
            earned=total_earned,
            max_score=total_max,
            percentage=percentage,
            items=all_items,
            weight=config.weight,
        )

    return summary


def _generate_recommendations(
    task_scores: list[TaskScore],
    threshold: int,
) -> list[str]:
    """根据打分结果生成改进建议。

    参数：
        task_scores: 任务得分列表
        threshold: 通过阈值

    返回：
        改进建议列表
    """
    recommendations: list[str] = []

    # 收集各维度的低分情况
    dim_failures: dict[Dimension, int] = {dim: 0 for dim in Dimension}

    for task_score in task_scores:
        for dim in task_score.failed_dimensions:
            dim_failures[dim] += 1

    # 根据失败次数生成建议
    dim_names = {
        Dimension.FUNCTIONALITY: "功能完整性",
        Dimension.CODE_QUALITY: "代码质量",
        Dimension.TEST_COVERAGE: "测试覆盖",
        Dimension.DOCUMENTATION: "文档同步",
    }

    for dim, count in dim_failures.items():
        if count > 0:
            name = dim_names.get(dim, dim.value)
            if count == 1:
                recommendations.append(f"有 1 个任务在 {name} 维度未达标")
            else:
                recommendations.append(f"有 {count} 个任务在 {name} 维度未达标")

    # 添加通用建议
    if dim_failures[Dimension.TEST_COVERAGE] > 0:
        recommendations.append("建议: 补充单元测试和集成测试")
    if dim_failures[Dimension.DOCUMENTATION] > 0:
        recommendations.append("建议: 更新文档和代码注释")
    if dim_failures[Dimension.CODE_QUALITY] > 0:
        recommendations.append("建议: 运行 lint 检查并修复代码风格问题")

    return recommendations


# ============================================================================
# 格式化输出函数
# ============================================================================

def format_result(result: ScoreResult) -> str:
    """格式化打分结果为可读字符串 (v1.2 兼容)。

    参数：
        result: 打分结果

    返回：
        格式化的字符串
    """
    lines = [
        "# Checklist 打分结果",
        "",
        f"**总分**: {result.total_score}/{result.max_score}",
        f"**百分比**: {result.percentage:.1f}%",
        f"**阈值**: {result.threshold}%",
        f"**状态**: {'√ 通过' if result.passed else '× 未通过'}",
        "",
    ]

    # 显示检查项明细
    lines.append("## 检查项")
    lines.append("")

    for item in result.items:
        status_symbol = {
            CheckStatus.PASSED: "[x]",
            CheckStatus.FAILED: "[ ]",
            CheckStatus.SKIPPED: "[-]",
        }[item.status]

        score_info = ""
        if item.status != CheckStatus.SKIPPED:
            score_info = f" ({item.score}/{item.max_score})"

        lines.append(f"- {status_symbol} {item.description}{score_info}")

        if item.notes:
            lines.append(f"  > {item.notes}")

    # 显示失败项
    if result.failed_items:
        lines.append("")
        lines.append("## 未通过项")
        lines.append("")

        for item in result.failed_items:
            lines.append(f"- {item.description}")

    return "\n".join(lines)


def format_dimension_report(result: ChecklistResult) -> str:
    """格式化四维度打分报告 (v1.3 新增)。

    参数：
        result: 完整打分结果

    返回：
        Markdown 格式的报告
    """
    lines = [
        "# Checklist 打分报告",
        "",
        f"**阈值**: {result.threshold}%",
        f"**整体得分**: {result.overall_score:.1f}%",
        f"**状态**: {'√ 通过' if result.overall_passed else '× 未通过'}",
        "",
        "## 总览",
        "",
        "| 任务 ID | 总分 | 功能 | 质量 | 测试 | 文档 | 状态 |",
        "|---------|------|------|------|------|------|------|",
    ]

    # 任务得分表格
    for task_score in result.task_scores:
        func_pct = task_score.dimension_scores.get(Dimension.FUNCTIONALITY)
        qual_pct = task_score.dimension_scores.get(Dimension.CODE_QUALITY)
        test_pct = task_score.dimension_scores.get(Dimension.TEST_COVERAGE)
        doc_pct = task_score.dimension_scores.get(Dimension.DOCUMENTATION)

        func_str = f"{func_pct.percentage:.0f}" if func_pct and func_pct.max_score > 0 else "-"
        qual_str = f"{qual_pct.percentage:.0f}" if qual_pct and qual_pct.max_score > 0 else "-"
        test_str = f"{test_pct.percentage:.0f}" if test_pct and test_pct.max_score > 0 else "-"
        doc_str = f"{doc_pct.percentage:.0f}" if doc_pct and doc_pct.max_score > 0 else "-"

        status = "√ 通过" if task_score.passed else "× 未通过"

        lines.append(
            f"| {task_score.task_id} | {task_score.total_score:.0f} | "
            f"{func_str} | {qual_str} | {test_str} | {doc_str} | {status} |"
        )

    # 维度汇总
    lines.extend([
        "",
        "## 维度汇总",
        "",
        "| 维度 | 权重 | 得分 | 状态 |",
        "|------|------|------|------|",
    ])

    dim_names = {
        Dimension.FUNCTIONALITY: "功能完整性",
        Dimension.CODE_QUALITY: "代码质量",
        Dimension.TEST_COVERAGE: "测试覆盖",
        Dimension.DOCUMENTATION: "文档同步",
    }

    for dim in Dimension:
        summary = result.dimension_summary.get(dim)
        if summary:
            name = dim_names.get(dim, dim.value)
            status = "√" if summary.percentage >= result.threshold else "×"
            lines.append(
                f"| {name} | {summary.weight}% | {summary.percentage:.1f}% | {status} |"
            )

    # 改进建议
    if result.recommendations:
        lines.extend([
            "",
            "## 改进建议",
            "",
        ])
        for rec in result.recommendations:
            lines.append(f"- {rec}")

    return "\n".join(lines)


def generate_failure_report(result: ScoreResult) -> str:
    """生成失败报告 (v1.2 兼容)。

    参数：
        result: 打分结果

    返回：
        Markdown 格式的失败报告
    """
    lines = [
        "# Checklist 验证失败",
        "",
        f"checklist 验证未达到要求的阈值 {result.threshold}%。",
        f"您的得分: **{result.percentage:.1f}%** ({result.total_score}/{result.max_score})",
        "",
        "## 未通过项",
        "",
        "以下项目需要处理:",
        "",
    ]

    for idx, item in enumerate(result.failed_items, 1):
        lines.append(f"{idx}. **{item.description}**")

        if item.notes:
            lines.append(f"   - 备注: {item.notes}")

        lines.append("")

    lines.extend([
        "## 下一步",
        "",
        "要继续工作流:",
        "",
        "1. 查看上述未通过的项目",
        "2. 完成缺失的任务",
        "3. 运行 `cc-spec clarify <change-name>` 标记任务返工",
        "4. 修改完成后重新运行 checklist 验证",
        "",
    ])

    return "\n".join(lines)


def generate_failure_report_v13(result: ChecklistResult) -> str:
    """生成增强的失败报告 (v1.3 新增)。

    包含四维度详细分析和针对性的改进建议。

    参数：
        result: 完整打分结果

    返回：
        Markdown 格式的详细失败报告
    """
    lines = [
        "# Checklist 验证失败",
        "",
        f"checklist 验证未达到要求的阈值 {result.threshold}%。",
        f"整体得分: **{result.overall_score:.1f}%**",
        "",
    ]

    # 未通过的任务详情
    for task_score in result.task_scores:
        if not task_score.passed:
            lines.extend([
                f"## {task_score.task_id}（{task_score.total_score:.0f} 分）×",
                "",
            ])

            dim_names = {
                Dimension.FUNCTIONALITY: "功能完整性",
                Dimension.CODE_QUALITY: "代码质量",
                Dimension.TEST_COVERAGE: "测试覆盖",
                Dimension.DOCUMENTATION: "文档同步",
            }

            for dim in Dimension:
                dim_score = task_score.dimension_scores.get(dim)
                if dim_score and dim_score.max_score > 0:
                    name = dim_names.get(dim, dim.value)
                    status = "√" if dim_score.percentage >= result.threshold else "×"
                    lines.append(
                        f"### {name} ({dim_score.percentage:.0f}/100) {status}"
                    )
                    lines.append("")

                    for item in dim_score.items:
                        if item.status == CheckStatus.PASSED:
                            lines.append(f"- [x] {item.description}")
                        elif item.status == CheckStatus.FAILED:
                            lines.append(f"- [ ] {item.description} ← **需要完成**")
                        else:
                            lines.append(f"- [-] {item.description}")

                    lines.append("")

    # 改进建议
    if result.recommendations:
        lines.extend([
            "## 改进建议",
            "",
        ])
        for rec in result.recommendations:
            lines.append(f"- {rec}")
        lines.append("")

    # 下一步
    lines.extend([
        "## 下一步",
        "",
        "× 未达到阈值，需要返工",
        "",
        "1. 运行 `cc-spec clarify <task-id>` 标记任务返工",
        "2. 完成上述未通过的检查项",
        "3. 重新运行 `cc-spec checklist` 验证",
        "",
    ])

    return "\n".join(lines)
