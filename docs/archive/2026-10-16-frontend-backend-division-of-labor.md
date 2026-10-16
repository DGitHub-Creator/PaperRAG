> 历史快照：2026-10-16 整理前版本，不作为现行规范或现状。现行入口见 [文档导航](../README.md)。

# 前后端分工与进度记录（前端 / Go / Python 三方归属 · 一页看清谁做什么、做到哪）

> **本文补的是什么**：`13` 写 As-Is 架构、`14` 写功能模块规划、`progress.json` 写进度，但**没有一份文档把「同一件事，
> 前端 / Go / Python 各占哪一段」和「这一段现在做到哪」并排放在一张表里**。本文就是这张表。
>
> **性质**：§1–§2 的**分工**是常青判断（依据 `02` To-Be 与 `13` As-Is，短期不变）；§3–§6 的**进度**是
> **复核时点的概括**，唯一真相始终是 [`../progress.json`](../progress.json)（逐轮实录见 [`../WORKLOG.md`](../WORKLOG.md)），本文不留日志。
>
> **三条口径纪律**：
> 1. **未实现一律标「未实现」**并指向卡片号，不写成既成事实（`08` 原则②）。
> 2. **每张数字表都附取数命令**，改数字前先重跑，别手抄（与 `13 §10` 同口径）。
> 3. **「纸面归属」与「代码现状」分开写**：`contracts/table-acl.md` 里的 `go: W` 在表建出来之前是计划，不是现状（台账 C30）。

---

## 0. 一页总览

### 0.1 运行形态（开发路径，2026-10-13 定案：容器只跑中间件）

```
浏览器 ──5173──▶ vite(dev)  ── /api 代理 ──▶  go-api:8080（Go，唯一公开入口）
                                                │  原生 8 业务 + 4 探针；
                                                └─ 未迁移前缀反代 ─▶ 127.0.0.1:8000 (ai-core / Python)
（prod 形态：nginx 仍 upstream backend 直指 Python:8000、不经 Go —— X2 的红点，属 P0-8）
```

| 层 | 载体 | 形态 | 今天的能力 |
| --- | --- | --- | --- |
| 前端 | `frontend/`（Vue 3 + Vite + TS + vue-router） | 源码 | 60 个源文件；路由 = login + `AppShell` 下 13 个子路由（9 页是 mock，见 `13 §7`）；设置页 5 个板块 |
| Go | `server/cmd/{api,worker}` | 源码 | api：4 探针 + **8 条业务路由**（auth 4 / preferences 2 / sessions 2），未迁移前缀反代 Python；worker：**只有探针** |
| Python | `backend/app.py`（ai-core） | 源码 | **25 条对外面 + 7 条内部面 + 全部 RAG/Agent 逻辑** |
| 中间件 | postgres / redis / etcd / minio(versitygw) / milvus / attu | **容器** | 六容器 |

### 0.2 一句话分工律

> **Go 管「谁在什么时候调用谁」**（入口 / 调度 / 状态 / 真相）；**Python 管「一次调用内部算什么」**（解析 / 检索 / embedding / LLM）；**前端只管「消费与展示」**。

这条律的硬边界只有一条：**全局调度器只能有一个，归 Go**（`AGENTS.md` §7；Python 不得再起循环）。

### 0.3 进度一句话（读数现场取，逐卡状态见 [`../progress.json`](../progress.json)，逐轮实录见 [`../WORKLOG.md`](../WORKLOG.md)）

**完成度 30%（118/394 h）**，P0 十四条卡全部 done、X1–X8 全绿；这些工时**全部落在平台底座**（P0 按口径不产出用户可见能力），产品轴 M1–M16 的可交付能力没有因 P0 收口而增加；P1/P2/P3 尚未开工。分工边界的现状见下面 §0.4。
真正在跑的端到端能力是 **Python 的单论文 RAG 问答**（M4/M6）；Go 侧已原生服务 **8 条业务路由**（认证 4 / 偏好 2 / 会话读删 2）+ 4 条探针，
其余路径反代 Python。P0 退出标准 7/8 pass，唯一红点是 **X2**（prod nginx 仍指 Python，属 P0-8）。

