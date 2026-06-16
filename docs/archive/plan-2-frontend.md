# Plan 2 — 前端工程化 ✅ 已完成（归档）

> 完成时间：2026-05
> 从 CDN 单页 HTML 迁移到 Vite + Vue3 SFC + TypeScript，全部功能移植完成。

---

## 迁移成果

- `frontend/` 已迁移为 Vite + Vue3 SFC + TypeScript 项目
- 9 个 `.ts` 源文件 + 7 个 `.vue` 组件（均含 `lang="ts"` 类型检查）
- `vue-tsc --noEmit` 零错误，`vite build` 构建通过
- 旧 CDN `script.js`（856 行）已退役，功能完全移植到 composables

## 2.1 Vite 构建集成（P1）✅

| # | 动作 | 状态 |
|---|------|------|
| 1 | Vite 构建 | ✅ `npx vite build` 通过 |
| 2 | 构建输出到 `frontend/dist/` | ✅ 默认配置 |
| 3 | 开发模式代理后端 API | ✅ `vite.config.js` 已配置 |

## 2.2 组件渐进迁移（P1）✅

| # | 动作 | 状态 |
|---|------|------|
| 1 | ChatView.vue — 对话界面 | ✅ 完整 SSE 流式 + RAG trace 折叠面板 |
| 2 | SettingsView.vue — 文档管理 | ✅ 上传进度（XHR） + 删除轮询 |
| 3 | HistorySidebar.vue — 会话侧边栏 | ✅ 加载/删除 |
| 4 | AuthPanel.vue + Sidebar.vue | ✅ 注册/登录/导航 |
| 5 | MessageBubble.vue + RagTracePanel.vue | ✅ 消息渲染 + RAG 追踪面板 |
| 6 | 旧 CDN `script.js` 退役 | ✅ 856 行全部移植到 composables + SFCs |

## 2.3 TypeScript（P2）✅

| # | 动作 | 状态 |
|---|------|------|
| 1 | `*.js` → `*.ts` + `lang="ts"` | ✅ vue-tsc 零错误 |
| 2 | 类型定义 | ✅ 7 个 interface（Message, RAGStep, SessionRecord 等） |
| 3 | `vue-tsc --noEmit` | ✅ 0 errors |
| 4 | Vite build 通过 | ✅ |

## 2.4 国际化 i18n（P2）✅

| # | 动作 | 状态 |
|---|------|------|
| 1 | vue-i18n 集成 | ✅ |
| 2 | 中文 locale (`zh-CN.json`) | ✅ |
| 3 | 英文 locale (`en.json`) | ✅ |
| 4 | 组件模板 `$t()` 替换 | ✅ |
| 5 | Composables `t()` 替换 | ✅ |

## 2.5 WebSocket 前端（P2）✅

| # | 动作 | 状态 |
|---|------|------|
| 1 | `composables/useWebSocket.ts` | ✅ 已创建 |
| 2 | `useChat.ts` 集成 WS + SSE 双模式 | ✅ 自动检测，优先使用 WS |

## 涉及文件

- 新增：`frontend/`（Vite 工程骨架）、`tsconfig.json`、`src/env.d.ts`、`src/i18n/`
- 迁移：9 个 `.js` → `.ts` 文件，7 个 `.vue` 组件加 `lang="ts"`
- 删除：`src/composables/useSSE.ts`（与 useChat 重复）
