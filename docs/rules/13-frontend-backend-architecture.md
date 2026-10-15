# 13 — 前后端架构（As-Is 实测，以及与 To-Be 的差）

> **本文定位**：[02-target-architecture.md](02-target-architecture.md) 写的是**目标态**，本文写的是
> **今天代码里真实存在的形状**与两者的差。每条断言都带 `file:line`，取数命令附在各节末，可复跑。
> 与 [01-current-architecture.md](../reference/01-current-architecture.md) 的区别：那份是 2026-10-09 的 **dated 审计基线**
> （`AGENTS.md` §7 规定逐字保留、不作为实施依据），本文是**当前可复核的形状**。
> 功能模块层面的规划在 [14-feature-modules.md](14-feature-modules.md)，本文只给它的证据。

---

## 0. 一页拓扑

```
                     ┌── 开发形态（本机，2026-10-13 定案）──────────────────────────┐
浏览器 ──5173──▶ vite(dev server) ── /api 代理(ws:true) ──▶ go-api :8080          │
                     │              （vite.config.js:12-16；Go 是唯一公开入口）    │
                     └──────────────────────────────┬─────────────────────────────┘
                                                    ▼
   ┌ 应用层（一律源码跑，不进容器）────────────────────────────────┐
   │ go-api   :8080   server/cmd/api   原生 8 业务 + 4 探针；未迁移前缀反代 Python │
   │ go-worker:—      server/cmd/worker     只有探针，调度循环属 P3                │
   │ ai-core  :8000   backend/app.py        25 条对外 HTTP + 1 WS（绑 127.0.0.1）  │
   └──────────────────────────┬──────────────────────────────────────┘
                               ▼
   ┌ 中间件（只有这些在容器里，6 个；起时 healthy，C28：Milvus 会半路自挂）──┐
   │ postgres:5432  redis:6379  milvus:19530  etcd:2379            │
   │ minio→versitygw:9000（S3 语义）  attu:3001（Milvus 控制台）   │
   └───────────────────────────────────────────────────────────────┘

   ┌ 生产形态（docker-compose.prod.yml，全栈容器）────────────────┐
   │ 浏览器 → nginx :80 → /api/ → upstream go-api:8080              │
   │                              └ 未迁移面 → PYTHON_UPSTREAM=      │
   │                                http://backend:8000（compose 网络）│
   │         └ 静态 /、/assets/ → frontend/dist                     │
   │ ⚠️ 有 go-api（第十七轮，X2 转 pass）；**没有 go-worker**（属 P3）│
   └───────────────────────────────────────────────────────────────┘
```

**读法**：dev 形态下 Go **已经**是入口承载物（vite→go-api:8080，Go 把未迁移路径反代给 Python）；
prod 的 nginx 已切到 `upstream go-api`（`nginx/nginx.conf:20-24, 45, 56, 71, 74`，第十七轮），X2 因此转 pass；
`backend` 这个 upstream **故意保留**，它是 04 §5 要求的那条一行回退路径，不是死配置。

---

## 1. 运行形态（2026-10-13 定案）

| 层 | 形态 | 载体 |
| --- | --- | --- |
| 中间件 | **容器** | `scripts/dev.py infra` 起 postgres / redis / etcd / minio(versitygw) / milvus / attu |
| Go（go-api / go-worker） | **源码** | `cd server && go run ./cmd/api`（`go-worker` 同形） |
| Python（ai-core） | **源码** | `uv run python scripts/dev.py serve`（宿主 uvicorn，默认只绑 `127.0.0.1`；跑 chain/e2e 证据要 `--no-reload`） |
| 前端 | **源码** | `cd frontend && npm run dev`（vite，只监听 `::1`） |
| 生产 | 全栈容器 | `docker-compose.prod.yml` + `--env-file .env.production`（台账 C27） |

三条连带后果（都已写进 `AGENTS.md` §3/§4 与台账 C29）：
1. **X1 的判据不再看 `compose ps`**，改为「中间件容器 + 应用源码起进程，`/api/v1/health` 与 `/ready` 各 200」——它因此**不再证明编排层**。
2. **X2 的 R4 现在按形态分判**：prod 判「应用服务不发布宿主端口」（`nginx` 的 80 是唯一入口，不算违反），
   dev 由新加的 **R5** 判「compose 里不得出现应用服务」；源码形态下的端口隔离等价物是
   `dev.py serve --host` 默认 `127.0.0.1`（由 `tests/unit/test_dev_cli.py` 钉住，漂回 `0.0.0.0` 就红）。
