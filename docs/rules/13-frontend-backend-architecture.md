# 13 — 前后端架构（As-Is 实测，以及与 To-Be 的差）

> **本文定位**：[02-target-architecture.md](02-target-architecture.md) 写的是**目标态**，本文写的是
> **今天代码里真实存在的形状**与两者的差。每条断言都带 `file:line`，取数命令附在各节末，可复跑。
> 与 [01-current-architecture.md](../reference/01-current-architecture.md) 的区别：那份是 2026-10-09 的 **dated 审计基线**
> （`AGENTS.md` §7 规定逐字保留、不作为实施依据），本文是**当前可复核的形状**。
> 功能模块层面的规划在 [14-feature-modules.md](14-feature-modules.md)，本文只给它的证据。

---

## 0. 一页拓扑

```
                     ┌── 开发形态（本机，2026-10-13 定案）────────────────────────┐
浏览器 ──5173──▶ vite(dev server)                                                 │
                     │  /api 代理 → 127.0.0.1:8000（vite.config.js:8-14, ws:true）│
                     └──────────────────┬────────────────────────────────────────┘
                                        ▼
   ┌ 应用层（一律源码跑，不进容器）────────────────────────────────┐
   │ go-api   :8080   server/cmd/api        今天只有探针 + 3 条认证路由 │
   │ go-worker:—      server/cmd/worker     只有探针，调度循环属 P3    │
   │ ai-core  :8000   backend/app.py        25 条浏览器面 HTTP + 1 WS  │
   └──────────────────────────┬──────────────────────────────────────┘
                               ▼
   ┌ 中间件（只有这些在容器里，6 个，全 healthy）─────────────────┐
   │ postgres:5432  redis:6379  milvus:19530  etcd:2379            │
   │ minio→versitygw:9000（S3 语义）  attu:3001（Milvus 控制台）   │
   └───────────────────────────────────────────────────────────────┘

   ┌ 生产形态（docker-compose.prod.yml，仍是全栈容器）────────────┐
   │ 浏览器 → nginx → /api/ → upstream backend:8000（ai-core）      │
   │         └ 静态 /、/assets/ → frontend/dist                     │
   │ ⚠️ 这份里同样没有 go-api / go-worker                            │
   └───────────────────────────────────────────────────────────────┘
```

**读法**：虚线以上的"唯一公开入口 = Go"是**目标**；今天两条路径的流量都直接落在 Python 上。
这不是实现偷懒，而是 X2/P0-8 尚未开工——但**别把本文的拓扑当成已完成的架构**。

---

## 1. 运行形态（2026-10-13 定案）

| 层 | 形态 | 载体 |
| --- | --- | --- |
| 中间件 | **容器** | `scripts/dev.py infra` 起 postgres / redis / etcd / minio(versitygw) / milvus / attu |
| Go（go-api / go-worker） | **源码** | `cd server && go run ./cmd/api`（`go-worker` 同形） |
| Python（ai-core） | **源码** | `uv run python scripts/dev.py serve`（宿主 uvicorn --reload） |
| 前端 | **源码** | `cd frontend && npm run dev`（vite，只监听 `::1`） |
| 生产 | 全栈容器 | `docker-compose.prod.yml` + `--env-file .env.production`（台账 C27） |

三条连带后果（都已写进 `AGENTS.md` §3/§4 与台账 C29）：
1. **X1 的判据不再看 `compose ps`**，改为「中间件容器 + 应用源码起进程，`/api/v1/health` 与 `/ready` 各 200」——它因此**不再证明编排层**。
2. **X2 的 R4**（compose 里 `ai-core` 不发布宿主端口）在 dev 形态下无物可判，等价口径是「只绑 `127.0.0.1`」。
3. 那个含 torch 的 **16.5 GB `backend` 镜像**只在部署才构建，已从 P0 阻塞清单移出（台账 C6 作废）。

---

## 2. 请求路径：今天实际怎么走 vs 目标

| 段 | 开发形态 | 生产形态 | 目标态（02 §2） |
| --- | --- | --- | --- |
| 入口 | vite `:5173` | nginx `:80` | nginx → `go-api` |
| `/api/*` 的去向 | **直连 `127.0.0.1:8000`（Python）** | **`upstream backend { server backend:8000; }`**（`nginx/nginx.conf:20-22, 34`） | `upstream go-api` |
| 是否经 Go | **否** | **否** | 是，唯一公开入口 |
| WS | `/api/v1/ws/chat`（vite `ws:true` 转发） | 同路径（`nginx.conf:45` + Upgrade） | 由 Go 终结或透传（P1-4） |
| `/internal/*` | 前端不可达（nginx 不转发） | 同左 | **必须仍然不可达**（R3） |

