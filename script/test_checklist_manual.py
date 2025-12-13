#!/usr/bin/env python3
"""Manual test script for checklist command.

This script creates a test environment and runs the checklist command
to verify basic functionality.
"""

import os
import tempfile
from datetime import datetime
from pathlib import Path

# Add src to path for imports
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))

from cc_spec.core.state import (
    ChangeState,
    Stage,
    StageInfo,
    TaskStatus,
    update_state,
)


def create_test_environment():
    """Create a test environment with a change ready for checklist."""
    # Create temp directory
    temp_dir = tempfile.mkdtemp(prefix="cc-spec-test-")
    project_root = Path(temp_dir)
    cc_spec_dir = project_root / ".cc-spec"
    changes_dir = cc_spec_dir / "changes"
    change_name = "test-checklist"
    change_dir = changes_dir / change_name

    # Create directories
    change_dir.mkdir(parents=True, exist_ok=True)

    # Create tasks.md with checklist
    tasks_content = """# Tasks - test-checklist

## 概览

| Wave | Task-ID | 预估 | 状态 | 依赖 |
|------|---------|------|------|------|
| 0 | 01-SETUP | 30k | 🟩 完成 | - |
| 1 | 02-MODEL | 50k | 🟨 进行中 | 01-SETUP |

## 任务详情

### 01-SETUP - Project Setup
**预估上下文**: ~30k tokens
**状态**: 🟩 完成
**依赖**: 无

**必读文档**:
- docs/plan/spec.md

**核心代码入口**:
- src/config/

**Checklist**:
- [x] 创建配置文件
- [x] 添加环境变量
- [x] 初始化数据库

---

### 02-MODEL - Data Model
**预估上下文**: ~50k tokens
**状态**: 🟨 进行中
**依赖**: 01-SETUP

**必读文档**:
- docs/plan/spec.md

**核心代码入口**:
- src/models/

**Checklist**:
- [x] 创建数据模型
- [ ] 添加验证逻辑
- [ ] 编写单元测试
"""
    tasks_path = change_dir / "tasks.md"
    tasks_path.write_text(tasks_content, encoding="utf-8")

    # Create status.yaml
    state = ChangeState(
        change_name=change_name,
        created_at=datetime.now().isoformat(),
        current_stage=Stage.APPLY,
        stages={
            Stage.SPECIFY: StageInfo(
                status=TaskStatus.COMPLETED,
                started_at=datetime.now().isoformat(),
                completed_at=datetime.now().isoformat(),
            ),
            Stage.CLARIFY: StageInfo(status=TaskStatus.COMPLETED),
            Stage.PLAN: StageInfo(status=TaskStatus.COMPLETED),
            Stage.APPLY: StageInfo(
                status=TaskStatus.COMPLETED,
                started_at=datetime.now().isoformat(),
                completed_at=datetime.now().isoformat(),
            ),
            Stage.CHECKLIST: StageInfo(status=TaskStatus.PENDING),
            Stage.ARCHIVE: StageInfo(status=TaskStatus.PENDING),
        },
    )

    status_path = change_dir / "status.yaml"
    update_state(status_path, state)

    print(f"✓ Created test environment at: {project_root}")
    print(f"  Change: {change_name}")
    print(f"  Tasks: {tasks_path}")
    print(f"  Status: {status_path}")
    print()

    return project_root, change_name


def test_scoring_functions():
    """Test the scoring module functions directly."""
    print("Testing scoring module functions...")
    print()

    from cc_spec.core.scoring import (
        calculate_score,
        extract_checklists_from_tasks_md,
        parse_checklist,
    )

    # Test parse_checklist
    checklist_text = """
- [x] Item 1 completed
- [ ] Item 2 not done
- [-] Item 3 skipped
- [x] Item 4 completed
"""
    items = parse_checklist(checklist_text)
    print(f"Parsed {len(items)} checklist items:")
    for item in items:
        print(f"  [{item.status.value}] {item.description} (score: {item.score})")
    print()

    # Test calculate_score
    result = calculate_score(items, threshold=80)
    print(f"Score calculation:")
    print(f"  Total score: {result.total_score}/{result.max_score}")
    print(f"  Percentage: {result.percentage:.1f}%")
    print(f"  Passed: {result.passed}")
    print(f"  Failed items: {len(result.failed_items)}")
    print()

    # Test extract_checklists_from_tasks_md
    tasks_content = """# Tasks

### 01-SETUP - Setup Task

**Checklist**:
- [x] Item 1
- [ ] Item 2

---

### 02-MODEL - Model Task

**Checklist**:
- [x] Item 3
- [x] Item 4
"""
    task_checklists = extract_checklists_from_tasks_md(tasks_content)
    print(f"Extracted checklists from tasks.md:")
    for task_id, items in task_checklists.items():
        print(f"  {task_id}: {len(items)} items")
    print()


def main():
    """Main test function."""
    print("=" * 60)
    print("CC-Spec Checklist Command - Manual Test")
    print("=" * 60)
    print()

    # Test 1: Scoring functions
    try:
        test_scoring_functions()
        print("✓ Scoring functions test passed")
        print()
    except Exception as e:
        print(f"✗ Scoring functions test failed: {e}")
        import traceback

        traceback.print_exc()
        return

    # Test 2: Create test environment
    try:
        project_root, change_name = create_test_environment()
        print("✓ Test environment created")
        print()
    except Exception as e:
        print(f"✗ Test environment creation failed: {e}")
        import traceback

        traceback.print_exc()
        return

    # Test 3: Try importing the command
    try:
        from cc_spec.commands.checklist import checklist_command

        print("✓ Checklist command imported successfully")
        print()
    except Exception as e:
        print(f"✗ Checklist command import failed: {e}")
        import traceback

        traceback.print_exc()
        return

    # Test 4: Try running the command (would need CLI runner)
    print("To run the command manually:")
    print(f"  cd {project_root}")
    print(f"  cc-spec checklist {change_name}")
    print()

    print("=" * 60)
    print("Manual test setup completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
