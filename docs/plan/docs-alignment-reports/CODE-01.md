# CODE-01 Report

版本号已集中到 cc_spec.version 常量，并改为语义化比较，避免字符串比较与版本降级风险。

## 变更摘要
- src/cc_spec/version.py：新增版本解析与比较函数（parse_version / is_version_gte）。
- src/cc_spec/core/config.py：默认版本改为 CONFIG_VERSION，比较逻辑改为语义化比较。
- src/cc_spec/commands/plan.py：tasks.yaml 版本改用 TASKS_YAML_VERSION。
- src/cc_spec/commands/update.py：更新说明头注释；subagent 更新时使用 CONFIG_VERSION 且不降级。

## 涉及文件
- src/cc_spec/version.py
- src/cc_spec/core/config.py
- src/cc_spec/commands/plan.py
- src/cc_spec/commands/update.py