```powershell
# 取数（本页所有进度数字都来自这两条）
uv run python -c "import json;d=json.load(open('docs/progress.json',encoding='utf-8'));[print(p['id'],len(p['tasks']),sum(t['hours'] for t in p['tasks']),sum(t['hours'] for t in p['tasks'] if t['status']=='done')) for p in d['phases']]"
uv run python -m pytest -q          # 测试基线（现状现场取，别抄文档）
```

---

### 0.4 P0 收口时刻的边界（2026-10-15，第十七轮）

> 这一节写的是**已经成立**的边界，不是目标态。每条都有机检或实跑撑着；
> 没有机检的边界迟早漂成一句口号，所以下面每行都点明"谁替我守着"。

| 层 | 今天实际负责的事 | 谁来守 |
| --- | --- | --- |
| **前端** | 展示与交互。业务请求只有一个出口（`api/http.ts`）、只有一份路径字面量（`api/client.ts`）、登录态只在一处（`api/token.ts`）；页面 13 条路由 | `check_frontend.py` R1–R11 + `check_contracts.py`（前端实调 ⊆ 契约，双向） |
| **Go** | 公开入口与门面：`nginx → go-api`，未迁移路径反代给 Python；原生实现 8 条业务面（auth 的 register/login/me/password、偏好 GET/PUT、sessions 列表/删除）+ 4 条探针（`/api/v1/health|ready` 及两条根别名）；直连 PG 读写 `users` / `user_preferences` / `chat_sessions` 三张表 | `check_nginx_routes.py` R1–R3（入口链）、`check_route_ownership.py`（每条面归属与 Go 注册一致）、chain 层 27 条 |
| **Python** | 业务实现与解析/检索/生成；`/internal/v1/ai/*` 内部执行面（P0 只注册 `PARSE_PAPER` / `INDEX_PAPER`）；documents / chat / ws / cache / stats 这些**还没搬**的面 | `check_route_ownership.py`（Python 暴露的每条面必须被认领归属；内部面必须 `/internal/` 前缀）、`internal_api/registry.py` 的显式未注册即失败 |

**三条要说准的边界，别读成"已经到位"**：

1. **入口链在 dev 与 prod 是两套承载物**。dev：`vite(:5173) → go-api(:8080) → 源码 Python(:8000)`，
   **nginx 不在请求路径上**（dev compose 里已没有应用服务，R5 守着这条）。
   prod：`nginx(:80) → go-api → backend`，Go 由 `server/Dockerfile` 构建、作为 compose 服务运行。
   "容器只跑中间件"这条定案**只管 dev**，写进 prod 会变成自相矛盾。
2. **`/api/v1/sessions/{id}`、documents、chat/stream、ws 仍是 Python 实现**（归属表里 17 行 `proxy`）。
   Go 是**门面**不是实现——门面先于重写（`14 §19` 铁律 2），所以"Go 接管了入口"不等于"Go 写了业务"。
3. **被接管的 Python 路由没有立刻删**：`register` / `login` / `me` / sessions 列表与删除五条仍在服务，
   因为 chain 的逐字对拍需要两侧在场。这条例外现在写在 `contracts/route-ownership.md` 的
   `Python 仍在` 列并由脚本判——其中 `register` **没有**对拍用例，登记为台账 **C36**（欠账，P1-2 处置）。

**新增的一条机检（本轮）**：`uv run python scripts/check_route_ownership.py`。
它把归属表回查到三个真相源（Go 源码的路由注册、`backend.app` 的实际路由表、`tests/chain` 的用例名），
专门堵两类过去没人看的漂移：**接管了却没删 Python 那条**、**新加了一条没人认领的面**。
过去 `check_contracts.py` 只比前端↔契约，服务侧完全不在它视野里（台账 C31）。