3. 那个含 torch 的 **16.5 GB `backend` 镜像**只在部署才构建，已从 P0 阻塞清单移出（台账 C6 作废）。

---

## 2. 请求路径：今天实际怎么走 vs 目标

| 段 | 开发形态 | 生产形态 | 目标态（02 §2） |
| --- | --- | --- | --- |
| 入口 | vite `:5173` | nginx `:80` | nginx → `go-api` |
| `/api/*` 的去向 | **vite→go-api:8080**；Go 原生 8 条业务面，未迁移前缀反代到 Python:8000 | **`upstream go-api { server go-api:8080; }`** → Go 再把未迁移面转给 `backend:8000` | `upstream go-api`（已达） |
| 是否经 Go | **是**（vite 的 `/api` 代理指 go-api:8080） | **是**（nginx → go-api，Go 是唯一业务入口） | 是，唯一公开入口 |
| WS | `/api/v1/ws/chat`（vite `ws:true` 转发） | 同路径（`nginx.conf:45` + Upgrade） | 由 Go 终结或透传（P1-4） |
| `/internal/*` | 前端不可达（nginx 不转发） | 同左 | **必须仍然不可达**（R3） |

⚠️ **三条容易被忽略的事实**
- **dev 形态下"Go 是唯一公开入口"这条不变量已有承载物**：vite 的 `/api` 代理指向 go-api:8080（`vite.config.js:12-16`），
  Go 原生服务 8 条业务面、把未迁移前缀反代给 Python。而 X2 判的是 **prod 的 nginx**，
  它只能**静态**判配置文件文本——切了 upstream 不等于跑过全栈，`level` 留在 e2e 是诚实的。
- **prod compose 有 `go-api` 服务**（8 个服务：postgres/redis/etcd/minio/milvus/backend/go-api/nginx），
  它用 `server/Dockerfile` 构建、不发布宿主端口；`go-worker` 仍不在任何 compose 里（P3 才起调度）。
  dev compose 只有 6 个中间件服务，**应用服务已移除**（台账 C29 处置，由 R5 守着）。
- `check_nginx_routes.py` 对真仓库配置 **exit 0**（第十七轮，R1–R5 全过）。
  ⚠️ 这条 exit 0 只是 X2 的**必要条件**：运行中的 nginx 与配置一致要到 prod 实跑才证，而本机 P0 没起过全栈容器
  （16.5 GB 镜像 + 与仓库同盘的 I/O 代价），所以 X2 的证据等级是**静态配置级**，别读成"prod 已经跑通"。

---

## 3. Go 面（`server/`）

| 进程 | 实际挂载 | 位置 |
| --- | --- | --- |
| `cmd/api` | **4 条探针**：`/api/v1/health`、`/api/v1/ready`、`/health`、`/ready` | `internal/httpapi/router.go:50-55` |
| | **8 条业务**：`/api/v1/auth/register`、`/login`、`/me`、`/auth/password`、`/me/preferences`（GET/PUT）、`/sessions`（GET）、`/sessions/{id}`（DELETE） | `cmd/api/main.go`（`mountAuthRoutes` 挂 `:110-115`、`mountSessionRoutes` 挂 `:131-132`）；实现 `internal/auth/{service,handler,preferences}.go`、`internal/session/` |
| | 其中 `/auth/password`、`/me/preferences`（GET/PUT）**无 Python 对照**（Go 原生新面） | 同上 |
| | 未注册的 `/api/*`、`/internal/*`、`/ws/*`、`/metrics` → 反代到 `PYTHON_UPSTREAM`（默认 `127.0.0.1:8000`） | `internal/httpapi/upstream.go`、`router.go:60-64`（`Deps.Upstream`） |
| `cmd/worker` | 只有 `/health`、`/ready`；**无调度循环** | `cmd/worker/main.go:37-38`，自述 `:52`「调度器属 P3，本进程当前只提供探针」 |

⚠️ **Go 的 `/ready` 探测键只有 `database` + `redis`**（`cmd/api/main.go:223` 的 `RedisCheck`），**不含 `milvus`**；
Python 的 `/ready` 三键齐全（`database`/`redis`/`milvus`，`backend/api/health.py:128-133`），Milvus 挂时回 503。
两侧探测键集合不相等，是 X1 收口时刻意保留的差（Go 面不依赖 Milvus）。

