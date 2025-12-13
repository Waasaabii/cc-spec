"""v1.3 quick-delta 增强测试。

测试 git diff 解析、文件变更统计和输出格式增强。
"""

import pytest
from unittest.mock import patch, MagicMock
from subprocess import CompletedProcess

from cc_spec.core.delta import DeltaOperation
from cc_spec.commands.quick_delta import (
    FileChange,
    DiffStats,
    _parse_git_diff,
    _parse_name_status,
    _get_diff_stats,
    _generate_slug,
)


class TestFileChange:
    """测试 FileChange 数据类。"""

    def test_create_file_change(self):
        """测试创建 FileChange 实例。"""
        change = FileChange(
            path="src/main.py",
            operation=DeltaOperation.MODIFIED,
        )

        assert change.path == "src/main.py"
        assert change.operation == DeltaOperation.MODIFIED
        assert change.old_path is None
        assert change.additions == 0
        assert change.deletions == 0

    def test_create_renamed_file_change(self):
        """测试创建重命名的 FileChange。"""
        change = FileChange(
            path="src/new_name.py",
            operation=DeltaOperation.RENAMED,
            old_path="src/old_name.py",
        )

        assert change.path == "src/new_name.py"
        assert change.old_path == "src/old_name.py"
        assert change.operation == DeltaOperation.RENAMED

    def test_file_change_with_stats(self):
        """测试带统计信息的 FileChange。"""
        change = FileChange(
            path="src/main.py",
            operation=DeltaOperation.MODIFIED,
            additions=10,
            deletions=5,
        )

        assert change.additions == 10
        assert change.deletions == 5


class TestDiffStats:
    """测试 DiffStats 数据类。"""

    def test_create_diff_stats(self):
        """测试创建 DiffStats 实例。"""
        changes = [
            FileChange("a.py", DeltaOperation.ADDED),
            FileChange("b.py", DeltaOperation.MODIFIED),
        ]
        stats = DiffStats(
            changes=changes,
            total_additions=20,
            total_deletions=5,
        )

        assert len(stats.changes) == 2
        assert stats.total_additions == 20
        assert stats.total_deletions == 5

    def test_count_by_operation_added(self):
        """测试按操作类型统计 - ADDED。"""
        changes = [
            FileChange("a.py", DeltaOperation.ADDED),
            FileChange("b.py", DeltaOperation.ADDED),
            FileChange("c.py", DeltaOperation.MODIFIED),
        ]
        stats = DiffStats(changes=changes)

        assert stats.count_by_operation(DeltaOperation.ADDED) == 2

    def test_count_by_operation_modified(self):
        """测试按操作类型统计 - MODIFIED。"""
        changes = [
            FileChange("a.py", DeltaOperation.ADDED),
            FileChange("b.py", DeltaOperation.MODIFIED),
            FileChange("c.py", DeltaOperation.MODIFIED),
        ]
        stats = DiffStats(changes=changes)

        assert stats.count_by_operation(DeltaOperation.MODIFIED) == 2

    def test_count_by_operation_removed(self):
        """测试按操作类型统计 - REMOVED。"""
        changes = [
            FileChange("a.py", DeltaOperation.REMOVED),
        ]
        stats = DiffStats(changes=changes)

        assert stats.count_by_operation(DeltaOperation.REMOVED) == 1

    def test_count_by_operation_renamed(self):
        """测试按操作类型统计 - RENAMED。"""
        changes = [
            FileChange("a.py", DeltaOperation.RENAMED, old_path="old.py"),
        ]
        stats = DiffStats(changes=changes)

        assert stats.count_by_operation(DeltaOperation.RENAMED) == 1

    def test_count_by_operation_none(self):
        """测试按操作类型统计 - 无匹配。"""
        changes = [
            FileChange("a.py", DeltaOperation.ADDED),
        ]
        stats = DiffStats(changes=changes)

        assert stats.count_by_operation(DeltaOperation.REMOVED) == 0


