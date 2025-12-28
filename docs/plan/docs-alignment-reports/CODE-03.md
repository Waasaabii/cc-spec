# CODE-03 Report

tasks 来源已统一为 tasks.yaml：命令层读取与模板说明均不再引用 tasks.md。

## 变更摘要
- clarify/list/goto 统一读取 tasks.yaml，并替换提示文案。
- list 改为解析 tasks.yaml（parse_tasks_yaml）。
- goto 查看任务详情改读 tasks.yaml，选项文案更新。
- checklist/plan/tasks 模板文字更新为 tasks.yaml。
- subagent executor 文档与提示同步为 tasks.yaml。
- 测试中涉及 tasks.md 的地方改为 tasks.yaml。

## 涉及文件
- src/cc_spec/commands/clarify.py
- src/cc_spec/commands/list.py
- src/cc_spec/commands/goto.py
- src/cc_spec/templates/checklist-template.md
- src/cc_spec/templates/plan-template.md
- src/cc_spec/templates/tasks-template.md
- src/cc_spec/core/command_templates/checklist_template.py
- src/cc_spec/subagent/executor.py
- tests/conftest.py
- tests/cli/test_cmd_archive.py
- tests/cli/test_cmd_clarify.py
- tests/integration/test_v12_workflow.py