`internal/` 六个包（无空目录）：`auth`（PBKDF2 / JWT / 注册登录 me / 改密码 / 偏好）、`config`（env 装载 + `ValidateAuth()` fail-fast）、
`db`（sqlc 生成物 + pgx 池）、`httpapi`（chi 组装、错误信封、中间件、探针、反代）、`observability`（slog + trace）、`session`（会话列表读 / 删）。

⚠️ **数据访问层的真实覆盖面**：sqlc 只对 **3 张表**生成了 SQL（**10 条命名查询**，分布在 3 个文件）——
`server/sql/queries/users.sql` 六条（`InsertUser:4`、`GetUserByUsername:15`、`GetUserByID:21`、`GetProfileByUsername:30`、
`UpdateUserPasswordByUsername:38`、`UpdateUserRoleByUsername:46`）、`server/sql/queries/user_preferences.sql` 两条
（`GetUserPreferences:4`、`UpsertUserPreferences:11`）、`server/sql/queries/chat_sessions.sql` 两条
（`ListSessionInfosForUser:7`、`DeleteSessionForUser:20`）。也就是 **Go 今天只读写 `users` / `user_preferences` / `chat_sessions` 三张表**；
`internal/db/models.go` 里其余表的 struct 只是声明，零查询（P0-3 把表字段生成进 model 是"看得见"，不等于"用得着"）。

```powershell
# 取数
Select-String -Path server/sql/queries/*.sql -Pattern '^-- name:'
Select-String -Path server/internal/db/models.go -Pattern '^type ' | Measure-Object
Select-String -Path server/internal/db/*.sql.go -Pattern 'FROM |INSERT INTO '
```

---

## 4. Python 面（`backend/`）——三分类实测

注册点：`backend/app.py:149-158`；`/api/v1` 前缀加在 `:152-156`（**注意 `:149` 的 health_router 不带前缀**）。

**A. 浏览器在用（13 条 HTTP + 1 WS）**

| 端点 | 位置 |
| --- | --- |
| `POST /auth/register` `/auth/login`、`GET /auth/me` | `backend/api/auth.py:34, 81, 99` |
| `GET /sessions`、`GET /sessions/{id}`、`DELETE /sessions/{id}` | `backend/api/sessions.py:21, 40, 54` |
| `POST /chat/stream`（SSE） | `backend/api/chat.py:53` |
| `GET /documents`、`POST /documents/upload/async`、`GET /documents/upload/jobs/{job_id}`、`DELETE /documents/delete/async/{filename}`、`GET /documents/delete/jobs/{job_id}` | `backend/api/documents.py:384, 410, 453, 543, 567` |
| `WS /api/v1/ws/chat` | `backend/api/ws.py:52` |

**B. 内部面（7 条，`/internal/v1/ai` 自带前缀，`backend/internal_api/router.py:32`）**
`/execute:120`、`POST /executions:133`、`GET /executions/{id}:145`、`/executions/{id}/result:153`、
`/executions/{id}/cancel:161`、`/healthz:169`、`/readyz:175`。
⚠️ **零生产调用方**——全仓 grep 只在 `tests/integration/test_ai_executions_internal_surface.py` 命中；
派发方（`go-worker`）还没有调度循环，所以这张"内部执行面"目前是**建好了等 caller**。

**C. 前端不调但仍可达（12 条）**
`POST /auth/refresh`(`auth.py:104`)、`POST /chat`(`chat.py:20`)、`POST /documents/upload`(`documents.py:468`)、
`GET /documents/upload/jobs`(`:461`)、`DELETE /documents/{filename}`(`:575`)、`POST /documents/ingest`(`:599`)、
`GET/DELETE /stats/usage`(`api/stats.py:15, 20`)、`POST /cache/clear`(`api/cache.py:15`)、
`GET /health` + `GET /ready`(`api/health.py:92, 121`，**根路径**，无 `/api/v1`)、`GET /metrics`(`app.py:150`)。

⚠️ 与目标态的差距就是这里：**「Python 只被动执行单次 AIExecution」尚未成立**——A + C 共 25 条对外/可用面
仍挂在 Python，其中 12 条属 P1-7 的"未调用接口审计 + Deprecation 头"清单。

---

## 5. 契约面一致性（`contracts/openapi.yaml`，21 个 operation）

