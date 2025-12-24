# 完成报告：P0 项目管理后端

## 完成内容
- 新增项目注册表（JSON）与导入/列表/当前项目/移除命令
- 提供项目路径规范化与去重逻辑，自动设置当前项目

## 代码变更
- `apps/cc-spec-tool/src-tauri/src/projects.rs`
- `apps/cc-spec-tool/src-tauri/src/main.rs`

## 备注
- 注册表存储路径：`%LOCALAPPDATA%/cc-spec-tool/projects.json`（非 Windows 使用 HOME）

## 参考
- `apps/cc-spec-tool/src-tauri/src/projects.rs:122`
- `apps/cc-spec-tool/src-tauri/src/projects.rs:152`
- `apps/cc-spec-tool/src-tauri/src/main.rs:950`
