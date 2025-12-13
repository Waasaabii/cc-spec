"""Tests for scoring mechanism module."""

import pytest

from cc_spec.core.scoring import (
    CheckItem,
    CheckStatus,
    ScoreResult,
    calculate_score,
    extract_checklists_from_tasks_md,
    format_result,
    generate_failure_report,
    parse_checklist,
)


class TestParseChecklist:
    """Test cases for parse_checklist function."""

    def test_parse_empty_content(self):
        """Test parsing empty content returns empty list."""
        result = parse_checklist("")
        assert result == []

    def test_parse_no_checklist_items(self):
        """Test parsing content without checklist items."""
        content = """
        # Some heading
        This is just regular text.
        No checklist items here.
        """
        result = parse_checklist(content)
        assert result == []

    def test_parse_passed_items(self):
        """Test parsing checked items (PASSED)."""
        content = """
        - [x] First task
        - [X] Second task (uppercase)
        """
        result = parse_checklist(content)

        assert len(result) == 2
        assert result[0].description == "First task"
        assert result[0].status == CheckStatus.PASSED
        assert result[0].score == 10
        assert result[1].description == "Second task (uppercase)"
        assert result[1].status == CheckStatus.PASSED

    def test_parse_failed_items(self):
        """Test parsing unchecked items (FAILED)."""
        content = """
        - [ ] Incomplete task
        - [ ] Another incomplete task
        """
        result = parse_checklist(content)

        assert len(result) == 2
        assert result[0].description == "Incomplete task"
        assert result[0].status == CheckStatus.FAILED
        assert result[0].score == 0
        assert result[1].description == "Another incomplete task"
        assert result[1].status == CheckStatus.FAILED

    def test_parse_skipped_items(self):
        """Test parsing skipped items."""
        content = """
        - [-] Skipped task
        - [-] Another skipped task
        """
        result = parse_checklist(content)

        assert len(result) == 2
        assert result[0].description == "Skipped task"
        assert result[0].status == CheckStatus.SKIPPED
        assert result[0].score == 0
        assert result[1].description == "Another skipped task"
        assert result[1].status == CheckStatus.SKIPPED

    def test_parse_mixed_items(self):
        """Test parsing mixed status items."""
        content = """
        - [x] Completed task
        - [ ] Incomplete task
        - [-] Skipped task
        - [x] Another completed task
        """
        result = parse_checklist(content)

        assert len(result) == 4
        assert result[0].status == CheckStatus.PASSED
        assert result[1].status == CheckStatus.FAILED
        assert result[2].status == CheckStatus.SKIPPED
        assert result[3].status == CheckStatus.PASSED

    def test_parse_with_asterisk_bullet(self):
        """Test parsing with asterisk instead of dash."""
        content = """
        * [x] Completed task
        * [ ] Incomplete task
        """
        result = parse_checklist(content)

        assert len(result) == 2
        assert result[0].status == CheckStatus.PASSED
        assert result[1].status == CheckStatus.FAILED

    def test_parse_ignores_non_checklist_lines(self):
        """Test that non-checklist lines are ignored."""
        content = """
        # Heading
        - [x] Valid item
        This is text
        - Regular bullet point
        - [x] Another valid item
        [x] No bullet prefix
        """
        result = parse_checklist(content)

        assert len(result) == 2
        assert result[0].description == "Valid item"
        assert result[1].description == "Another valid item"


