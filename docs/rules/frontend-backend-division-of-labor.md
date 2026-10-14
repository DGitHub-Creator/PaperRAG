# 前后端分工与进度记录（前端 / Go / Python 三方归属 · 一页看清谁做什么、做到哪）

> **本文补的是什么**：`13` 写 As-Is 架构、`14` 写功能模块规划、`progress.json` 写进度，但**没有一份文档把「同一件事，
> 前端 / Go / Python 各占哪一段」和「这一段现在做到哪」并排放在一张表里**。本文就是这张表。
>
> **性质**：§1–§2 的**分工**是常青判断（依据 `02` To-Be 与 `13` As-Is，短期不变）；§3–§6 的**进度**是
> **dated 快照（2026-10-14）**，唯一真相始终是 [`../progress.json`](../progress.json)，本文只在被复核时更新。
>
> **三条口径纪律**：
> 1. **未实现一律标「未实现」**并指向卡片号，不写成既成事实（`08` 原则②）。
> 2. **每张数字表都附取数命令**，改数字前先重跑，别手抄（与 `13 §10` 同口径）。
> 3. **「纸面归属」与「代码现状」分开写**：`contracts/table-acl.md` 里的 `go: W` 在表建出来之前是计划，不是现状（台账 C30）。

---

## 0. 一页总览

### 0.1 运行形态（开发路径，2026-10-13 定案：容器只跑中间件）

```
浏览器 ──5173──▶ vite(dev)  ── /api 代理 ──▶  127.0.0.1:8000 (ai-core / Python)
                                                  ▲
                                      目标态还要先过 go-api:8080（今天没承载物）
```

| 层 | 载体 | 形态 | 今天的能力 |
| --- | --- | --- | --- |
| 前端 | `frontend/`（Vue 3 + Vite + TS） | 源码 | 4 个视图：登录 / 聊天 / 历史 / 设置(文档管理) |
| Go | `server/cmd/{api,worker}` | 源码 | api：探针 + **3 条认证路由**；worker：**只有探针** |
| Python | `backend/app.py`（ai-core） | 源码 | **25 条对外面 + 7 条内部面 + 全部 RAG/Agent 逻辑** |
| 中间件 | postgres / redis / etcd / minio(versitygw) / milvus / attu | **容器** | 六容器 |

### 0.2 一句话分工律

> **Go 管「谁在什么时候调用谁」**（入口 / 调度 / 状态 / 真相）；**Python 管「一次调用内部算什么」**（解析 / 检索 / embedding / LLM）；**前端只管「消费与展示」**。

这条律的硬边界只有一条：**全局调度器只能有一个，归 Go**（`AGENTS.md` §7；Python 不得再起循环）。

### 0.3 进度一句话（快照，2026-10-14）

**后端工程进度 14.7%（58/394 h）**，且这 58 h **100% 落在 P0 平台底座**——而 P0 按口径**不产出用户可见能力**。
P1 / P2 / P3 **一张未完成**。真正能跑的只有两条：**Python 的单论文 RAG 问答**（M4/M6）与 **Go 的认证三条路由**（X5 pass）。

```powershell
# 取数（本页所有进度数字都来自这两条）
uv run python -c "import json;d=json.load(open('docs/progress.json',encoding='utf-8'));[print(p['id'],len(p['tasks']),sum(t['hours'] for t in p['tasks']),sum(t['hours'] for t in p['tasks'] if t['status']=='done')) for p in d['phases']]"
uv run python -m pytest -q          # 测试基线（现状现场取，别抄文档）
```

---

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

### 2.2 现状：24 张 ACL 表 vs 11 张实建表（差集）

| 集合 | 数量 | 说明 |
| --- | --- | --- |
| 基线实建（`000001` + `000002`） | **11** | `users` `chat_sessions` `chat_messages` `parent_chunks` `workspaces` `workspace_members` `paper_nodes` `citation_edges` `glossary_entries` `alembic_version` `ai_executions` |
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
| **FE-1** | **done** | mock | 结构重构：唯一请求出口 `api/` + 模块单例状态层 + R1–R11 机检 |
| P1-5 | pending | e2e | 基址切换 + nginx 收口（业务 API 退出 Python） |
| P2-7 | pending | e2e | 产品化：Monitor / Paper Reader / 引用回溯视图 |

### 3.2 现状（36 个源文件，28 个被 R1–R11 机检）

| 视图 | 组件 | 调用端点（实测） |
| --- | --- | --- |
| 登录 | `components/AuthPanel.vue` | `POST /auth/register` `/auth/login`、`GET /auth/me` |
| 聊天 | `components/ChatView.vue` | `POST /chat/stream`（SSE）、`WS /api/v1/ws/chat` |
| 历史 | `components/HistorySidebar.vue` | `GET /sessions` `GET/DELETE /sessions/{id}` |
| 设置（文档） | `components/SettingsView.vue` | `GET /documents`、`POST /documents/upload/async`、job 轮询、`DELETE /documents/delete/async/{fn}` |

分层：`components → composables → api → (browser)` 单向；`api/` 7 模块是唯一请求出口（`client.ts` 是路径字面量唯一所在地、`http.ts` 是唯 fetch/XHR 出口、`token.ts` 是唯一 token 所有者）。

### 3.3 三条真实缺口