`check_contracts.py` 今天 rc=0，但它校验的是**前端实调集合 ↔ 契约**与 `code` 枚举一致性，**不校验服务侧路由是否与契约一致**，
所以三条不一致是机检盲区（现查）：

| 契约声明 | Python 实际 | Go 实际 | 后果 |
| --- | --- | --- | --- |
| `GET /api/v1/health`（`openapi.yaml:430`）、`GET /api/v1/ready`（`:461`） | **只注册在根路径**（`app.py:149` + `api/health.py:92,121`） | 两条都有（`router.go:50-51`） | prod（nginx→Python）按契约调 `/api/v1/health` 是 404（Python 只有根 `/health`，即契约的 `healthRootAlias:447` / `readyRootAlias:484`）；dev 经 go-api 则两条都在，不 404 |
| `GET /metrics`（`openapi.yaml:501`） | 有（`app.py:150`） | **未原生实现**（Go 只把 `/metrics` 反代给 Python，`router.go:61`） | nginx 无对应 location、前端不调 → 三不管端点 |
| 请求体 schema（如 `RegisterRequest.role`） | `role: str \| None`，实测 `role:"root"` 返 200 | 照实现走 | 契约的 enum 是值域描述、不是入参校验（台账 C21） |

---

## 6. 数据面

### 6.1 PostgreSQL：ACL 声明的表 与 基线实建的表 是两个集合

