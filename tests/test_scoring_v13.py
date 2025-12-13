"""v1.3 四维度打分机制测试。

测试四维度打分 (功能完整性、代码质量、测试覆盖、文档同步) 的分类、计算和报告生成。
"""

import pytest

from cc_spec.core.config import Dimension, DimensionConfig, ScoringConfig
from cc_spec.core.scoring import (
    CheckItem,
    CheckStatus,
    DimensionScore,
    TaskScore,
    ChecklistResult,
    calculate_dimension_score,
    calculate_task_score,
    calculate_checklist_result,
    classify_items,
    format_dimension_report,
    generate_failure_report_v13,
)


class TestClassifyItems:
    """测试检查项分类功能。"""

    def test_classify_functionality_keywords(self):
        """测试功能完整性关键词分类。"""
        items = [
            CheckItem("实现用户登录功能", CheckStatus.PASSED, score=10),
            CheckItem("Add feature flag support", CheckStatus.PASSED, score=10),
            CheckItem("完成需求文档", CheckStatus.PASSED, score=10),
        ]

        result = classify_items(items)

        # "实现" 和 "feature" 应归类到功能完整性
        assert len(result[Dimension.FUNCTIONALITY]) >= 2

    def test_classify_quality_keywords(self):
        """测试代码质量关键词分类。"""
        items = [
            CheckItem("代码通过 lint 检查", CheckStatus.PASSED, score=10),
            CheckItem("重构登录模块", CheckStatus.PASSED, score=10),
            CheckItem("Code quality review passed", CheckStatus.PASSED, score=10),
        ]

        result = classify_items(items)

        # "lint", "重构", "quality" 应归类到代码质量
        assert len(result[Dimension.CODE_QUALITY]) >= 2

    def test_classify_test_keywords(self):
        """测试测试覆盖关键词分类。"""
        items = [
            CheckItem("添加单元测试", CheckStatus.PASSED, score=10),
            CheckItem("测试覆盖率达到 80%", CheckStatus.PASSED, score=10),
            CheckItem("Test coverage report generated", CheckStatus.PASSED, score=10),
        ]

        result = classify_items(items)

        # "测试", "test", "覆盖" 应归类到测试覆盖
        assert len(result[Dimension.TEST_COVERAGE]) >= 2

    def test_classify_documentation_keywords(self):
        """测试文档同步关键词分类。"""
        items = [
            CheckItem("更新 API 文档", CheckStatus.PASSED, score=10),
            CheckItem("添加代码注释", CheckStatus.PASSED, score=10),
            CheckItem("Documentation updated", CheckStatus.PASSED, score=10),
        ]

        result = classify_items(items)

        # "文档", "注释", "doc" 应归类到文档同步
        assert len(result[Dimension.DOCUMENTATION]) >= 2

    def test_classify_default_to_functionality(self):
        """测试无关键词项默认归类到功能完整性。"""
        items = [
            CheckItem("完成任务", CheckStatus.PASSED, score=10),
            CheckItem("Random task done", CheckStatus.PASSED, score=10),
        ]

        result = classify_items(items)

        # 无法分类的项应归类到功能完整性
        assert len(result[Dimension.FUNCTIONALITY]) >= 1

    def test_classify_updates_item_dimension(self):
        """测试分类后检查项的 dimension 属性被更新。"""
        items = [
            CheckItem("添加测试用例", CheckStatus.PASSED, score=10),
        ]

        classify_items(items)

        # 检查项的 dimension 属性应被设置
        assert items[0].dimension == Dimension.TEST_COVERAGE


class TestCalculateDimensionScore:
    """测试单维度得分计算。"""

    def test_calculate_all_passed(self):
        """测试全部通过的维度得分。"""
        items = [
            CheckItem("Task 1", CheckStatus.PASSED, score=10),
            CheckItem("Task 2", CheckStatus.PASSED, score=10),
        ]

        result = calculate_dimension_score(Dimension.FUNCTIONALITY, items, weight=30)

        assert result.earned == 20
        assert result.max_score == 20
        assert result.percentage == 100.0
        assert result.weight == 30

    def test_calculate_mixed_items(self):
        """测试混合状态的维度得分。"""
        items = [
            CheckItem("Task 1", CheckStatus.PASSED, score=10),
            CheckItem("Task 2", CheckStatus.FAILED, score=0),
        ]

        result = calculate_dimension_score(Dimension.CODE_QUALITY, items, weight=25)

        assert result.earned == 10
        assert result.max_score == 20
        assert result.percentage == 50.0

    def test_calculate_with_skipped_items(self):
        """测试包含跳过项的维度得分。"""
        items = [
            CheckItem("Task 1", CheckStatus.PASSED, score=10),
            CheckItem("Task 2", CheckStatus.SKIPPED, score=0),
        ]

        result = calculate_dimension_score(Dimension.TEST_COVERAGE, items, weight=25)

        # 跳过项不计入分数
        assert result.earned == 10
        assert result.max_score == 10
        assert result.percentage == 100.0

    def test_calculate_empty_items(self):
        """测试空检查项列表的维度得分。"""
        result = calculate_dimension_score(Dimension.DOCUMENTATION, [], weight=20)

        # 空列表视为通过
        assert result.earned == 0
        assert result.max_score == 0
        assert result.percentage == 100.0