⚠️ **三条容易被忽略的事实**
- **dev 形态下"Go 是唯一公开入口"这条不变量在运行时没有承载物**：vite 把 `/api` 直接转给 ai-core:8000。
  所以 X2 只能**静态**判 `nginx/nginx.conf` + compose 文本，`level` 留在 e2e 是诚实的，不是脚本缺陷。
- 两份 compose **都没有 `go-api` / `go-worker` 服务**（`docker-compose.yml` 与 `docker-compose.prod.yml` 的服务清单实测）。
- `check_nginx_routes.py` 今天对真仓库配置如实 **exit 1**（R1：`/api/` 还指向 Python），这条红是 P0-8 的活。

---

## 3. Go 面（`server/`）

| 进程 | 实际挂载 | 位置 |
| --- | --- | --- |
| `cmd/api` | `/api/v1/health`、`/api/v1/ready`、`/health`、`/ready` | `internal/httpapi/router.go:45-50` |
| | `/api/v1/auth/register`、`/login`、`/me` | `cmd/api/main.go`（`mountAuthRoutes`） |
| | `/api/v1/auth/password`、`/api/v1/me/preferences`（GET/PUT）（2026-10-14 新增，**无 Python 对照**） | `cmd/api/main.go`（`mountAuthRoutes`）；实现 `internal/auth/{service,handler,preferences}.go` |
| | 未注册的 `/api/*`、`/internal/*`、`/ws/*`、`/metrics` → 反代到 `PYTHON_UPSTREAM` | `internal/httpapi/upstream.go`、`router.go` 的 `Deps.Upstream` |
| `cmd/worker` | 只有 `/health`、`/ready`；**无调度循环** | `cmd/worker/main.go:37-38`，自述 `:52`「调度器属 P3，本进程当前只提供探针」 |

`internal/` 五个包（无空目录）：`auth`（PBKDF2 / JWT / 注册登录 me）、`config`（env 装载 + `ValidateAuth()` fail-fast）、
`db`（sqlc 生成物 + pgx 池）、`httpapi`（chi 组装、错误信封、中间件、探针）、`observability`（slog + trace）。

⚠️ **数据访问层的真实覆盖面**：sqlc 只对 **2 张表**生成了 SQL——`server/sql/queries/users.sql` 六条
（`InsertUser:4`、`GetUserByUsername:15`、`GetUserByID:21`、`GetProfileByUsername:30`、
`UpdateUserPasswordByUsername:38`、`UpdateUserRoleByUsername:46`）与 `server/sql/queries/user_preferences.sql` 两条
（`GetUserPreferences:4`、`UpsertUserPreferences:11`，2026-10-14 随迁移 000003 新增）。
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

## 5. 契约面一致性（`contracts/openapi.yaml`，18 个 operation）

`check_contracts.py` 今天 rc=0，但它校验的是**前端实调集合 ↔ 契约**与 `code` 枚举一致性，**不校验服务侧路由是否与契约一致**，
所以三条不一致是机检盲区（现查）：

| 契约声明 | Python 实际 | Go 实际 | 后果 |
| --- | --- | --- | --- |
| `GET /api/v1/health`（`openapi.yaml:356`）、`GET /api/v1/ready`（`:387`） | **只注册在根路径**（`app.py:149` + `api/health.py:92,121`） | 两条都有（`router.go:45-46`） | 前端若按契约调 `/api/v1/health`，在今天的 dev/prod 路径上都是 404；契约的根路径别名 `healthRootAlias:370` / `readyRootAlias:407` 才是 Python 满足的那两条 |
| `GET /metrics`（`openapi.yaml:427`） | 有（`app.py:150`） | **未实现** | nginx 无对应 location、前端不调 → 三不管端点 |
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

⚠️ **没有 vue-router**：`src/main.ts:16-28` 只 `createApp(App).use(i18n)`；没有 `router/`、没有 `views/`。
视图切换靠枚举 ref——`src/composables/useNav.ts:4-7` 的 `type NavKey = "newChat" | "history" | "settings"`，
在 `src/App.vue:16-26` 用 `v-if / v-else-if` 手选组件。

**这条技术事实有产品后果**：`11 §3` 的五个产品入口（Deep Reader / 书架 / 工作区 / 报告 / 设置）**没有路由承载物**，
`11 §8` 第 1 项"产品入口层作为一等概念"之所以是缺口，根子在这里。要加入口，先决定引入 router 还是扩 NavKey——
这是个架构选择，不是体力活。

