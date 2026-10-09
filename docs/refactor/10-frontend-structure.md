# 10 — 前端结构：分层、单一请求边界、单一状态模式

> **性质**：本文是 `09` 之外的**结构专项**（用户指令 2026-10-09：「前端要重构」「先按照核心原则把前端结构做完整，做完善」）。
> **不改框架**（`08` §9）：Vue 3 + Vite + TS + vue-i18n 保留，不引入 Pinia/Router/新请求库。
> 按原则③先出本文再动代码，同日按 §5 的增量顺序实施；每个增量的判据就是 §4，不靠"看起来改完了"。

## 0. 为什么"结构"本轮必须做，且不违反 08 §5

`08` §5 禁止的是**为顺手统一而改与本轮目标无关的文件**，并把「把 `authFetch`/`apiFetch` 全量替换」当作反例。
本轮恰恰相反：用户点名的目标**就是**前端结构，请求层替换是任务本体而非搭车改动。
判据是"改动是否都挂在同一张卡（FE-1）的验收标准上"——§4 的每条机检都能回溯到本文的一句规定，回溯不到的改动不进来。

## 1. 现状缺陷（实读确认，不是推测）

| # | 缺陷 | 位置 | 后果 |
| --- | --- | --- | --- |
| F1 | 请求边界不唯一：`fetch` 在 `services/api.ts`，XHR 在 `useDocuments.uploadFile`，WS URL 自己拼 `location.host` | `services/api.ts:18` / `useDocuments.ts:143` / `useWebSocket.ts:14` | 基址变更要改三处；401 语义只有 `authFetch` 有，XHR 分支自己判断 `status === 401` |
| F2 | token 读取分散 5 处 | `services/api.ts:6`、`useAuth.ts:9`、`App.vue:55`、`App.vue:71`、`useDocuments.ts:144` | 存储键改名要全仓搜；登出后残留读取点会带着旧 token 再发一次请求 |
| F3 | 状态模式两套并存 | `useAuth`/`useChat`/`useWebSocket` 是模块单例；`useSessions`/`useDocuments` 在函数内建 ref | 每次 `useDocuments()` 调用得到**独立**状态：`SettingsView` 卸载即丢上传进度，两个组件之间列表不同步 |
| F4 | 状态层里做 UI 副作用 | `useSessions.ts:29,37,41`、`useDocuments.ts:88,164,222` 的 `alert`/`confirm`；`useChat.ts:42` 的 `document.querySelector(".chat-container")` | 状态层无法在 SSR/测试下运行；`confirm()` 卡在 action 中间，组件无法替换成自定义对话框 |
| F5 | 事件总线裸用 `window` 且从不解绑 | `services/api.ts:22` dispatch、`App.vue:54` addEventListener | 组件重挂载会重复注册登出回调 |
| F6 | 11 个 `res.json()` 调用点无类型 | `useAuth`/`useSessions`/`useChat`/`useDocuments` | 契约（`contracts/openapi.yaml`）与前端各说各话；`JobStartResponse` 里根本没有 `status` 键，`useDocuments` 却在读 |
| F7 | 虚构类型 | `useChat.ts:12` `RAGTraceEntry`（`{step,label,score,time_ms}`）；`loadMessages(data: unknown[])` 里 `msg: any` | 后端 `rag_trace` 实际是**对象**（`backend/rag/rag_pipeline.py:183`、契约 `RagTrace`），`RagTracePanel` 按数组 `v-for` 渲染，检索过程面板恒空白 |
| F8 | SSE 手工解析内联在业务函数里 | `useChat.ts:125-143` | `\n\n` 分帧、`data: ` 前缀、`[DONE]` 字面量与 JSON.parse 混在 `send()` 的 70 行里 |
| F9 | 死代码与无用依赖 | `frontend/style.css`（1314 行，全仓零引用）、`MessageBubble.vue`（无引用，绕过 `utils/markdown` 的 KaTeX/hljs 配置）、`axios`（`package.json:13`，无人 import） | 体积与误导：留着一个不生效的全局样式文件会让人以为改它有用 |
| F10 | 硬编码中文串绕过 i18n | `useDocuments.ts:41-54` 步骤标签、`CitationChips.vue:5,17`、`ChatView.vue` 的「🐱」等 | 切到 `en` 后这些位置仍显示中文 |
| F11 | `authMode`/`activeNav` 用裸字符串 | `App.vue:49-50` | `'setttings'` 这类拼写错误 typecheck 抓不到 |

