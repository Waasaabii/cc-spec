# Scoring Module Usage Examples

## Basic Usage

### 1. Parse Checklist from Markdown

```python
from cc_spec.core.scoring import parse_checklist

checklist_content = """
- [x] Create project structure
- [x] Configure dependencies
- [ ] Write documentation
- [-] Optional feature (skipped)
"""

items = parse_checklist(checklist_content)

# Result: 4 CheckItem objects
# - 2 PASSED items (score=10 each)
# - 1 FAILED item (score=0)
# - 1 SKIPPED item (score=0, not counted)
```

### 2. Calculate Score

```python
from cc_spec.core.scoring import parse_checklist, calculate_score

items = parse_checklist(checklist_content)
result = calculate_score(items, threshold=80)

print(f"Total Score: {result.total_score}/{result.max_score}")
print(f"Percentage: {result.percentage:.1f}%")
print(f"Passed: {result.passed}")
print(f"Failed Items: {len(result.failed_items)}")
```

Output:
```
Total Score: 20/30
Percentage: 66.7%
Passed: False
Failed Items: 1
```

### 3. Format Result

```python
from cc_spec.core.scoring import format_result

formatted = format_result(result)
print(formatted)
```

Output:
```markdown
# Checklist Score Result

**Total Score**: 20/30
**Percentage**: 66.7%
**Threshold**: 80%
**Status**: ✗ FAILED

## Items

- [x] Create project structure (10/10)
- [x] Configure dependencies (10/10)
- [ ] Write documentation (0/10)
- [-] Optional feature (skipped)

## Failed Items

- Write documentation
```

### 4. Generate Failure Report

```python
from cc_spec.core.scoring import generate_failure_report

report = generate_failure_report(result)

# Optional: write to file if you want a local report
with open("checklist-result.md", "w") as f:
    f.write(report)
```

Output (checklist-result.md):
```markdown
# Checklist Validation Failed

The checklist validation did not meet the required threshold of 80%.
Your score: **66.7%** (20/30)

## Failed Items

The following items need to be addressed:

1. **Write documentation**

## Next Steps

To continue with the workflow:

1. Review the failed items above
2. Complete the missing tasks
3. Run `cc-spec clarify <change-name>` to rework the tasks
4. Re-run the checklist validation after making changes
```

### 5. Extract Checklists from tasks.yaml

```python
from cc_spec.core.scoring import extract_checklists_from_tasks_md

tasks_content = """
### 01-SETUP - Project Setup

**Checklist**:
- [x] Create configuration file
- [x] Initialize repository
- [ ] Setup CI/CD

### 02-BUILD - Build System

**Checklist**:
- [x] Configure build tool
- [ ] Add tests
"""

checklists = extract_checklists_from_tasks_md(tasks_content)

# Result: dict with task IDs as keys
# {
#   "01-SETUP": [CheckItem(...), CheckItem(...), CheckItem(...)],
#   "02-BUILD": [CheckItem(...), CheckItem(...)]
# }

# Score each task separately
for task_id, items in checklists.items():
    result = calculate_score(items, threshold=80)
    print(f"{task_id}: {result.percentage:.1f}% - {'PASSED' if result.passed else 'FAILED'}")
```

Output:
```
01-SETUP: 66.7% - FAILED
02-BUILD: 50.0% - FAILED
```

## Advanced Usage

### Custom Scoring

```python
from cc_spec.core.scoring import CheckItem, CheckStatus, calculate_score

# Create custom items with different max_score
items = [
    CheckItem("Critical task", CheckStatus.PASSED, score=20, max_score=20),
    CheckItem("Important task", CheckStatus.PASSED, score=10, max_score=10),
    CheckItem("Minor task", CheckStatus.FAILED, score=0, max_score=5),
]

result = calculate_score(items, threshold=85)

# Total: 30/35 = 85.7% (PASSED)
```

### Adding Notes to Items

```python
from cc_spec.core.scoring import CheckItem, CheckStatus

item = CheckItem(
    description="Database migration",
    status=CheckStatus.FAILED,
    score=0,
    notes="Migration script failed due to missing column"
)

# Notes will appear in formatted output and failure reports
```

### Complete Workflow Example

```python
from pathlib import Path
from cc_spec.core.scoring import (
    extract_checklists_from_tasks_md,
    calculate_score,
    format_result,
    generate_failure_report,
)

# 1. Read tasks.yaml
tasks_path = Path(".cc-spec/changes/my-change/tasks.yaml")
tasks_content = tasks_path.read_text(encoding="utf-8")

# 2. Extract all checklists
checklists = extract_checklists_from_tasks_md(tasks_content)

# 3. Calculate overall score
all_items = []
for items in checklists.values():
    all_items.extend(items)

result = calculate_score(all_items, threshold=80)

# 4. Save results (CLI default writes to KB; file output is optional)
if result.passed:
    print("✓ All tasks completed successfully!")
    print(format_result(result))
else:
    print("✗ Checklist validation failed")

    # Optional: save failure report to a file
    report_path = Path(".cc-spec/changes/my-change/checklist-result.md")
    report_path.write_text(generate_failure_report(result), encoding="utf-8")

    print(f"Failure report saved to: {report_path}")
```

## Checklist Format

The module supports standard markdown checkbox syntax:

- `- [x]` or `* [x]` → PASSED (10 points)
- `- [ ]` or `* [ ]` → FAILED (0 points)
- `- [-]` or `* [-]` → SKIPPED (not counted)

Case insensitive: `[X]`, `[x]` both work.

## Scoring Rules

1. **PASSED items**: Earn full score (default 10 points)
2. **FAILED items**: Earn 0 points
3. **SKIPPED items**: Not included in total or max score
4. **Percentage**: `(total_score / max_score) * 100`
5. **Pass threshold**: Default 80%, customizable via config.yaml

## Integration with cc-spec Workflow

This module is used in the `checklist` stage (tasks.yaml source):

1. Parse checklists from `tasks.yaml`
2. Calculate scores for all tasks
3. If score >= threshold:
   - Move to `archive` stage
   - Mark change as completed
4. If score < threshold:
   - Write failure record to KB (default behavior)
   - Optionally generate `checklist-result.md` with `--write-report`
   - Stay in `checklist` stage
   - User can run `clarify` or `apply` to rework tasks

## Error Handling

The module is designed to be robust:

- Empty content returns empty list
- Invalid lines are ignored
- Unknown task IDs are skipped
- Division by zero is handled (returns 0%)
- Missing checklists return empty dict


## 权重说明

四维度权重以 `config.yaml` 为准（默认 30/25/25/20），评分计算按配置权重执行。