class TestCalculateScore:
    """Test cases for calculate_score function."""

    def test_calculate_all_passed(self):
        """Test scoring when all items are passed."""
        items = [
            CheckItem("Task 1", CheckStatus.PASSED, score=10),
            CheckItem("Task 2", CheckStatus.PASSED, score=10),
            CheckItem("Task 3", CheckStatus.PASSED, score=10),
        ]

        result = calculate_score(items, threshold=80)

        assert result.total_score == 30
        assert result.max_score == 30
        assert result.percentage == 100.0
        assert result.passed is True
        assert len(result.failed_items) == 0

    def test_calculate_all_failed(self):
        """Test scoring when all items failed."""
        items = [
            CheckItem("Task 1", CheckStatus.FAILED, score=0),
            CheckItem("Task 2", CheckStatus.FAILED, score=0),
            CheckItem("Task 3", CheckStatus.FAILED, score=0),
        ]

        result = calculate_score(items, threshold=80)

        assert result.total_score == 0
        assert result.max_score == 30
        assert result.percentage == 0.0
        assert result.passed is False
        assert len(result.failed_items) == 3

    def test_calculate_mixed_scores(self):
        """Test scoring with mixed pass/fail items."""
        items = [
            CheckItem("Task 1", CheckStatus.PASSED, score=10),
            CheckItem("Task 2", CheckStatus.FAILED, score=0),
            CheckItem("Task 3", CheckStatus.PASSED, score=10),
            CheckItem("Task 4", CheckStatus.FAILED, score=0),
        ]

        result = calculate_score(items, threshold=80)

        assert result.total_score == 20
        assert result.max_score == 40
        assert result.percentage == 50.0
        assert result.passed is False
        assert len(result.failed_items) == 2

    def test_calculate_with_skipped_items(self):
        """Test that skipped items are not counted in score."""
        items = [
            CheckItem("Task 1", CheckStatus.PASSED, score=10),
            CheckItem("Task 2", CheckStatus.SKIPPED, score=0),
            CheckItem("Task 3", CheckStatus.PASSED, score=10),
        ]

        result = calculate_score(items, threshold=80)

        # Skipped item should not affect max_score
        assert result.total_score == 20
        assert result.max_score == 20  # Not 30!
        assert result.percentage == 100.0
        assert result.passed is True

    def test_calculate_exactly_at_threshold(self):
        """Test scoring exactly at threshold."""
        items = [
            CheckItem("Task 1", CheckStatus.PASSED, score=10),
            CheckItem("Task 2", CheckStatus.PASSED, score=10),
            CheckItem("Task 3", CheckStatus.PASSED, score=10),
            CheckItem("Task 4", CheckStatus.PASSED, score=10),
            CheckItem("Task 5", CheckStatus.FAILED, score=0),
        ]

        result = calculate_score(items, threshold=80)

        assert result.total_score == 40
        assert result.max_score == 50
        assert result.percentage == 80.0
        assert result.passed is True  # Exactly at threshold

    def test_calculate_custom_threshold(self):
        """Test scoring with custom threshold."""
        items = [
            CheckItem("Task 1", CheckStatus.PASSED, score=10),
            CheckItem("Task 2", CheckStatus.FAILED, score=0),
        ]

        result = calculate_score(items, threshold=40)

        assert result.percentage == 50.0
        assert result.passed is True  # 50% >= 40%
        assert result.threshold == 40

    def test_calculate_empty_items(self):
        """Test scoring with no items."""
        items = []
        result = calculate_score(items, threshold=80)

        assert result.total_score == 0
        assert result.max_score == 0
        assert result.percentage == 0.0
        assert result.passed is False

    def test_calculate_only_skipped_items(self):
        """Test scoring with only skipped items."""
        items = [
            CheckItem("Task 1", CheckStatus.SKIPPED, score=0),
            CheckItem("Task 2", CheckStatus.SKIPPED, score=0),
        ]

        result = calculate_score(items, threshold=80)

        assert result.total_score == 0
        assert result.max_score == 0
        assert result.percentage == 0.0  # Division by zero handled


