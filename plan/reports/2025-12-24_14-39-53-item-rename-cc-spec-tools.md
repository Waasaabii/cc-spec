# 修复报告：Viewer 改名为 cc-spec-tools

## 完成内容
- 更新前端与 Tauri 的产品/包名显示为 cc-spec tools
- 迁移配置与数据目录到 tools 命名（保留 viewer 旧路径回退）
- 同步 Python streaming 配置路径为 tools.json，并保留 viewer.json 兼容读取

## 兼容与迁移说明
- 仍支持读取旧的 viewer.json、viewer 目录与历史路径，优先使用新的 tools 命名

## 验证
- 运行 `cargo build`（apps/cc-spec-tool/src-tauri）失败：目标可执行文件被占用，提示拒绝访问 (os error 5)

## 风险
- 若 cc-spec-tools 正在运行会导致构建失败；需先关闭正在运行的进程再重试构建

## 参考
- `apps/cc-spec-tool/package.json:2`
- `apps/cc-spec-tool/index.html:6`
- `apps/cc-spec-tool/src-tauri/tauri.conf.json:3`
- `apps/cc-spec-tool/src-tauri/Cargo.toml:2`
- `apps/cc-spec-tool/src-tauri/src/projects.rs:50`
- `apps/cc-spec-tool/src-tauri/src/main.rs:607`
- `src/cc_spec/codex/streaming.py:17`