## 1. 分工矩阵：功能模块 × 三方归属

依据：模块清单取 [`14-feature-modules.md`](14-feature-modules.md) 的 M1–M17；目标归属取
[`02-target-architecture.md`](02-target-architecture.md) §6.1；现状取 `13` 实测。

| 模块 | 前端 | **Go**（编排 / 真相 / 调度） | **Python**（单次执行） | 现状 |
| --- | --- | --- | --- | --- |
| **M1** 论文摄取与解析 | `SettingsView` 上传/列表 | 编排（P1-3） | **解析 / 清洗 / 分块**（现状全包） | 部分实现 |
| **M2** 自动抓取与导入 | — | 编排 + 任务态（P2-9） | 取回 / 解析 | **零存在** |
| **M3** RAG 存储与真相层 | — | **建表 / schema**（P2-1） | 写入（过渡期双 owner） | **未实现** |
| **M4** 检索与匹配 | 检索过程展示 | 门面（P1-4） | **dense+BM25+hybrid+RRF+rerank** | ✅ 已实现 |
| **M5** 学术元数据 | —（公式提问结果可见） | — | **提取 + 入库**（P2-2） | 提取在跑、**入库即丢弃** |
| **M6** 问答与流式 | `ChatView` + `useChat` | 门面 + 事件日志（P1-4/P2-5） | **LangGraph / SSE 生成** | 已实现（两折扣） |
| **M7** 引用可信与定位 | `CitationChips`（仅展示层） | 校验归位（P2-7） | 元数据供给 | **未实现** |
| **M8** 会话 / 笔记 / 工作区 | `HistorySidebar` | **接管读写**（P1-1/P1-2）+ 工作区（F-7） | 现状读写 | 会话活、`workspaces` 死表 |
| **M9** 主题分类与书架 | — | 编排（P2-10） | 聚类（LLM） | **零存在** |
| **M10** 比较矩阵 / Paper Diff | — | 编排（F-1） | 逐格抽取 | 零存在 |
| **M11** Gap Explorer / 看板 | — | 看板状态（F-2） | 候选生成 | 零存在 |
| **M12** Research Lab | — | 编排（F-3） | 建模 / 工具调用 | 零存在 |
| **M13** Research Writing | — | 报告出口（P3-5） | 生成 + 引用接地 | 雏形在 P3 |
| **M14** Radar / Knowledge Diff | — | **长期项目 + 调度**（F-4） | 执行 | 零存在 |
| **M15** 自主研究引擎 | — | **独占**（P3-1…P3-7） | 仅被调用 | 零存在 |
| **M16** 知识双图 / Evidence | —（可视化缺） | **建表 + 读写**（F-8） | — | 死表 |
| **M17** 平台底座 | 登录态 / 契约消费 | **独占**（认证 / 契约 / 任务态 / 记账） | 现状 | 进行中（P0） |

**读法（三句）**：
- **前端只占一列的一半**：17 个模块里只有 M1/M4/M6/M7/M8/M17 有前端承载物，其余 11 个**前端零代码**（根因见 §3.3）。
- **Python 占"执行"列的全部**：所有"算一次"的能力（解析 / 检索 / embedding / LLM / 聚类 / 建模）都在 Python，这是 REUSE，不是待迁移项。
- **Go 占"编排 + 真相 + 调度"列，但今天几乎全是空的**：M15/M17 是 Go **独占**（这两块 Python 不得染指），其余模块 Go 的职责都是"搬家"——把 Python 现状的编排搬到 Go。

---

## 2. 数据写入边界（表级）

### 2.1 目标矩阵（To-Be，`02 §6.2`）

`● 独占写 / ○ 只读 / ✗ 禁止访问`；机器可读版本是 [`../../contracts/table-acl.md`](../../contracts/table-acl.md)，`check_contracts.py` 在 CI 校验。

