# 完成报告：A2 Codex 参数对齐

## 完成内容
- codex runner 增加 `CODEX_PATH` 环境变量支持
- Windows/Unix 路径解析改用 where/which，行为与 Python 版 `shutil.which` 对齐
- exec/resume 参数保持 `--skip-git-repo-check --cd <workdir> --json -` 结构

## 代码变更
- 修改 `apps/cc-spec-tool/src-tauri/src/codex_runner.rs`

## 参考
- `apps/cc-spec-tool/src-tauri/src/codex_runner.rs:20`
