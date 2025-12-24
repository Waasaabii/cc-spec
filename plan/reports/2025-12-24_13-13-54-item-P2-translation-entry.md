# 完成报告：P2 翻译入口接入

## 完成内容
- 设置页加入翻译模型状态与下载/清理入口（含进度提示）
- RunCard 中为 agent 行添加翻译按钮并展示译文
- 补充翻译模型前端类型定义

## 代码变更
- `apps/cc-spec-tool/src/components/settings/SettingsPage.tsx`
- `apps/cc-spec-tool/src/components/chat/RunCard.tsx`
- `apps/cc-spec-tool/src/components/chat/TranslateButton.tsx`
- `apps/cc-spec-tool/src/types/translation.ts`

## 风险
- 下载依赖本地 curl 与网络，失败时仅提示错误
- 翻译基于整行文本，含代码块时可能影响译文质量

## 后续步骤
- P2：事件协议统一接入
- P3：前端信息架构/页面重构优化

## 参考
- `apps/cc-spec-tool/src/components/settings/SettingsPage.tsx:280`
- `apps/cc-spec-tool/src/components/chat/RunCard.tsx:237`
- `apps/cc-spec-tool/src/components/chat/TranslateButton.tsx:12`
- `apps/cc-spec-tool/src/types/translation.ts:1`
