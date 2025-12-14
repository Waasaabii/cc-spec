"""Unit tests for UI components."""

import io
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from cc_spec.ui import (
    STATUS_ICONS,
    THEME,
    ProgressTracker,
    WaveProgressTracker,
    get_status_color,
    get_status_icon,
    show_progress,
    show_status_panel,
    show_task_table,
    show_wave_tree,
)


@pytest.fixture
def console():
    """Create a Rich console with string output."""
    string_io = io.StringIO()
    return Console(file=string_io, force_terminal=True, width=120)


class TestThemeAndIcons:
    """Test theme and icon constants."""

    def test_theme_colors(self):
        """Test that all expected theme colors are defined."""
        expected_keys = [
            "success",
            "warning",
            "error",
            "info",
            "pending",
            "in_progress",
            "completed",
            "failed",
            "timeout",
        ]
        for key in expected_keys:
            assert key in THEME
            assert isinstance(THEME[key], str)

    def test_status_icons(self):
        """Test that all expected status icons are defined."""
        expected_keys = ["pending", "in_progress", "completed", "failed", "timeout"]
        for key in expected_keys:
            assert key in STATUS_ICONS
            assert isinstance(STATUS_ICONS[key], str)

    def test_get_status_color(self):
        """Test get_status_color function."""
        assert get_status_color("pending") == THEME["pending"]
        assert get_status_color("completed") == THEME["completed"]
        assert get_status_color("unknown_status") == "white"

    def test_get_status_icon(self):
        """Test get_status_icon function."""
        assert get_status_icon("pending") == STATUS_ICONS["pending"]
        assert get_status_icon("completed") == STATUS_ICONS["completed"]
        assert get_status_icon("unknown_status") == "○"


class TestDisplayFunctions:
    """Test display functions."""

    def test_show_status_panel(self, console):
        """Test show_status_panel displays correctly."""
        show_status_panel(
            console,
            change_name="test-change",
            current_stage="apply",
            progress={"waves_completed": 2, "waves_total": 5},
        )

        output = console.file.getvalue()
        assert "test-change" in output
        assert "执行" in output  # "apply" maps to "执行" in Chinese
        assert "2/5" in output

    def test_show_status_panel_no_progress(self, console):
        """Test show_status_panel without progress info."""
        show_status_panel(
            console,
            change_name="simple-change",
            current_stage="specify",
        )

        output = console.file.getvalue()
        assert "simple-change" in output
        assert "编写规格" in output  # "specify" maps to "编写规格" in Chinese

    def test_show_task_table(self, console):
        """Test show_task_table displays correctly."""
        tasks = [
            {
                "id": "01-SETUP",
                "status": "completed",
                "wave": 0,
                "estimate": "30k",
                "dependencies": [],
            },
            {
                "id": "02-MODEL",
                "status": "in_progress",
                "wave": 1,
                "estimate": "50k",
                "dependencies": ["01-SETUP"],
            },
        ]

        show_task_table(console, tasks)

        output = console.file.getvalue()
        assert "01-SETUP" in output
        assert "02-MODEL" in output
        assert "已完成" in output  # "completed" maps to "已完成" in Chinese
        assert "进行中" in output  # "in_progress" maps to "进行中" in Chinese

    def test_show_task_table_no_wave(self, console):
        """Test show_task_table without wave column."""
        tasks = [
            {
                "id": "TASK-1",
                "status": "pending",
                "estimate": "20k",
                "dependencies": [],
            }
        ]

        show_task_table(console, tasks, show_wave=False)

        output = console.file.getvalue()
        assert "TASK-1" in output
        assert "待执行" in output  # "pending" maps to "待执行" in Chinese

    def test_show_wave_tree(self, console):
        """Test show_wave_tree displays correctly."""
        waves = {
            0: [{"id": "01-SETUP", "status": "completed", "dependencies": []}],
            1: [
                {"id": "02-MODEL", "status": "in_progress", "dependencies": ["01-SETUP"]},
                {"id": "03-API", "status": "pending", "dependencies": ["01-SETUP"]},
            ],
        }

        show_wave_tree(console, waves, current_wave=1)

        output = console.file.getvalue()
        assert "波次 0" in output  # "Wave 0" is displayed as "波次 0" in Chinese
        assert "波次 1" in output  # "Wave 1" is displayed as "波次 1" in Chinese
        assert "01-SETUP" in output
        assert "02-MODEL" in output
        assert "03-API" in output