class TestFormatResult:
    """Test cases for format_result function."""

    def test_format_passed_result(self):
        """Test formatting a passed result."""
        items = [
            CheckItem("Task 1", CheckStatus.PASSED, score=10),
            CheckItem("Task 2", CheckStatus.PASSED, score=10),
        ]
        result = calculate_score(items, threshold=80)

        formatted = format_result(result)

        assert "# Checklist Score Result" in formatted
        assert "20/20" in formatted
        assert "100.0%" in formatted
        assert "✓ PASSED" in formatted
        assert "[x] Task 1" in formatted
        assert "[x] Task 2" in formatted

    def test_format_failed_result(self):
        """Test formatting a failed result."""
        items = [
            CheckItem("Task 1", CheckStatus.PASSED, score=10),
            CheckItem("Task 2", CheckStatus.FAILED, score=0),
        ]
        result = calculate_score(items, threshold=80)

        formatted = format_result(result)

        assert "✗ FAILED" in formatted
        assert "50.0%" in formatted
        assert "## Failed Items" in formatted
        assert "Task 2" in formatted

    def test_format_with_skipped_items(self):
        """Test formatting with skipped items."""
        items = [
            CheckItem("Task 1", CheckStatus.PASSED, score=10),
            CheckItem("Task 2", CheckStatus.SKIPPED, score=0),
        ]
        result = calculate_score(items, threshold=80)

        formatted = format_result(result)

        assert "[-] Task 2" in formatted

    def test_format_with_notes(self):
        """Test formatting items with notes."""
        items = [
            CheckItem("Task 1", CheckStatus.FAILED, score=0, notes="Missing configuration"),
        ]
        result = calculate_score(items, threshold=80)

        formatted = format_result(result)

        assert "Missing configuration" in formatted


class TestGenerateFailureReport:
    """Test cases for generate_failure_report function."""

    def test_generate_report_with_failures(self):
        """Test generating failure report."""
        items = [
            CheckItem("Task 1", CheckStatus.PASSED, score=10),
            CheckItem("Task 2", CheckStatus.FAILED, score=0),
            CheckItem("Task 3", CheckStatus.FAILED, score=0),
        ]
        result = calculate_score(items, threshold=80)

        report = generate_failure_report(result)

        assert "# Checklist Validation Failed" in report
        assert "80%" in report
        assert "## Failed Items" in report
        assert "Task 2" in report
        assert "Task 3" in report
        assert "## Next Steps" in report
        assert "cc-spec clarify" in report

    def test_generate_report_includes_notes(self):
        """Test that failure report includes item notes."""
        items = [
            CheckItem("Task 1", CheckStatus.FAILED, score=0, notes="Needs investigation"),
        ]
        result = calculate_score(items, threshold=80)

        report = generate_failure_report(result)

        assert "Needs investigation" in report

    def test_generate_report_numbering(self):
        """Test that failed items are numbered."""
        items = [
            CheckItem("First fail", CheckStatus.FAILED, score=0),
            CheckItem("Second fail", CheckStatus.FAILED, score=0),
            CheckItem("Third fail", CheckStatus.FAILED, score=0),
        ]
        result = calculate_score(items, threshold=80)

        report = generate_failure_report(result)

        assert "1. **First fail**" in report
        assert "2. **Second fail**" in report
        assert "3. **Third fail**" in report