class TestParseNameStatus:
    """测试 _parse_name_status 函数。"""

    def test_parse_added_file(self):
        """测试解析新增文件。"""
        output = "A\tsrc/new_file.py\n"
        result = _parse_name_status(output)

        assert len(result) == 1
        assert result[0].path == "src/new_file.py"
        assert result[0].operation == DeltaOperation.ADDED

    def test_parse_modified_file(self):
        """测试解析修改的文件。"""
        output = "M\tsrc/existing.py\n"
        result = _parse_name_status(output)

        assert len(result) == 1
        assert result[0].path == "src/existing.py"
        assert result[0].operation == DeltaOperation.MODIFIED

    def test_parse_deleted_file(self):
        """测试解析删除的文件。"""
        output = "D\tsrc/deleted.py\n"
        result = _parse_name_status(output)

        assert len(result) == 1
        assert result[0].path == "src/deleted.py"
        assert result[0].operation == DeltaOperation.REMOVED

    def test_parse_renamed_file(self):
        """测试解析重命名的文件。"""
        output = "R100\told_name.py\tnew_name.py\n"
        result = _parse_name_status(output)

        assert len(result) == 1
        assert result[0].path == "new_name.py"
        assert result[0].old_path == "old_name.py"
        assert result[0].operation == DeltaOperation.RENAMED

    def test_parse_multiple_files(self):
        """测试解析多个文件。"""
        output = "A\tnew.py\nM\texisting.py\nD\tdeleted.py\n"
        result = _parse_name_status(output)

        assert len(result) == 3
        assert result[0].operation == DeltaOperation.ADDED
        assert result[1].operation == DeltaOperation.MODIFIED
        assert result[2].operation == DeltaOperation.REMOVED

    def test_parse_empty_output(self):
        """测试解析空输出。"""
        result = _parse_name_status("")

        assert len(result) == 0

    def test_parse_unknown_status(self):
        """测试解析未知状态。"""
        output = "U\tunmerged.py\n"  # U = 未合并
        result = _parse_name_status(output)

        assert len(result) == 1
        # 未知状态默认为 MODIFIED
        assert result[0].operation == DeltaOperation.MODIFIED

    def test_parse_with_spaces_in_path(self):
        """测试路径包含空格（tab 分隔）。"""
        output = "M\tsrc/path with spaces/file.py\n"
        result = _parse_name_status(output)

        assert len(result) == 1
        assert result[0].path == "src/path with spaces/file.py"


class TestGetDiffStats:
    """测试 _get_diff_stats 函数。"""

    @patch("cc_spec.commands.quick_delta.subprocess.run")
    def test_get_stats_success(self, mock_run):
        """测试成功获取统计信息。"""
        mock_run.return_value = CompletedProcess(
            args=["git", "diff"],
            returncode=0,
            stdout="10\t5\tsrc/main.py\n20\t3\tsrc/utils.py\n",
        )

        result = _get_diff_stats("--staged")

        assert "src/main.py" in result
        assert result["src/main.py"] == (10, 5)
        assert "src/utils.py" in result
        assert result["src/utils.py"] == (20, 3)

    @patch("cc_spec.commands.quick_delta.subprocess.run")
    def test_get_stats_binary_file(self, mock_run):
        """测试二进制文件统计。"""
        mock_run.return_value = CompletedProcess(
            args=["git", "diff"],
            returncode=0,
            stdout="-\t-\timage.png\n10\t5\tsrc/main.py\n",
        )

        result = _get_diff_stats("--staged")

        assert "image.png" in result
        assert result["image.png"] == (0, 0)  # 二进制文件
        assert result["src/main.py"] == (10, 5)

    @patch("cc_spec.commands.quick_delta.subprocess.run")
    def test_get_stats_empty(self, mock_run):
        """测试空输出。"""
        mock_run.return_value = CompletedProcess(
            args=["git", "diff"],
            returncode=0,
            stdout="",
        )

        result = _get_diff_stats("--staged")

        assert len(result) == 0

    @patch("cc_spec.commands.quick_delta.subprocess.run")
    def test_get_stats_error(self, mock_run):
        """测试命令失败。"""
        mock_run.return_value = CompletedProcess(
            args=["git", "diff"],
            returncode=1,
            stdout="",
        )

        result = _get_diff_stats("--staged")

        assert len(result) == 0


