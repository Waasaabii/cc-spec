"""基于 Rich 的终端 UI 组件。"""

from cc_spec.ui.display import (
    STAGE_NAMES,
    STATUS_ICONS,
    THEME,
    get_status_color,
    get_status_icon,
    show_status_panel,
    show_task_table,
    show_wave_tree,
)
from cc_spec.ui.progress import (
    ProgressTracker,
    WaveProgressTracker,
    show_progress,
)
from cc_spec.ui.prompts import (
    confirm_action,
    get_text_input,
    select_option,
)

__all__ = [
    # 主题与常量
    "THEME",
    "STATUS_ICONS",
    "STAGE_NAMES",
    # 展示函数
    "show_status_panel",
    "show_task_table",
    "show_wave_tree",
    "get_status_color",
    "get_status_icon",
    # 进度组件
    "ProgressTracker",
    "WaveProgressTracker",
    "show_progress",
    # 交互提示函数
    "confirm_action",
    "select_option",
    "get_text_input",
]