class TestExtractChecklistsFromTasksMd:
    """Test cases for extract_checklists_from_tasks_md function."""

    def test_extract_single_task(self):
        """Test extracting checklist from a single task."""
        content = """
        ### 01-SETUP - Project Setup

        **Checklist**:
        - [x] Create project structure
        - [ ] Configure dependencies
        """

        result = extract_checklists_from_tasks_md(content)

        assert "01-SETUP" in result
        assert len(result["01-SETUP"]) == 2
        assert result["01-SETUP"][0].description == "Create project structure"
        assert result["01-SETUP"][0].status == CheckStatus.PASSED
        assert result["01-SETUP"][1].description == "Configure dependencies"
        assert result["01-SETUP"][1].status == CheckStatus.FAILED

    def test_extract_multiple_tasks(self):
        """Test extracting checklists from multiple tasks."""
        content = """
        ### 01-SETUP - Project Setup

        **Checklist**:
        - [x] Create structure
        - [x] Configure deps

        ### 02-BUILD - Build System

        **Checklist**:
        - [ ] Setup build
        - [-] Optional feature
        """

        result = extract_checklists_from_tasks_md(content)

        assert len(result) == 2
        assert "01-SETUP" in result
        assert "02-BUILD" in result
        assert len(result["01-SETUP"]) == 2
        assert len(result["02-BUILD"]) == 2

    def test_extract_no_checklists(self):
        """Test extracting when no checklists exist."""
        content = """
        ### 01-SETUP - Project Setup

        Just some description without a checklist.
        """

        result = extract_checklists_from_tasks_md(content)

        assert len(result) == 0

    def test_extract_task_without_checklist_header(self):
        """Test that tasks without '**Checklist**' header are ignored."""
        content = """
        ### 01-SETUP - Project Setup

        - [x] This is just a bullet point
        - [ ] Not under a Checklist header
        """

        result = extract_checklists_from_tasks_md(content)

        assert len(result) == 0

    def test_extract_with_extra_content(self):
        """Test extracting with extra content between tasks."""
        content = """
        # Tasks Document

        Some introduction text.

        ### 01-SETUP - Project Setup

        This is a description of the task.

        **Checklist**:
        - [x] Item 1
        - [x] Item 2

        Additional notes here.

        ### 02-BUILD - Build System

        Another description.

        **Checklist**:
        - [ ] Item 3
        """

        result = extract_checklists_from_tasks_md(content)

        assert len(result) == 2
        assert len(result["01-SETUP"]) == 2
        assert len(result["02-BUILD"]) == 1

    def test_extract_task_id_formats(self):
        """Test various task ID formats."""
        content = """
        ### 01-SETUP - Setup
        **Checklist**:
        - [x] Task 1

        ### 02A-BUILD - Build
        **Checklist**:
        - [x] Task 2

        ### TEST-001 - Testing
        **Checklist**:
        - [x] Task 3
        """

        result = extract_checklists_from_tasks_md(content)

        assert "01-SETUP" in result
        assert "02A-BUILD" in result
        assert "TEST-001" in result

    def test_extract_with_checklist_variations(self):
        """Test different variations of Checklist header."""
        content = """
        ### 01-SETUP - Setup
        **Checklist**:
        - [x] Task 1

        ### 02-BUILD - Build
        **Checklist**
        - [x] Task 2
        """

        result = extract_checklists_from_tasks_md(content)

        # Both variations should work
        assert "01-SETUP" in result
        assert "02-BUILD" in result

    def test_extract_empty_content(self):
        """Test extracting from empty content."""
        result = extract_checklists_from_tasks_md("")
        assert len(result) == 0

    def test_extract_preserves_item_order(self):
        """Test that item order is preserved."""
        content = """
        ### 01-SETUP - Setup
        **Checklist**:
        - [x] First
        - [ ] Second
        - [-] Third
        - [x] Fourth
        """

        result = extract_checklists_from_tasks_md(content)

        items = result["01-SETUP"]
        assert items[0].description == "First"
        assert items[1].description == "Second"
        assert items[2].description == "Third"
        assert items[3].description == "Fourth"


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_full_workflow_passing(self):
        """Test complete workflow with passing score."""
        # Parse checklist
        content = """
        - [x] Task 1
        - [x] Task 2
        - [x] Task 3
        - [ ] Task 4
        """
        items = parse_checklist(content)

        # Calculate score
        result = calculate_score(items, threshold=70)

        # Verify results
        assert result.percentage == 75.0
        assert result.passed is True

        # Format result
        formatted = format_result(result)
        assert "✓ PASSED" in formatted

    def test_full_workflow_failing(self):
        """Test complete workflow with failing score."""
        # Parse checklist
        content = """
        - [x] Task 1
        - [ ] Task 2
        - [ ] Task 3
        - [ ] Task 4
        """
        items = parse_checklist(content)

        # Calculate score
        result = calculate_score(items, threshold=80)

        # Verify results
        assert result.percentage == 25.0
        assert result.passed is False

        # Generate failure report
        report = generate_failure_report(result)
        assert "# Checklist Validation Failed" in report
        assert "Task 2" in report

    def test_tasks_md_to_score(self):
        """Test extracting from tasks.md and scoring."""
        tasks_content = """
        ### 01-SETUP - Setup

        **Checklist**:
        - [x] Create files
        - [x] Configure settings
        - [ ] Write docs
        """

        # Extract checklists
        checklists = extract_checklists_from_tasks_md(tasks_content)
        assert "01-SETUP" in checklists

        # Calculate score
        result = calculate_score(checklists["01-SETUP"], threshold=80)

        # Should not pass (66.7% < 80%)
        assert result.passed is False
        assert len(result.failed_items) == 1
