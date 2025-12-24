# 完成报告：P2 索引初始化提示接入

## 完成内容
- 当前项目切换时检查 index 是否存在与是否已关闭提示
- 满足条件时自动弹出 IndexPrompt

## 代码变更
- `apps/cc-spec-tool/src/App.tsx`

## 风险
- cc-spec CLI 未安装或不可用时，IndexPrompt 初始化会失败（组件内提示错误）

## 后续步骤
- P2：翻译入口接入（设置页下载 + 消息翻译）
- P2：事件协议统一接入

## 参考
- `apps/cc-spec-tool/src/App.tsx:275`
- `apps/cc-spec-tool/src/App.tsx:689`