| 表族 | Go | Python | 说明 |
| --- | --- | --- | --- |
| `users` `workspaces` `workspace_members` | ● | ○ | Python 只校验服务身份 |
| `chat_sessions` `chat_messages` | ● | ✗ | 迁移后 Python 不再持久化对话；且改 append-only |
| `papers` `paper_versions` `paper_files` | ● | ✗ | Go 是文献实体权威 |
| `paper_chunks` | ● | ●（**仅过渡期**） | 过渡期 Python 写以重建可信 chunk 层，Go 接管后转 Go 写 / Python 读 |
| `research_*` `outbox_events` | ● | ✗ | L1 调度真相 |
| `research_budget_usage` `model_usage_records` | ● | ✗ | Python 上报，Go 记账 |
| `knowledge_*` `exploration_*` `evidence_links` `research_claims` `report_*` | ● | ✗ | Python 只交候选 |
| `ai_executions` | ○ | ● | **Python 独占** |

### 2.2 现状：25 张 ACL 表 vs 12 张实建表（差集）

| 集合 | 数量 | 说明 |
| --- | --- | --- |
| 基线实建（`000001` + `000002` + `000003`） | **12** | `users` `chat_sessions` `chat_messages` `parent_chunks` `workspaces` `workspace_members` `paper_nodes` `citation_edges` `glossary_entries` `alembic_version` `ai_executions` `user_preferences` |
| 只在 ACL 里、SQL 里不存在（**纸面归属**） | **18** | `papers` `paper_versions` `paper_files` `paper_chunks` 与全部 `research_*` `outbox_events` `knowledge_items` `exploration_gaps` `evidence_links` `research_claims` `report_sections` |
| 只在 SQL 里、ACL 未覆盖 | **5** | `parent_chunks` `paper_nodes` `citation_edges` `glossary_entries` `alembic_version`（归属即决策 **D6**） |
| 有 model 无读写的**死表** | **4** | `workspaces` `paper_nodes` `citation_edges` `glossary_entries`（`13 §6.4`） |

⚠️ **别把 ACL 的 `go: W` 读成"Go 现在在写"**：那 18 张表在库里**根本不存在**，任何"Go 独占写 X 表"的说法在 P2/P3 建表前**不可执行**（台账 C30）。

