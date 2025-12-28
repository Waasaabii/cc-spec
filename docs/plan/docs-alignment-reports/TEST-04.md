# TEST-04 Report

新增测试辅助工具并替换主要 CLI 测试的字符串断言与 YAML 读写，减少重复造轮子。

## 变更摘要
- 新增 tests/helpers.py：assert_contains_any/read_yaml/write_yaml。
- conftest 增加 tests 路径入 sys.path 以便 helpers 可用。
- CLI 测试的多分支 stdout 断言改为 assert_contains_any。
- YAML 读写改用 read_yaml/write_yaml（CLI + unit 部分文件）。

## 涉及文件
- tests/helpers.py
- tests/conftest.py
- tests/cli/test_cmd_apply.py
- tests/cli/test_cmd_archive.py
- tests/cli/test_cmd_checklist.py
- tests/cli/test_cmd_plan.py
- tests/cli/test_cmd_specify.py
- tests/cli/test_cmd_quick_delta.py
- tests/cli/test_cmd_goto.py
- tests/cli/test_cmd_update.py
- tests/cli/test_cmd_init.py
- tests/cli/test_cmd_clarify.py
- tests/unit/test_state.py
- tests/unit/test_config.py