```powershell
# 取数（本文所有表数都来自这条）
Select-String -Path contracts/table-acl.md -Pattern '^\| `' 
Select-String -Path server/migrations/*.up.sql -Pattern 'CREATE TABLE IF NOT EXISTS'
```

| 集合 | 数量 | 成员 |
| --- | --- | --- |
| 建表 SQL 合计数（`000001` + `000002` + `000003`） | **12** | `users`、`chat_sessions`、`chat_messages`、`parent_chunks`、`workspaces`、`workspace_members`、`paper_nodes`、`citation_edges`、`glossary_entries`、`alembic_version`、`ai_executions`、**`user_preferences`（000003，2026-10-14）** |
| ACL 声明（`contracts/table-acl.md`） | **25** | 上述 SQL 里实建的 7 张 + 下面 18 张 |
| **只在 ACL 里、SQL 里不存在**（纸面归属） | **18** | `papers`、`paper_versions`、`paper_files`、`paper_chunks`、`research_projects`、`research_runs`、`research_plans`、`research_tasks`、`research_task_dependencies`、`research_events`、`outbox_events`、`research_budget_usage`、`model_usage_records`、`knowledge_items`、`exploration_gaps`、`evidence_links`、`research_claims`、`report_sections` |
| **只在 SQL 里、ACL 未覆盖** | **5** | `parent_chunks`、`paper_nodes`、`citation_edges`、`glossary_entries`、`alembic_version`（归属问题即决策 **D6**） |

⚠️ 这条必须写明白：ACL 里那 18 张表的 `go: W` 是**计划归属**，不是现状——库里没有这些表，
所以任何"Go 独占写 X 表"的说法在 P2/P3 建表之前都不可执行。反向的 5 张则相反：**库里已经有表但 ACL 没管**，
其中 `parent_chunks` 是**活表**（11 处读写，见 §6.4），`paper_nodes`/`citation_edges`/`glossary_entries` 是死表。

⚠️ **两张新表（`ai_executions`/`user_preferences`）在真库里的状态不一样，别混说**：`user_preferences` 已于
2026-10-14 在 dev 库上实建（连跑两遍 `up.sql`，第二遍 `NOTICE relation already exists, skipping`，rc=0，表数 10→11→11），
并通过 Go 走完 PUT→GET→落库往返；`ai_executions` **至今没在任何长期库上建过**（只在临时库里验过幂等），
所以 dev 库距"12 张表齐全"还差 `000002` 那一步——这是 P0-7 的活，不是本条遗漏。

### 6.2 Milvus：可重建索引，字段就是能力的天花板

集合名默认 `embeddings_collection`（`backend/core/config/database.py:9`）。字段清单（`backend/vectordb/milvus_client.py:235-256`）：
`dense_embedding`、`sparse_embedding`、`text`（**`VARCHAR(2000)`，`:240`**）、`filename`、`file_type`、`file_path`、
`page_number`、`chunk_idx`、`chunk_id`、`parent_chunk_id`、`root_chunk_id`、`chunk_level`。

⚠️ **没有学术元数据列**（定理 / 公式 / 引文 / 术语 / `has_figure` / `has_table`）——
提取器产出的结构化信息在写入时就被丢弃，这是 14 §M5 那条链路断点的**位置**。
`text` 的 2000 截断则意味着：**正文真相不在这里**（P2-1 的立卡理由）。

### 6.3 Redis 与 S3

缓存键形如 `{REDIS_KEY_PREFIX}:{key}`（`backend/services/cache.py:240, 285`）；
上传/删除任务态**默认在进程内存**，`USE_REDIS_JOB_MANAGER=true` 才切 Redis（`backend/services/upload_jobs.py`，台账 C9）。
S3 侧：`minio` 这个 compose 服务名的实现已是 **versitygw v1.8.0**（决策 D9 / 台账 C24），
Milvus 已通过 S3 API 自建 `a-bucket`，对象级 PUT/GET/LIST/DELETE 已单独验过——**但 Milvus 的索引读写尚未验证**（空闲时不写对象）。

### 6.4 有 model 无读写的死表（4 张）

| 表 | model 位置 | 现状 |
| --- | --- | --- |
| `workspaces` | `backend/core/models.py:274` | 只在 `backend/schemas/schemas.py` 出现，**无 ORM 读写点** |
| `paper_nodes` | `:328` | 全仓零读写 |
| `citation_edges` | `:367` | 全仓零读写 |
| `glossary_extractor` 陷阱 | `:402`（`glossary_entries`） | 零 ORM 读写；`backend/rag/glossary_extractor.py:13` 的 `GlossaryEntry` 是**同名 `NamedTuple`**，不是 model——容易误判为"在用" |

活表对照：`users`（Python 50 处 + Go 真查询）、`chat_sessions`（`services/conversation_storage.py:67,72,149,187,226`）、
`chat_messages`（同文件 `:80,93,157,197`）、`parent_chunks`（`rag/parent_chunk_store.py:81,115,164,195,203`，上游 10 处调用在
`api/documents.py` 与 `rag/rag_utils.py:98`）、`workspace_members`（只读，`core/auth.py:428-431`）。

---

## 7. 前端架构（`frontend/`）

**已引入 vue-router**（`10 §7.1` 的选项 B）：`src/main.ts:29` 是 `createApp(App).use(i18n).use(router)`；
路由表 `src/router/index.ts` = 独立 `login` 页 + `AppShell` 外壳下 **13 条懒加载子路由**（chat / library / reader /
compare / gaps / graph / runs / lab / writing / radar / history / workspace / settings）。`src/composables/useNav.ts:5` 的
`type NavKey` 现在是**路由名的联合类型**（与路由表 `name` 同源），不再持有视图状态——视图状态已交给 vue-router。
`11 §3` 的五个产品入口因此**有了路由承载物**（`11 §8` 第 1 项"产品入口层作为一等概念"由此解开）。

**14 个视图文件里 9 个是 mock 页**（顶部有「示例数据」徽标 `SampleNotice` + 归属卡号，数据在 `src/mock/`、只用英文以过 R9）：

| 视图 | 组件（import 行实测） | 状态来源 | 真实 / mock |
| --- | --- | --- | --- |
| 登录 | `views/LoginView.vue:30` | `useAuth` / `useAppSession` / `usePreferences` | **真实**：`POST /auth/register`、`POST /auth/login`、`GET /auth/me` |
| 聊天 | `views/ChatView.vue:96` | `useChat` / `useWebSocket` | **真实**：`POST /chat/stream`（SSE）、`/api/v1/ws/chat?token=` |
| 历史 | `views/HistoryView.vue:47` | `useSessions` / `useChat` | **真实**：`GET /sessions`、`GET /sessions/{id}`、`DELETE /sessions/{id}` |
| 书架 | `views/LibraryView.vue:111` | `useDocuments` + `mock/library` | **混合**：文献页签真实（`GET /documents`、异步上传/删除、job 轮询）；主题群与抓取页签是 mock（P2-9/P2-10） |
| 设置 | `views/SettingsView.vue:31` | `useAuth` / `usePreferences` | **真实**：5 个板块组件（账号 / 主题 / 偏好 / 改密码 + 仅管理员的知识库管理，后者消费 `useDocuments`） |
| 比较矩阵 / 问题与假设 / 知识双图 / 文献雷达 / 研究实验室 / 深读 / 自主运行 / 报告写作 / 工作区 | `views/{Compare,Gaps,Graph,Radar,Lab,Reader,Runs,Writing,Workspace}View.vue` | `mock/{analysis,library,program}` | **mock**：归属依次 F-1 / F-2 / F-8 / F-4 / F-3 / P2-7·Z3 / P3-1…P3-7 / P3-5·F-5 / F-7 |

分层与约束（由 `scripts/check_frontend.py` 的 R1–R11 机器执行，FE-1 done）：
`api/` 7 个模块是唯一请求出口——`client.ts`（路径字面量的唯一所在地，全部 `/api/v1` 前缀）、
`http.ts`（fetch + XHR 出口，`BASE` 在 `:8`）、`sse.ts`、`ws.ts`、`token.ts`（单一 token 所有者）、`events.ts`、`types.ts`；
状态层无 pinia，用 `composables/` 的模块顶层 ref 做单例；DOM/对话框外移 `utils/`（`theme.ts` 写 `data-theme`，`dialog.ts` 是唯一接缝）。
⚠️ 前端**未接 refresh 流程**：`/auth/refresh` 后端存在但没人调（`api/client.ts` 不含该端点），60 分钟到期需重登。

```powershell
# 取数
uv run python scripts/check_frontend.py         # R1–R11
cd frontend; npm run typecheck                  # vue-tsc --noEmit
Select-String -Path frontend/src/api/*.ts,frontend/src/composables/*.ts -Pattern '/api/v1'
```

---

## 8. 横切面归属（谁今天实现、谁将接管、拿什么判）

| 关注面 | 今天的实现 | 目标归属 | 判据 |
| --- | --- | --- | --- |
| 认证（PBKDF2 校验 / JWT） | Python 裁判；Go 已实现且被 golden vectors 钉住（`contracts/pbkdf2_golden.json` 10 条、`jwt_golden.json` 9 条） | Go | X4 **pass**（chain 15 项双向互验）、X5 **pass** |
| trace_id | Go `observability`；Python 侧透传 | Go 生成 | P1-0 |
| 错误信封 | Go `httpapi` 已照抄生产侧文案（含 `Internal server error` 小写 s，台账 C23） | Go | Y3（SSE 字节级比对属 P1） |
| 限流 | Python `RATE_LIMIT` 真生效（slowapi） | 迁移待定 | ⚠️ **C33**：Go 侧没有任何限流层，接管一条路由就静默丢掉它的限流；登录/注册已丢，接管批次要带上限流 |
| 流式 | Python SSE（`chat.py:66` 逐 chunk yield，但**整段答案一次性下发**，非 token 级） | Go 门面 | P1-4 + P2-5（Last-Event-ID 续传） |
| 任务态 | 进程内存（`upload_jobs`，台账 C9） | Go + PG | Z4 |
| 预算 / usage 记账 | `/stats/usage` 前端不调 | Go | P2-6 |
| 入口路由 | dev：vite→go-api→Python（Go 已是承载物）；prod：nginx 单指 Python | nginx → go-api | X2（静态判 prod nginx，如实 exit 1） |

---

## 9. 死代码 / 纸面归属总清单（14 的输入）

| 项 | 位置 | 性质 |
| --- | --- | --- |
| 多模态图表检索 | `backend/rag/multimodal.py` | 模块 + 单测都在，**零调用方** |
| 公式索引**入库侧** | `backend/rag/rag_utils.py:644 _build_formula_index` | 查询侧已接（`:730`），**建索引函数零调用点** → LSH 恒空 |
| 学术元数据入检索层 | `backend/vectordb/milvus_writer.py` 写入字段 | 提取器都接在分块期，但**Milvus schema 无对应列** → 入库即丢弃 |
| 4 张死表 | §6.4 | 有 model 无读写 |
| 12 条前端不调的端点 | §4-C | 对外可达但无 caller（P1-7 逐条审计 + Deprecation 头） |
| `go-worker` | `cmd/worker/main.go:52` | 只有探针，无调度循环（P3-3） |
| 18 张 ACL 纸面表 | §6.1 | 归属已写、表未建（P2 / P3 各卡片的建表清单） |

---

## 10. 维护规则

- **本文只在"代码事实"变化时更新**；目标态变化改 `02`，卡片与工时改 `docs/progress.json`，缺陷处置改 `12`。
- 每节末的取数命令是本文的**可复核性**所在；改数字前先重跑命令，别手抄。
- 与 `01`（dated 审计）冲突时以本文为准；与 `02`（目标态）冲突时说明是差、不是错。