```powershell
# 取数（两条命令取差集）
Select-String -Path contracts/table-acl.md -Pattern '^\| `'
Select-String -Path server/migrations/*.up.sql -Pattern 'CREATE TABLE IF NOT EXISTS'
```

---

## 3. 前端：进度与归属

### 3.1 卡片

| 卡片 | 状态 | 等级 | 内容 |
| --- | --- | --- | --- |
| A0-1（旧） | done | mock | 修 `apiFetch/BASE` 未导入等故障；`typecheck` 进 CI |
| **FE-1** | **done** | mock | 结构重构：唯一请求出口 `api/` + 模块单例状态层 + R1–R11 机检；范围后扩到引入 vue-router、重建为 login + 13 个可深链接页 + 设置页 5 板块（见 `13 §7`） |
| P1-5 | pending | e2e | 基址切换 + nginx 收口（业务 API 退出 Python） |
| P2-7 | pending | e2e | 产品化：Monitor / Paper Reader / 引用回溯视图 |

### 3.2 现状（60 个源文件，全部纳入 R1–R11 机检；已引入 vue-router）

路由 = 独立 `login` + `AppShell` 下 13 条懒加载子路由（`router/index.ts`）。真实调接口的只有下面几页，其余 **9 页是 mock**（顶部 `SampleNotice` 徽标 + 归属卡号，逐页清单见 `13 §7`）：

| 视图 | 组件 | 调用端点（实测） |
| --- | --- | --- |
| 登录 | `views/LoginView.vue` | `POST /auth/register` `/auth/login`、`GET /auth/me` |
| 聊天 | `views/ChatView.vue` | `POST /chat/stream`（SSE）、`WS /api/v1/ws/chat` |
| 历史 | `views/HistoryView.vue` | `GET /sessions` `GET/DELETE /sessions/{id}` |
| 书架（文献页签） | `views/LibraryView.vue` | `GET /documents`、`POST /documents/upload/async`、job 轮询、`DELETE /documents/delete/async/{fn}`（主题群/抓取页签是 mock） |
| 设置 | `views/SettingsView.vue`（5 个板块组件） | 改密码 `POST /auth/password`、偏好 `GET|PUT /me/preferences`（Go 原生面）；管理员「知识库管理」板块复用 documents 端点 |

分层：`views/components → composables → api → (browser)` 单向；`api/` 7 模块是唯一请求出口（`client.ts` 是路径字面量唯一所在地、`http.ts` 是唯 fetch/XHR 出口、`token.ts` 是唯一 token 所有者）。

### 3.3 真实缺口

1. **无 vue-router —— 已解决**：FE-1 引入 vue-router，路由 = `login` + `AppShell` 下 13 个子路由（`router/index.ts`），
   `main.ts:29` 已 `.use(router)`；`11 §3` 的五个产品入口有了路由承载物（详见 `13 §7`）。
2. **无 e2e 判据**：`package.json` 只有 `dev/build/preview/typecheck`，**没有 `test:e2e`**；FE-f（浏览器真跑）归 P0-9。
3. **未接 refresh**：`/auth/refresh` 后端存在但前端没人调，60 分钟到期需重登。

```powershell
# 取数
uv run python scripts/check_frontend.py         # R1–R11（60 个源文件全部纳入机检）
cd frontend; npm run typecheck                  # vue-tsc --noEmit
```

---

## 4. Go 侧：进度与覆盖

### 4.1 进程与路由（实测）

| 进程 | 实际挂载 | 位置 |
| --- | --- | --- |
| `cmd/api` | 4 探针：`/api/v1/health` `/ready`、`/health` `/ready` | `internal/httpapi/router.go:50-55` |
| | **8 条业务路由**：`/api/v1/auth/register` `/login` `/me` `/password`、`/api/v1/me/preferences`(GET/PUT)、`/api/v1/sessions`(GET)、`/api/v1/sessions/{id}`(DELETE) | `cmd/api/main.go`（auth 挂 `:110-115`、sessions 挂 `:131-132`） |
| | 未注册的 `/api/*` `/internal/*` `/ws/*` `/metrics` → 反代到 `PYTHON_UPSTREAM`（默认 `127.0.0.1:8000`） | `internal/httpapi/upstream.go`、`router.go:60-64` |
| `cmd/worker` | 只有 `/health` `/ready`；**无调度循环** | `cmd/worker/main.go:37-38`，自述 `:52`「调度器属 P3」 |

`internal/` 六个包：`auth`（PBKDF2 / JWT / 注册登录 me / 改密码 / 偏好）、`config`（env + `ValidateAuth()` fail-fast）、
`db`（sqlc 生成物 + pgx 池）、`httpapi`（chi 组装、错误信封、中间件、探针、反代）、`observability`（slog + trace）、`session`（会话列表读 / 删）。

### 4.2 数据访问的真实覆盖面

⚠️ **sqlc 只对 3 张表生成了 SQL**（10 条命名查询，分布 3 个文件）——`server/sql/queries/users.sql` 六条（`InsertUser` `GetUserByUsername` `GetUserByID` `GetProfileByUsername` `UpdateUserPasswordByUsername` `UpdateUserRoleByUsername`）、`user_preferences.sql` 两条（`GetUserPreferences` `UpsertUserPreferences`）、`chat_sessions.sql` 两条（`ListSessionInfosForUser` `DeleteSessionForUser`）。也就是 **Go 今天只读写 `users` / `user_preferences` / `chat_sessions` 三张表**；
`internal/db/models.go` 里**其余表的 struct 只是声明、零查询**（"生成进 model" ≠ "用得着"）。

### 4.3 卡片

| 卡片 | 状态 | 等级 |
| --- | --- | --- |
| P0-1 Go 服务骨架 | done | real |
| P0-3 Go 数据访问层（sqlc） | done | mock |
| P0-4 契约目录 | done | mock |
| P0-5 跨语言契约测试骨架 + chain fixture | done | real |
| P0-6 认证垂直切片 | in_progress | mock（X4/X5 **pass**，real 档待 `--from-db`） |
| P0-7 ai-core 内部执行面 | in_progress | mock |
| P0-8 Go 接线与跨环境实跑 | in_progress | real（Go 侧已接反代 + 认证/偏好/会话面；剩 nginx upstream 切 Go + C29 遗留物） |
| P1-0…P1-8（9 张） | pending | none |

```powershell
# 取数
Select-String -Path server/sql/queries/*.sql -Pattern '^-- name:'
Select-String -Path server/internal/db/*.sql.go -Pattern 'FROM |INSERT INTO '
cd server && gofmt -l . && go vet ./... && go test ./...
```

---

## 5. Python 侧：进度与三分类

注册点 `backend/app.py:149-158`（`/api/v1` 前缀加在 `:152-156`；**`:149` 的 health_router 不带前缀**）。

| 类 | 数量 | 内容 | 状态 |
| --- | --- | --- | --- |
| **A. 浏览器在用** | 13 HTTP + 1 WS | auth(3) / sessions(3) / chat/stream(1) / documents(5) / ws(1) | ✅ 在产 |
| **B. 内部面** `/internal/v1/ai/*` | 7 | `/execute` `/executions` `/executions/{id}` `/result` `/cancel` `/healthz` `/readyz` | ⚠️ **零生产 caller**（派发方 `go-worker` 无循环） |
| **C. 前端不调但仍可达** | 12 | `/auth/refresh` `/chat` 旧上传 3 条 `/stats/usage` 2 条 `/cache/clear` `/health` `/ready` `/metrics` | P1-7 的审计 + Deprecation 头清单 |

⚠️ 目标态那句「**Python 只被动执行单次 `AIExecution`**」**今天不成立**：A+C 共 **25 条面仍挂在 Python**。其中 dev 形态下 register/login/me/password、preferences(GET+PUT)、sessions(list+delete) 这 **8 条已由 Go 原生服务**，Python 的同名路由只在 prod（nginx→Python）才被走到；其余由 Go 反代到 Python。

RAG/Agent 主体（`backend/rag/*` 13 文件、`backend/agent/*`、`backend/vectordb/*`、`backend/services/*`）是**在产的唯一端到端能力**（M4/M6）。

```powershell
# 取数
Select-String -Path backend/app.py -Pattern 'include_router|APIRouter'
Select-String -Path backend/**/*.py -Pattern '@router\.(get|post|delete|put)'
```

---

## 6. 卡片进度记录（全 40 张，按阶段）

**逐卡状态与证据等级以 [`../progress.json`](../progress.json) 为唯一真相**——本节只列卡名与阶段归属，不再复制状态快照。
一句话概括（读数用本节末取数命令现场取）：40 张卡 done 10 / in_progress 3 / pending 27；P0 退出 8 条 pass 7，唯一红点是 X2（prod nginx 仍指 Python）。

### P0 平台底座 —— 14 张

`SPEC-1` spec 重排 + 进度机制 · `A0-1` 前端故障修复 · `A0-3` 鉴权与运行安全修复 · `FE-1` 前端结构重构 ·
`P0-0` 统一命令入口与可复现环境 · `P0-1` Go 服务骨架 · `P0-2` Schema 基线与收编 · `P0-3` Go 数据访问层 ·
`P0-4` 契约目录 · `P0-5` 跨语言契约测试骨架 + chain fixture · `P0-6` 认证垂直切片 · `P0-7` ai-core 内部执行面 ·
`P0-8` Go 接线与跨环境实跑 · `P0-9` P0 端到端演示。

### P1 门面接管 —— 9 张 / 80 h / 已完成 0

`P1-0` 反向代理 · `P1-1` 接管读接口 · `P1-2` 接管写接口 · `P1-3` 上传编排移 Go · `P1-4` 流式接管 ·
`P1-5` 前端基址切换 · `P1-6` 真实 E2E 骨架 · `P1-7` 12 条未调用接口审计 · `P1-8` 退出复核 —— **全部 pending（real/e2e）**。

### P2 数据面与学术能力 —— 10 张 / 114 h / 已完成 0

`P2-1` Chunk 真相层 · `P2-2` 公式索引接通 · `P2-3` chunk/公式链路测试 · `P2-4` 固定回归集 ·
`P2-5` 会话 append-only + 续传 · `P2-6` 预算与 usage 持久化 · `P2-7` 前端产品化 ·
`P2-8` 退出复核 · `P2-9` 论文自动抓取 · `P2-10` 主题分类与书架 —— **全部 pending（real/e2e）**。

### P3 自主研究引擎 —— 7 张 / 82 h / 已完成 0

`P3-1` research_* schema · `P3-2` Frontier 队列 · `P3-3` Worker Pool · `P3-4` Agent 接入 ai-core ·
`P3-5` 报告与 PARTIAL · `P3-6` 崩溃恢复 · `P3-7` 固定工作流基线 —— **全部 pending（real）**。

```powershell
# 取数（全 40 张逐条）
uv run python -c "import json;d=json.load(open('docs/progress.json',encoding='utf-8'));[print(t['id'],t['status'],t['requires'],t['evidence'],'|',t['title']) for p in d['phases'] for t in p['tasks']]"
```

---

## 7. 断层与待拍板（分工落地的真正卡点）

| # | 断层 | 现状 | 归属 |
| --- | --- | --- | --- |
| 1 | **入口**：Go 是唯一公开入口 | dev **已经过 Go**（vite→go-api:8080，未迁移前缀反代 Python）；prod nginx 仍 `upstream backend` 直指 Python、不经 Go | P0-8（X2 静态判 prod nginx，唯一红点） |
| 2 | **数据面**：Go 侧 schema 只建 12 张 | 18 张 ACL 表未建，Python 又在写其中几张 → **过渡期双 owner** | P2-1 / P3-1 |
| 3 | **调度权**：Go 唯一调度 | `go-worker` 只有探针，内部面 7 条**零 caller** | P3-1…P3-3 |
| 4 | **前端承载**：五个产品入口 | **已解决**——FE-1 引入 vue-router，五个入口有路由承载物（`13 §7`）；`NavKey` 现为路由名联合类型 | F-6 已交付 |
| 5 | **进度分母**：产品轴提案未登记 | `14 §18` 的 F-1…F-11（178 h，其中 F-6 已随 FE-1 交付）进不进分母未定 | 决策 **D5** |

**已列待决（用户侧）**：D4（V1 可信化 / P2-1+P2-2 是否前移）· D5（F-1…F-11 登记与否）·
D6（`alembic_version` 归属）· D8（Go 侧迁移由谁执行）· C28（存储拓扑：etcd 换 named volume 等）。

---

## 8. 与其他文档的分工（别重复）

| 想知道 | 看 |
| --- | --- |
| 现在代码长什么样（带 `file:line`） | [`13`](13-frontend-backend-architecture.md) |
| 目标态应该长什么样 | [`02`](02-target-architecture.md) |
| 某功能模块的现状 / 判据 / 顺序 | [`14`](14-feature-modules.md) |
| 进度唯一真相 | [`../progress.json`](../progress.json) |
| 前端结构规定（F/R 清单） | [`10`](10-frontend-structure.md) |
| 产品愿景与版本 | [`11`](11-product-vision.md) |
| **谁做什么 + 做到哪（本文）** | 本文件 |

> **维护规则**：§1–§2 在**分工变化**时改（改了要先回 `02`/`contracts/` 对齐）；§3–§6 在**被复核时**改，
> 且改前先重跑各节取数命令。**本文不增删卡片**——卡片只在 `progress.json` 里改。