class TestCalculateTaskScore:
    """测试任务四维度加权得分计算。"""

    def test_calculate_all_dimensions(self):
        """测试包含所有维度的任务得分。"""
        items = [
            CheckItem("实现功能", CheckStatus.PASSED, score=10),
            CheckItem("代码质量检查", CheckStatus.PASSED, score=10),
            CheckItem("添加测试", CheckStatus.PASSED, score=10),
            CheckItem("更新文档", CheckStatus.PASSED, score=10),
        ]

        result = calculate_task_score("01-SETUP", items, threshold=80)

        assert result.task_id == "01-SETUP"
        assert result.passed is True
        assert result.total_score >= 80
        assert len(result.failed_dimensions) == 0

    def test_calculate_partial_failure(self):
        """测试部分维度未通过的任务得分。"""
        items = [
            CheckItem("实现功能", CheckStatus.PASSED, score=10),
            CheckItem("代码 lint 通过", CheckStatus.FAILED, score=0),
            CheckItem("添加测试", CheckStatus.FAILED, score=0),
            CheckItem("更新文档", CheckStatus.PASSED, score=10),
        ]

        result = calculate_task_score("02-MODEL", items, threshold=80)

        # 应有未通过的维度
        assert result.passed is False
        assert len(result.failed_dimensions) > 0

    def test_calculate_with_custom_config(self):
        """测试自定义配置的任务得分。"""
        items = [
            CheckItem("实现功能", CheckStatus.PASSED, score=10),
            CheckItem("通过测试", CheckStatus.PASSED, score=10),
        ]

        config = ScoringConfig(
            pass_threshold=80,
            dimensions={
                "functionality": DimensionConfig(weight=50),
                "test_coverage": DimensionConfig(weight=50),
            }
        )

        result = calculate_task_score("03-API", items, scoring_config=config, threshold=80)

        assert result.passed is True

    def test_calculate_empty_task(self):
        """测试空任务的得分。"""
        result = calculate_task_score("EMPTY-TASK", [], threshold=80)

        assert result.total_score == 0
        assert result.passed is False


class TestCalculateChecklistResult:
    """测试完整 checklist 打分结果计算。"""

    def test_calculate_single_task(self):
        """测试单任务的 checklist 结果。"""
        task_checklists = {
            "01-SETUP": [
                CheckItem("实现功能", CheckStatus.PASSED, score=10),
                CheckItem("添加测试", CheckStatus.PASSED, score=10),
            ]
        }

        result = calculate_checklist_result(task_checklists, threshold=80)

        assert len(result.task_scores) == 1
        assert result.overall_passed is True
        assert result.overall_score >= 80

    def test_calculate_multiple_tasks(self):
        """测试多任务的 checklist 结果。"""
        task_checklists = {
            "01-SETUP": [
                CheckItem("实现功能", CheckStatus.PASSED, score=10),
            ],
            "02-MODEL": [
                CheckItem("创建模型", CheckStatus.PASSED, score=10),
                CheckItem("添加测试", CheckStatus.FAILED, score=0),
            ],
        }

        result = calculate_checklist_result(task_checklists, threshold=80)

        assert len(result.task_scores) == 2

    def test_calculate_overall_score(self):
        """测试整体得分计算。"""
        task_checklists = {
            "01-SETUP": [
                CheckItem("任务 1", CheckStatus.PASSED, score=10),
                CheckItem("任务 2", CheckStatus.PASSED, score=10),
            ],
            "02-MODEL": [
                CheckItem("任务 1", CheckStatus.PASSED, score=10),
                CheckItem("任务 2", CheckStatus.FAILED, score=0),
            ],
        }

        result = calculate_checklist_result(task_checklists, threshold=80)

        # 整体得分应是所有任务得分的平均值
        assert 0 <= result.overall_score <= 100

    def test_calculate_failed_tasks(self):
        """测试未通过任务列表。"""
        task_checklists = {
            "01-SETUP": [
                CheckItem("完成", CheckStatus.PASSED, score=10),
            ],
            "02-MODEL": [
                CheckItem("未完成", CheckStatus.FAILED, score=0),
            ],
        }

        result = calculate_checklist_result(task_checklists, threshold=80)

        # 应有未通过的任务
        assert len(result.failed_tasks) >= 1

    def test_calculate_dimension_summary(self):
        """测试维度汇总计算。"""
        task_checklists = {
            "01-SETUP": [
                CheckItem("实现功能", CheckStatus.PASSED, score=10),
                CheckItem("添加测试", CheckStatus.PASSED, score=10),
            ],
        }

        result = calculate_checklist_result(task_checklists, threshold=80)

        # 应有维度汇总
        assert Dimension.FUNCTIONALITY in result.dimension_summary or \
               Dimension.TEST_COVERAGE in result.dimension_summary

    def test_calculate_recommendations(self):
        """测试改进建议生成。"""
        task_checklists = {
            "01-SETUP": [
                CheckItem("添加测试", CheckStatus.FAILED, score=0),
                CheckItem("更新文档", CheckStatus.FAILED, score=0),
            ],
        }

        result = calculate_checklist_result(task_checklists, threshold=80)

        # 应有改进建议
        assert len(result.recommendations) > 0