## 2. 目标结构

```
frontend/src/
├── api/                      # 唯一的"与后端对话"层，不认识 Vue
│   ├── types.ts              # DTO：名称对齐 openapi components/schemas
│   ├── token.ts              # 登录态持久化唯一所有者（localStorage 只在这读写）
│   ├── events.ts             # 类型化事件总线（auth-expired），替代裸 window 事件
│   ├── http.ts               # 唯一 fetch/XHR 出口：BASE、鉴权头、错误信封→ApiError、401
│   ├── sse.ts                # SSE 帧解析（分帧 / data 前缀 / [DONE] / JSON）
│   ├── ws.ts                 # WS URL（token 走 query：浏览器 WebSocket 带不了 Authorization 头）
│   └── client.ts             # 一条 operationId 一个函数；路径字面量只在这里，check_contracts 从它抽实调集合
├── composables/              # 唯一状态层，**只允许一种模式**：模块级单例 + 零 DOM/零对话框
│   ├── useAuth.ts            # 登录态反应式视图（持久化委托给 api/token）
│   ├── useNav.ts             # activeNav / 历史面板开合（视图状态，非路由）
│   ├── useChat.ts            # 消息、流式、sessionId
│   ├── useSessions.ts        # 会话列表
│   ├── useDocuments.ts       # 文档列表 + 上传/删除 job（轮询定时器由本层持有，不外泄）
│   └── useWebSocket.ts       # WS 通道（URL 由 api/ws.ts 给）
├── components/               # 只有渲染 + 用户意图 → action；对话框/滚动在这一层
├── utils/
│   ├── markdown.ts           # 保持
│   ├── errors.ts             # reason 码 + ApiError → i18n 文案（api 层不产人类文案）
│   ├── dialog.ts             # alert/confirm 的唯一封装（只允许组件层 import）
│   └── fileIcon.ts           # 从 services/api.ts 迁出（它不是 API 关注点）
└── i18n/                     # 保持；步骤标签改走 i18n 键
```

路径常量为什么并入 `client.ts` 而不单开 `endpoints.ts`：常量和调用同处一文件，`check_contracts.py`
抽取的"前端实调集合"就等于"前端真在用的操作"，不会出现有常量没人调的僵尸条目。

**依赖方向是单向的**：`components → composables → api → (browser)`，`utils/` 是叶子层（只被 import，不 import 状态层）。
`composables` 不得 import `utils/dialog`，`api` 不得 import `vue`，视图层不得直接 import `api/http` 或 `api/client`（读数据一律经 composable 的 action）。
唯一的例外形状是 `utils/errors.ts`：它 import `api/http` 只为拿 `ApiError` 与 reason 码做文案翻译，不发请求。

## 3. 规定（每条都对应 §4 的一个机检）

| # | 规定 | 理由 |
| --- | --- | --- |
| R1 | 全仓只有 `src/api/http.ts` 允许出现 `fetch(` / `XMLHttpRequest` | F1：基址与鉴权头只有一个实现点 |
| R2 | 只有 `src/api/token.ts` 允许出现 `localStorage`（`i18n/index.ts` 的 `locale` 例外并登记在 allowlist） | F2 |
| R3 | `src/composables/*` 禁止 `alert(` / `confirm(` / `document.` / `window.` | F4：状态层必须能在无 DOM 环境下推理与测试 |
| R4 | `src/composables/*` 的反应式状态**必须声明在模块作用域**（`export function useX` 之前） | F3：只允许一种状态模式 |
| R5 | 只有 `src/api/http.ts` 允许 `.json()`；其余文件拿到的是泛型 DTO | F6 |
| R6 | DTO 只在 `src/api/types.ts` 定义，且名称与 `contracts/openapi.yaml` 的 schema 一致 | 契约与前端能逐字对照，Go 接管后可复用同一份类型 |
| R7 | 事件只经 `src/api/events.ts`；订阅方必须拿到退订函数并在 `onUnmounted` 调用 | F5 |
| R8 | `src/**` 禁止 `any`（allowlist 只有 `env.d.ts` 的 SFC 声明垫片与 `i18n/index.ts` 的 locale 两处） | F7：`any` 是类型边界的洞 |
| R9 | 用户可见字面串必须是 i18n 键：`i18n/` 之外的字符串字面量里不得出现中文字符（注释不受约束） | F10 |
| R10 | 枚举化视图状态：`NavKey = "newChat" \| "history" \| "settings"`，`AuthMode = "login" \| "register"`；`activeNav` 的 props 不得退回 `string` | F11 |
| R11 | 依赖必须双向干净：`dependencies` 里声明的包要在 `src/**` 被 import（无死依赖），import 到的包要在 `package.json` 里声明（无未声明依赖）；相对路径与 `@/` 别名不算包 | F9：删掉 axios 却留着它的条目，和留着代码一样会误导下一个读的人 |

