# 完成报告：P1 项目上下文一键打开 Claude 终端

## 完成内容
- 项目面板新增“打开 Claude 终端”入口
- 调用 Tauri 的 `launch_claude_terminal` 并在错误时提示

## 代码变更
- `apps/cc-spec-tool/src/App.tsx`
- `apps/cc-spec-tool/src/components/projects/ProjectPanel.tsx`
- `apps/cc-spec-tool/src/types/viewer.ts`

## 风险
- 若系统未安装或未配置 `claude` 命令，将触发启动失败提示

## 后续步骤
- P1：接入 Skills 管理 UI
- P2：接入索引初始化提示

## 参考
- `apps/cc-spec-tool/src/App.tsx:152`
- `apps/cc-spec-tool/src/components/projects/ProjectPanel.tsx:95`
- `apps/cc-spec-tool/src/types/viewer.ts:66`
