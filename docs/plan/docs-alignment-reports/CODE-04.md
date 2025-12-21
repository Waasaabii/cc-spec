# CODE-04 Report

快速/标准模式判定、跳过规则与 quick-delta 的 KB 记录已对齐。

## 变更摘要
- quick-delta 增加文件数阈值预检（>5 强制标准）并记录 mode_decision。
- quick-delta 写入 KB：最小需求集、跳过步骤、git/diff 摘要。
- 命令模板加入 Workflow Controls 规则（显式跳过/强制、KB 记录、文件数阈值）。
- 新增 quick-delta 模板并纳入命令生成器。
- 补充 quick-delta 变更计数单测（过滤 .cc-spec）。

## 涉及文件
- src/cc_spec/commands/quick_delta.py
- src/cc_spec/rag/workflow.py
- src/cc_spec/core/command_templates/base.py
- src/cc_spec/core/command_templates/quick_delta_template.py
- src/cc_spec/core/command_templates/__init__.py
- src/cc_spec/core/command_generator.py
- tests/cli/test_quick_delta_v13.py