**`rag_trace` 的形状按契约来**：类型是对象（`RagTrace`，契约只锁 `tool_used`/`tool_name`，其余透传），
`RagTracePanel` 改为按对象条目渲染键值行。这同时修掉 F7 里的"面板恒空白"。

## 4. 验收标准（全部可机检，本机可跑）

| # | 标准 | 判定命令 | 期望 | 等级 |
| --- | --- | --- | --- | --- |
| FE-a | 类型边界成立 | `cd frontend && npm run typecheck` | 退出 0 | mock |
| FE-b | 产物能构建 | `cd frontend && npm run build` | 退出 0 | mock |
| FE-c | §3 十一条规定被机器执行 | `uv run python scripts/check_frontend.py` | 退出 0；`tests/unit/test_check_frontend.py` 为每条规则配一负一正两个用例，证明它会报错而不是恒过、且不误伤注释与合法例外 | mock |
| FE-d | 契约与前端调用集仍双向吻合 | `uv run python scripts/check_contracts.py` | 退出 0（18 个操作不变） | mock |
| FE-e | 进度已同步 | `uv run python scripts/sync_progress.py --check` | 退出 0 | mock |
| FE-f | 浏览器里真的能用（注册→登录→问答→上传） | P0-9 的 Playwright（`X7`/`demo`） | 不在本机范围：无 Docker/PG/LLM key，本轮如实 `not_run` | e2e |

FE-a…FE-e 是本轮的**完成判据**；FE-f 属于 P0-9，所以 FE-1 卡的 `requires` 写 `mock`，
并在 `note` 里点明"浏览器级回归证据在 P0-9"，不用静态检查冒充端到端。

## 5. 实施增量（每个增量单独提交，提交即同步 progress）

1. **api 层落地**（R1/R2/R5/R6）：`types.ts`、`token.ts`、`events.ts`、`http.ts`、`sse.ts`、`ws.ts`、`client.ts`。此时 `services/api.ts` 仍存在，新旧并存但只有新层被引用。
2. **状态层重写**（R3/R4/R7/R8/R9/R10）：六个 composable 统一为模块单例，副作用外移；`utils/dialog.ts`、`utils/fileIcon.ts` 新增。
3. **组件接线**：`App.vue`（`useNav` + 退订）、`ChatView.vue`（滚动/自动增高在这层）、`SettingsView.vue`、`AuthPanel.vue`、`HistorySidebar.vue`、`Sidebar.vue`、`RagTracePanel.vue`（对象条目）、`CitationChips.vue`（i18n）。
4. **删除** `services/`、`MessageBubble.vue`、`frontend/style.css`，从 `package.json` 摘掉 `axios`（同步 lock）。
5. **门禁**：`scripts/check_frontend.py` + `tests/unit/test_check_frontend.py` + CI `frontend` job 加一步 + `08` §6「前端」行改写为新的请求边界与门禁 + 本文。

## 6. 明确不做（防止范围漂移）

- 不加 Router、不加 Pinia、不引 SSR、不做代码分割（`build` 的 1.4 MB 警告留到 P2-7 产品化一起处理）。
- 不重排视觉样式，不改 `assets/*.css` 的类名（结构重构只碰 `.vue` 的 `<script setup>` 与必要的模板绑定）。
- 不动 `vite.config.js` 的代理与 `index.html` 的标题（改名属于全仓一次性动作，随 P1-5 基址切换做）。
- 不新增前端测试框架（本轮无可运行的浏览器，Playwright 属 P0-9）。