class TestParseGitDiff:
    """测试 _parse_git_diff 函数。"""

    @patch("cc_spec.commands.quick_delta.subprocess.run")
    def test_parse_staged_changes(self, mock_run):
        """测试解析 staged 变更。"""
        # 第一次调用 (name-status) 返回变更
        # 第二次调用 (numstat) 返回统计
        mock_run.side_effect = [
            CompletedProcess(
                args=["git", "diff", "--staged", "--name-status"],
                returncode=0,
                stdout="A\tnew.py\nM\texisting.py\n",
            ),
            CompletedProcess(
                args=["git", "diff", "--staged", "--numstat"],
                returncode=0,
                stdout="10\t0\tnew.py\n5\t3\texisting.py\n",
            ),
        ]

        result = _parse_git_diff()

        assert result is not None
        assert len(result.changes) == 2
        assert result.total_additions == 15
        assert result.total_deletions == 3

    @patch("cc_spec.commands.quick_delta.subprocess.run")
    def test_parse_fallback_to_head(self, mock_run):
        """测试降级到 HEAD~1。"""
        mock_run.side_effect = [
            # staged 为空
            CompletedProcess(
                args=["git", "diff", "--staged", "--name-status"],
                returncode=0,
                stdout="",
            ),
            # HEAD~1 有变更
            CompletedProcess(
                args=["git", "diff", "HEAD~1", "--name-status"],
                returncode=0,
                stdout="M\tmodified.py\n",
            ),
            # numstat
            CompletedProcess(
                args=["git", "diff", "HEAD~1", "--numstat"],
                returncode=0,
                stdout="5\t2\tmodified.py\n",
            ),
        ]

        result = _parse_git_diff()

        assert result is not None
        assert len(result.changes) == 1
        assert result.changes[0].operation == DeltaOperation.MODIFIED

    @patch("cc_spec.commands.quick_delta.subprocess.run")
    def test_parse_no_changes(self, mock_run):
        """测试无变更时返回 None。"""
        mock_run.side_effect = [
            # staged 为空
            CompletedProcess(
                args=["git", "diff", "--staged", "--name-status"],
                returncode=0,
                stdout="",
            ),
            # HEAD~1 也为空
            CompletedProcess(
                args=["git", "diff", "HEAD~1", "--name-status"],
                returncode=0,
                stdout="",
            ),
        ]

        result = _parse_git_diff()

        assert result is None

    @patch("cc_spec.commands.quick_delta.subprocess.run")
    def test_parse_git_error(self, mock_run):
        """测试 git 命令失败。"""
        mock_run.side_effect = [
            # staged 失败
            CompletedProcess(
                args=["git", "diff", "--staged", "--name-status"],
                returncode=1,
                stdout="",
            ),
            # HEAD~1 也失败
            CompletedProcess(
                args=["git", "diff", "HEAD~1", "--name-status"],
                returncode=1,
                stdout="",
            ),
        ]

        result = _parse_git_diff()

        assert result is None


class TestGenerateSlug:
    """测试 _generate_slug 函数。"""

    def test_simple_message(self):
        """测试简单消息。"""
        slug = _generate_slug("Fix login bug")

        assert slug == "fix-login-bug"

    def test_chinese_message(self):
        """测试中文消息。"""
        slug = _generate_slug("修复登录问题")

        assert slug == "修复登录问题"

    def test_special_characters(self):
        """测试特殊字符。"""
        slug = _generate_slug("Fix bug! @version 1.0")

        assert "@" not in slug
        assert "!" not in slug

    def test_max_length(self):
        """测试最大长度限制。"""
        long_message = "This is a very long message that should be truncated"
        slug = _generate_slug(long_message, max_length=20)

        assert len(slug) <= 20

    def test_empty_message(self):
        """测试空消息。"""
        slug = _generate_slug("")

        assert slug == "change"  # 默认值

    def test_only_special_chars(self):
        """测试仅包含特殊字符。"""
        slug = _generate_slug("!@#$%^&*()")

        assert slug == "change"  # 默认值

    def test_multiple_spaces(self):
        """测试多个空格。"""
        slug = _generate_slug("Fix    multiple    spaces")

        assert "--" not in slug  # 不应有连续的连字符

    def test_leading_trailing_spaces(self):
        """测试首尾空格。"""
        slug = _generate_slug("  Fix bug  ")

        assert not slug.startswith("-")
        assert not slug.endswith("-")


class TestIntegration:
    """集成测试。"""

    @patch("cc_spec.commands.quick_delta.subprocess.run")
    def test_full_diff_parse_workflow(self, mock_run):
        """测试完整的 diff 解析流程。"""
        mock_run.side_effect = [
            # name-status
            CompletedProcess(
                args=["git", "diff", "--staged", "--name-status"],
                returncode=0,
                stdout="A\tsrc/new.py\nM\tsrc/existing.py\nD\tsrc/deleted.py\nR100\tsrc/old.py\tsrc/renamed.py\n",
            ),
            # numstat
            CompletedProcess(
                args=["git", "diff", "--staged", "--numstat"],
                returncode=0,
                stdout="50\t0\tsrc/new.py\n10\t5\tsrc/existing.py\n0\t30\tsrc/deleted.py\n20\t20\tsrc/renamed.py\n",
            ),
        ]

        result = _parse_git_diff()

        assert result is not None
        assert len(result.changes) == 4

        # 验证各类型统计
        assert result.count_by_operation(DeltaOperation.ADDED) == 1
        assert result.count_by_operation(DeltaOperation.MODIFIED) == 1
        assert result.count_by_operation(DeltaOperation.REMOVED) == 1
        assert result.count_by_operation(DeltaOperation.RENAMED) == 1

        # 验证总计
        assert result.total_additions == 80
        assert result.total_deletions == 55