| 视图 | 组件 | 状态来源 | 调用端点（实测） |
| --- | --- | --- | --- |
| 登录 | `components/AuthPanel.vue:35` | `composables/useAuth.ts:7-8` | `POST /auth/register`(`:49`)、`POST /auth/login`(`:48`)、`GET /auth/me`(`:40`) |
| 聊天 | `components/ChatView.vue:78` | `composables/useChat.ts:19-23` | `POST /chat/stream`（SSE，`useChat.ts:126`）、`/api/v1/ws/chat?token=`（`api/ws.ts:6-9`） |
| 历史 | `components/HistorySidebar.vue` | `composables/useSessions.ts:6` | `GET /sessions`(`:10`)、`GET /sessions/{id}`(`:15`)、`DELETE /sessions/{id}`(`:19`) |
| 设置（文档管理） | `components/SettingsView.vue:106` | `composables/useDocuments.ts:33-45` | `GET /documents`(`:110`)、`POST /documents/upload/async`(`:160`)、`GET /documents/upload/jobs/{id}`(`:129`)、`DELETE /documents/delete/async/{fn}`(`:215`)、`GET /documents/delete/jobs/{id}`(`:175`) |

分层与约束（由 `scripts/check_frontend.py` 的 R1–R11 机器执行，FE-1 done）：
`api/` 7 个模块是唯一请求出口——`client.ts`（路径字面量的唯一所在地，全部 `/api/v1` 前缀）、
`http.ts`（fetch + XHR 出口，`BASE` 在 `:8`）、`sse.ts`、`ws.ts`、`token.ts`（单一 token 所有者）、`events.ts`、`types.ts`；
状态层无 pinia，用 `composables/` 的模块顶层 ref 做单例。
⚠️ 前端**未接 refresh 流程**：`/auth/refresh` 后端存在但没人调，60 分钟到期需重登。

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
| 认证（PBKDF2 校验 / JWT） | Python 裁判；Go 已实现且被 golden vectors 钉住（`contracts/pbkdf2_golden.json` 10 条、`jwt_golden.json` 9 条） | Go | X4（chain 半侧待 P0-5）、X5 **pass** |
| trace_id | Go `observability`；Python 侧透传 | Go 生成 | P1-0 |
| 错误信封 | Go `httpapi` 已照抄生产侧文案（含 `Internal server error` 小写 s，台账 C23） | Go | Y3（SSE 字节级比对属 P1） |
| 限流 | Python `RATE_LIMIT` 真生效 | 迁移待定 | — |
| 流式 | Python SSE（`chat.py:66` 逐 chunk yield，但**整段答案一次性下发**，非 token 级） | Go 门面 | P1-4 + P2-5（Last-Event-ID 续传） |
| 任务态 | 进程内存（`upload_jobs`，台账 C9） | Go + PG | Z4 |
| 预算 / usage 记账 | `/stats/usage` 前端不调 | Go | P2-6 |
| 入口路由 | nginx 单指 Python | nginx → go-api | X2（静态判据，如实 exit 1） |

---

## 9. 死代码 / 纸面归属总清单（14 的输入）

| 项 | 位置 | 性质 |
| --- | --- | --- |
| 多模态图表检索 | `backend/rag/multimodal.py` | 模块 + 单测都在，**零调用方** |
| 公式索引**入库侧** | `backend/rag/rag_utils.py:644 _build_formula_index` | 查询侧已接（`:730`），**建索引函数零调用点** → LSH 恒空 |
| 学术元数据入检索层 | `backend/vectordb/milvus_writer.py` 写入字段 | 提取器都接在分块期，但**Milvus schema 无对应列** → 入库即丢弃 |
| 4 张死表 | §6.4 | 有 model 无读写 |
| 8 条前端不调的端点 | §4-C | 对外可达但无 caller（P1-7 逐条审计 + Deprecation 头） |
| `go-worker` | `cmd/worker/main.go:52` | 只有探针，无调度循环（P3-3） |
| 18 张 ACL 纸面表 | §6.1 | 归属已写、表未建（P2 / P3 各卡片的建表清单） |

---

## 10. 维护规则

- **本文只在"代码事实"变化时更新**；目标态变化改 `02`，卡片与工时改 `docs/progress.json`，缺陷处置改 `12`。
- 每节末的取数命令是本文的**可复核性**所在；改数字前先重跑命令，别手抄。
- 与 `01`（dated 审计）冲突时以本文为准；与 `02`（目标态）冲突时说明是差、不是错。