class TestFormatDimensionReport:
    """测试四维度报告格式化。"""

    def test_format_passed_report(self):
        """测试通过的报告格式。"""
        task_checklists = {
            "01-SETUP": [
                CheckItem("实现功能", CheckStatus.PASSED, score=10),
                CheckItem("添加测试", CheckStatus.PASSED, score=10),
            ],
        }
        result = calculate_checklist_result(task_checklists, threshold=80)

        report = format_dimension_report(result)

        assert "# Checklist 打分报告" in report
        assert "✅" in report or "PASS" in report

    def test_format_failed_report(self):
        """测试未通过的报告格式。"""
        task_checklists = {
            "01-SETUP": [
                CheckItem("任务", CheckStatus.FAILED, score=0),
            ],
        }
        result = calculate_checklist_result(task_checklists, threshold=80)

        report = format_dimension_report(result)

        assert "❌" in report or "FAIL" in report

    def test_format_includes_table(self):
        """测试报告包含表格。"""
        task_checklists = {
            "01-SETUP": [
                CheckItem("任务", CheckStatus.PASSED, score=10),
            ],
        }
        result = calculate_checklist_result(task_checklists, threshold=80)

        report = format_dimension_report(result)

        assert "|" in report  # Markdown 表格分隔符


class TestGenerateFailureReportV13:
    """测试增强版失败报告生成。"""

    def test_generate_basic_report(self):
        """测试基本失败报告。"""
        task_checklists = {
            "01-SETUP": [
                CheckItem("任务 1", CheckStatus.FAILED, score=0),
                CheckItem("任务 2", CheckStatus.FAILED, score=0),
            ],
        }
        result = calculate_checklist_result(task_checklists, threshold=80)

        report = generate_failure_report_v13(result)

        assert "# Checklist 验证失败" in report
        assert "80%" in report
        assert "下一步" in report

    def test_generate_report_with_dimensions(self):
        """测试包含维度信息的失败报告。"""
        task_checklists = {
            "01-SETUP": [
                CheckItem("实现功能", CheckStatus.PASSED, score=10),
                CheckItem("添加测试", CheckStatus.FAILED, score=0),
            ],
        }
        result = calculate_checklist_result(task_checklists, threshold=80)

        report = generate_failure_report_v13(result)

        # 应包含任务和维度信息
        assert "01-SETUP" in report

    def test_generate_report_with_recommendations(self):
        """测试包含改进建议的失败报告。"""
        task_checklists = {
            "01-SETUP": [
                CheckItem("添加测试", CheckStatus.FAILED, score=0),
            ],
        }
        result = calculate_checklist_result(task_checklists, threshold=80)

        report = generate_failure_report_v13(result)

        # 应包含改进建议
        assert "改进建议" in report or "建议" in report


class TestBackwardCompatibility:
    """测试向后兼容性。"""

    def test_old_calculate_score_still_works(self):
        """测试旧版 calculate_score 函数仍可用。"""
        from cc_spec.core.scoring import calculate_score

        items = [
            CheckItem("Task 1", CheckStatus.PASSED, score=10),
            CheckItem("Task 2", CheckStatus.FAILED, score=0),
        ]

        result = calculate_score(items, threshold=80)

        assert result.total_score == 10
        assert result.max_score == 20
        assert result.percentage == 50.0

    def test_old_format_result_still_works(self):
        """测试旧版 format_result 函数仍可用。"""
        from cc_spec.core.scoring import format_result, calculate_score

        items = [CheckItem("Task", CheckStatus.PASSED, score=10)]
        result = calculate_score(items, threshold=80)

        formatted = format_result(result)

        assert "# Checklist" in formatted

    def test_old_generate_failure_report_still_works(self):
        """测试旧版 generate_failure_report 函数仍可用。"""
        from cc_spec.core.scoring import generate_failure_report, calculate_score

        items = [CheckItem("Task", CheckStatus.FAILED, score=0)]
        result = calculate_score(items, threshold=80)

        report = generate_failure_report(result)

        assert "# Checklist" in report
