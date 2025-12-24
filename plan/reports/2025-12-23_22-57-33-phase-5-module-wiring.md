# Phase 5 报告：模块连线核查（索引/skills/翻译/数据库/导出/sidecar/并发/设置）

## 范围
- 前端 UI 是否有入口与调用
- 后端命令是否被触发
- 模块事件是否被前端订阅

## 结论总览
| 模块 | 后端命令 | 前端入口 | 事件订阅 | 结论 |
| --- | --- | --- | --- | --- |
| 索引 Index | 已注册 (init/update/status) | IndexPrompt 未接入 | 未订阅 | 未连线 |
| Skills | 已注册 | useSkills 未被引用 | 未订阅 | 未连线 |
| 翻译 Translation | translate_text 被调用 | TranslateButton 未接入 | 未订阅 | 部分连线（仅 API） |
| 数据库 Database | 已注册 | 无入口 | 未订阅 | 未连线 |
| 导出 Export | 已注册 | 无入口 | 未订阅 | 未连线 |
| Sidecar | 已注册 | useSidecar 未接入 | 仅 sidecar stream 监听 | 未连线 |
| 并发控制 | get_concurrency_status 被调用 | SettingsPage 展示 | 队列控制未接入 | 部分连线 |
| 设置 Settings | get/set 被调用 | SettingsPage 已接入 | - | 已连线 |

## 详细发现
- IndexPrompt 组件存在但未在 App.tsx 或其他入口使用
- useSkills/useSidecar/useSettings Hooks 未被引用（重复逻辑分散在 App.tsx 和 SettingsPage.tsx）
- 翻译仅调用 translate_text API，下载/缓存/状态相关命令无入口
- Database/Export 无任何前端调用
- 并发队列控制（cancel_queued_task/update_concurrency_limits）无前端入口

## 参考证据
- `apps/cc-spec-tool/src/components/index/IndexPrompt.tsx:1`
- `apps/cc-spec-tool/src/hooks/useSkills.ts:1`
- `apps/cc-spec-tool/src/components/chat/TranslateButton.tsx:1`
- `apps/cc-spec-tool/src/App.tsx:6`