1. **无 vue-router**：`main.ts` 只 `use(i18n)`；视图靠 `useNav.ts` 的三值枚举 `NavKey = "newChat" | "history" | "settings"` + `App.vue` 的 `v-if` 手选。
   → 这是结构性缺口：`11 §3` 的**五个产品入口（Deep Reader / 书架 / 工作区 / 报告 / 设置）没有路由承载物**，
   所以「加书架 / 矩阵 / 看板」不是画组件，而是**先决定引入 router 还是扩 NavKey**（`10 §7` 的待拍板项 A/B）。
2. **无 e2e 判据**：`package.json` 只有 `dev/build/preview/typecheck`，**没有 `test:e2e`**；FE-f（浏览器真跑）归 P0-9。
3. **未接 refresh**：`/auth/refresh` 后端存在但前端没人调，60 分钟到期需重登。

```powershell
# 取数
uv run python scripts/check_frontend.py         # R1–R11，现状 rc=0（28 源文件全过）
cd frontend; npm run typecheck                  # vue-tsc --noEmit
```

---

## 4. Go 侧：进度与覆盖

### 4.1 进程与路由（实测）

| 进程 | 实际挂载 | 位置 |
| --- | --- | --- |
| `cmd/api` | `/api/v1/health` `/ready`、`/health` `/ready` | `internal/httpapi/router.go:45-50` |
| | `/api/v1/auth/register` `/login` `/me`（**仅此 3 条业务路由**） | `cmd/api/main.go:96-98` |
| `cmd/worker` | 只有 `/health` `/ready`；**无调度循环** | `cmd/worker/main.go:37-38`，自述 `:52`「调度器属 P3」 |

`internal/` 五个包（25 个 `.go` 文件）：`auth`（PBKDF2 / JWT / 注册登录 me）、`config`（env + `ValidateAuth()` fail-fast）、
`db`（sqlc 生成物 + pgx 池）、`httpapi`（chi 组装、错误信封、中间件、探针）、`observability`（slog + trace）。

### 4.2 数据访问的真实覆盖面

⚠️ **sqlc 只对 `users` 生成了 SQL**——`server/sql/queries/users.sql` 四条（`InsertUser` `GetUserByUsername` `GetUserByID` `GetProfileByUsername`）。
`internal/db/models.go` 里**其余 10 张表的 struct 只是声明、零查询**（"生成进 model" ≠ "用得着"）。

### 4.3 卡片

| 卡片 | 状态 | 等级 |
| --- | --- | --- |
| P0-1 Go 服务骨架 | in_progress | mock（real 缺口：未进 compose、未与 Python 联调） |
| P0-3 Go 数据访问层（sqlc） | done | mock |
| P0-4 契约目录 | done | mock |
| P0-6 认证垂直切片 | in_progress | mock（X5 **pass**，real 档待 `--from-db`） |
| P0-7 ai-core 内部执行面 | in_progress | mock |
| P0-8 Go 接线与跨环境实跑 | pending | none |
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

⚠️ 目标态那句「**Python 只被动执行单次 `AIExecution`**」**今天不成立**：A+C 共 **25 条面仍挂在 Python**。

RAG/Agent 主体（`backend/rag/*` 13 文件、`backend/agent/*`、`backend/vectordb/*`、`backend/services/*`）是**在产的唯一端到端能力**（M4/M6）。

```powershell
# 取数
Select-String -Path backend/app.py -Pattern 'include_router|APIRouter'
Select-String -Path backend/**/*.py -Pattern '@router\.(get|post|delete|put)'
```

---

## 6. 卡片进度记录（全 40 张，按阶段）

快照 2026-10-14。`req/ev` = 要求 / 已有证据等级。

### P0 平台底座 —— 14 张 / 118 h / 已完成 58 h

| 卡片 | 状态 | req/ev |
| --- | --- | --- |
| SPEC-1 spec 重排 + 进度机制 | done | mock/mock |
| A0-1 前端故障修复 | done | mock/mock |
| A0-3 鉴权与运行安全修复 | done | mock/mock |
| FE-1 前端结构重构 | done | mock/mock |
| P0-0 统一命令入口与可复现环境 | done | real/real |
| P0-2 Schema 基线与收编 | done | real/real |
| P0-3 Go 数据访问层 | done | mock/mock |
| P0-4 契约目录 | done | mock/mock |
| P0-1 Go 服务骨架 | in_progress | real/mock |
| P0-6 认证垂直切片 | in_progress | real/mock |
| P0-7 ai-core 内部执行面 | in_progress | real/mock |
| P0-5 跨语言契约测试骨架 | pending | real/none |
| P0-8 Go 接线与跨环境实跑 | pending | real/none |
| P0-9 P0 端到端演示 | pending | e2e/none |

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
| 1 | **入口**：Go 是唯一公开入口 | dev vite 直连 Python:8000、prod nginx `upstream backend`——**两条路径都不经 Go** | P0-8（X2 只能静态判 nginx） |
| 2 | **数据面**：Go 侧 schema 只建 11 张 | 18 张 ACL 表未建，Python 又在写其中几张 → **过渡期双 owner** | P2-1 / P3-1 |
| 3 | **调度权**：Go 唯一调度 | `go-worker` 只有探针，内部面 7 条**零 caller** | P3-1…P3-3 |
| 4 | **前端承载**：五个产品入口 | 无 router，`NavKey` 里没有入口概念 | 待拍板（`10 §7` 选项 A/B）+ 提案 F-6 |
| 5 | **进度分母**：产品轴提案未登记 | `14 §18` 的 F-1…F-11（178 h）进不进分母未定 | 决策 **D5** |

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