class TestProgressComponents:
    """Test progress components."""

    def test_show_progress(self, console):
        """Test show_progress function."""
        show_progress(console, "Processing tasks", total=10, completed=7)

        output = console.file.getvalue()
        # Strip ANSI codes for easier matching
        import re
        clean_output = re.sub(r'\x1b\[[0-9;]*m', '', output)

        assert "Processing tasks" in clean_output
        assert "7" in clean_output and "10" in clean_output
        assert "70.0%" in clean_output

    def test_show_progress_zero_total(self, console):
        """Test show_progress with zero total."""
        show_progress(console, "Empty progress", total=0, completed=0)

        output = console.file.getvalue()
        # Strip ANSI codes for easier matching
        import re
        clean_output = re.sub(r'\x1b\[[0-9;]*m', '', output)

        assert "Empty progress" in clean_output
        assert "0" in clean_output

    def test_progress_tracker(self):
        """Test ProgressTracker basic functionality."""
        string_io = io.StringIO()
        console = Console(file=string_io, force_terminal=True)

        with ProgressTracker(console) as tracker:
            tracker.add_task("task1", "Task 1", total=100)
            tracker.update_task("task1", advance=50)
            tracker.update_task("task1", completed=75)
            tracker.complete_task("task1")

        # Verify no exceptions raised
        assert True

    def test_progress_tracker_remove_task(self):
        """Test ProgressTracker task removal."""
        string_io = io.StringIO()
        console = Console(file=string_io, force_terminal=True)

        tracker = ProgressTracker(console)
        tracker._progress.__enter__()

        tracker.add_task("task1", "Task 1", total=100)
        tracker.remove_task("task1")

        # Task should be removed
        assert "task1" not in tracker._tasks

        tracker._progress.__exit__(None, None, None)

    def test_wave_progress_tracker(self, console):
        """Test WaveProgressTracker."""
        tracker = WaveProgressTracker(console, total_waves=3, total_tasks=5)

        # Start wave
        tracker.start_wave(0, ["01-SETUP"])
        tracker.update_task(0, "01-SETUP", "completed")
        tracker.complete_wave(0)

        # Start next wave
        tracker.start_wave(1, ["02-MODEL", "03-API"])
        tracker.update_task(1, "02-MODEL", "in_progress")

        # Render progress
        table = tracker.render()
        assert table is not None

        # Display progress
        tracker.display()
        output = console.file.getvalue()
        assert "波次执行进度" in output  # "Wave Execution Progress" is displayed as "波次执行进度" in Chinese

    def test_wave_progress_tracker_time_estimation(self, console):
        """Test WaveProgressTracker time estimation."""
        tracker = WaveProgressTracker(console, total_waves=2, total_tasks=4)

        # Simulate some progress
        tracker.start_wave(0, ["01-SETUP", "02-MODEL"])
        tracker.update_task(0, "01-SETUP", "completed")
        tracker.update_task(0, "02-MODEL", "completed")
        tracker.complete_wave(0)

        # Check that time estimation is included
        table = tracker.render()
        assert table is not None


class TestPromptFunctions:
    """Test prompt functions (with mocking)."""

    @patch("cc_spec.ui.prompts.readchar.readkey")
    def test_confirm_action_yes(self, mock_readkey, console):
        """Test confirm_action with yes response."""
        from cc_spec.ui.prompts import confirm_action

        mock_readkey.return_value = "y"

        result = confirm_action(console, "Continue?")

        assert result is True
        output = console.file.getvalue()
        assert "已确认" in output  # "Confirmed" is displayed as "已确认" in Chinese

    @patch("cc_spec.ui.prompts.readchar.readkey")
    def test_confirm_action_no(self, mock_readkey, console):
        """Test confirm_action with no response."""
        from cc_spec.ui.prompts import confirm_action

        mock_readkey.return_value = "n"

        result = confirm_action(console, "Continue?")

        assert result is False
        output = console.file.getvalue()
        assert "已取消" in output  # "Cancelled" is displayed as "已取消" in Chinese

    @patch("cc_spec.ui.prompts.readchar.readkey")
    def test_confirm_action_default(self, mock_readkey, console):
        """Test confirm_action with default response."""
        from cc_spec.ui.prompts import readchar
        from cc_spec.ui.prompts import confirm_action

        mock_readkey.return_value = readchar.key.ENTER

        result = confirm_action(console, "Continue?", default=True)

        assert result is True

    @patch("cc_spec.ui.prompts.readchar.readkey")
    def test_confirm_action_warning(self, mock_readkey, console):
        """Test confirm_action with warning flag."""
        from cc_spec.ui.prompts import confirm_action

        mock_readkey.return_value = "y"

        result = confirm_action(console, "Delete files?", warning=True)

        assert result is True
        output = console.file.getvalue()
        assert "警告" in output  # "Warning" is displayed as "警告" in Chinese

    @patch("cc_spec.ui.prompts.readchar.readkey")
    def test_select_option_single(self, mock_readkey, console):
        """Test select_option with single selection."""
        from cc_spec.ui.prompts import readchar
        from cc_spec.ui.prompts import select_option

        # Simulate Enter key press
        mock_readkey.return_value = readchar.key.ENTER

        options = {"option1": "First option", "option2": "Second option"}
        result = select_option(console, options, default="option1")

        assert result == "option1"

    @patch("cc_spec.ui.prompts.readchar.readkey")
    def test_select_option_navigation(self, mock_readkey, console):
        """Test select_option with navigation."""
        from cc_spec.ui.prompts import readchar
        from cc_spec.ui.prompts import select_option

        # Simulate Down arrow then Enter
        mock_readkey.side_effect = [readchar.key.DOWN, readchar.key.ENTER]

        options = ["option1", "option2", "option3"]
        result = select_option(console, options)

        assert result == "option2"

    @patch("cc_spec.ui.prompts.readchar.readkey")
    def test_select_option_cancel(self, mock_readkey, console):
        """Test select_option with cancellation."""
        from cc_spec.ui.prompts import readchar
        from cc_spec.ui.prompts import select_option

        mock_readkey.return_value = readchar.key.ESC

        options = ["option1", "option2"]
        result = select_option(console, options)

        assert result == ""

    @patch("builtins.input")
    def test_get_text_input(self, mock_input, console):
        """Test get_text_input function."""
        from cc_spec.ui.prompts import get_text_input

        mock_input.return_value = "test input"

        result = get_text_input(console, "Enter name")

        assert result == "test input"

    @patch("builtins.input")
    def test_get_text_input_default(self, mock_input, console):
        """Test get_text_input with default value."""
        from cc_spec.ui.prompts import get_text_input

        mock_input.return_value = ""

        result = get_text_input(console, "Enter name", default="default-name")

        assert result == "default-name"

    @patch("builtins.input")
    def test_get_text_input_empty_required(self, mock_input, console):
        """Test get_text_input with empty input when required."""
        from cc_spec.ui.prompts import get_text_input

        # First return empty, then return valid input
        mock_input.side_effect = ["", "valid input"]

        result = get_text_input(console, "Enter name", required=True)

        assert result == "valid input"
        assert mock_input.call_count == 2
