# 00 — Phase 0 代码审计

> **本文状态（2026-10-09 复核）**：性质=**事实**（审计基线 `main @ c55129e`，逐文件读源码 + grep 调用点验证）。里程碑口径一律用 **P0–P3**；旧 `Milestone A/B/C`、`A0-x` 的对应关系见 [04 §0/§3](04-migration.md)。结论仍然有效；文中提到的修复去向已按 04 §0 重映射，已落地的部分（A0-1 `2c3e583`、A0-3 `d8f1563`、FE-1、P0-4、P0-7）见 [../progress.json](../progress.json)。

> 依据 [plan-v2.0-researchpilot.md](../archive/refactor-plan-v2.0-researchpilot.md) §2 要求产出（该计划已归档，见 [../archive/README.md](../archive/README.md)）。
> 审计对象：`main @ c55129e`（2026-10-09）。方法：逐文件读源码 + grep 调用点验证，**所有结论以代码为第一依据，文档声明不作为事实**。
> 标注约定：`[V]` = 本次已用调用点/实跑验证；`[U]` = 未验证，需后续确认。

---

## 1. 规模与基线

| 项 | 实测 |
| --- | --- |
| 后端 Python | 11,041 行 / 62 个模块 |
| 前端 | 2,820 行（Vue 3 SFC + TS composable），无 UI 测试 |
| 测试 | `tests/` 41 个文件，pytest（asyncio=auto，strict-markers） |
| 依赖 | `pyproject.toml` 40 项；`uv.lock` 1.0MB |
| 数据库迁移 | 3 个 alembic 版本，线性无分叉，head=`add_paper_knowledge_graph` |
| `.env` | **不存在**（仅 `.env.example` / `.env.production.example`）→ 仓库当前状态无法直接启动 |

**基线命令与结果**（Phase 0 §2.3 要求"记录既有测试结果与已知失败，不允许假设旧项目完全正常"）：

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 依赖同步 | `uv sync` | 成功，169 包（注：`pytest` 不在默认依赖里，需 `--extra test`）[V] |
| Python 测试 | `uv run --extra test pytest -q` | **280 passed, 44 warnings, 52.26s，exit 0** [V] |
| 前端类型 | `npm install && npm run typecheck` | **6 项 error，exit 2**（详见 §1.1）[V] |
| 前端构建 | `npm run build` | **成功**（exit 0，产物 `dist/assets/index-*.js`）[V] —— `vite build` 不跑 `vue-tsc`，因此 §1.1 的 6 项类型错误与 `apiFetch` 未定义**不会阻断构建**，只会在浏览器运行时爆掉。这正是"绿灯掩盖故障"的机制。 |
| 端到端 8 项流程（上传/向量化/检索/Rerank/生成/SSE/权限/DB） | — | **未跑**：无 `.env`、无 LLM key、基础设施未起。见 Q1 |

测试告警中值得记录的两条（均为后续 spec 要处理的真实隐患）：`conversation_storage.py:85` 的 `datetime.utcnow()` 已被标 deprecated；`services/tools.py:119` 触发 `There is no current event loop`。

### 1.1 基线失败项（已确认，与"280 项全绿"提交信息不符的风险点）

`c55129e` 提交信息称"测试套件 280 项 29s 全绿"。审计发现**测试通过 ≠ 功能可用**：测试大量 mock 掉 langgraph / sentence_transformers / Milvus（见 `4a5e806` "mock langgraph/sentence_transformers"），因此以下真实缺陷不会被任何测试捕获。

**前端两处必现运行时故障**：

1. `frontend/src/composables/useAuth.ts:2` 只导入 `authFetch`，但 `:34`、`:45` 调用 `apiFetch` → 登录与注册在浏览器中抛 `ReferenceError`。[V] **已由 `npm run typecheck` 复现**：
   - `src/composables/useAuth.ts(34,23): error TS2304: Cannot find name 'apiFetch'.`
   - `src/composables/useAuth.ts(45,23): error TS2304: Cannot find name 'apiFetch'.`
   - 另有 4 项 `CitationChips.vue(2,40)(2,64)(7,39)(16,44): error TS18048: 'citations'/'unsupported' is possibly 'undefined'`
   - 合计 6 error / exit 2。即 **`npm run typecheck` 在当前主干上是红的**，而 `pyproject` 的 `fail_under=40` 与 CI 只跑 Python 侧（`.github/workflows/ci.yml`），前端类型检查不在门禁内。[V]
2. `frontend/src/composables/useDocuments.ts:143` `xhr.open("POST", "/documents/upload/async")` **缺 `/api/v1` 前缀**，与 `services/api.ts:1-3` 的"所有调用必须经过 BASE"约定矛盾；dev 只有 `/api` 被代理，prod nginx 该路径落到静态层 → 异步上传按钮实际打不通。[V]（typecheck 抓不到，属纯运行时缺陷：路径是字符串字面量）

> **对 V2.0 计划的直接影响**：**P1** 的验收标准（旧称里程碑 A）是"原有论文问答功能保持可用"。以上两项说明**当前主干的登录与上传在浏览器里可能就是坏的**。若不在重构前修复，Go 接管后无法区分"迁移引入的回归"与"既有故障"。

---

## 2. 三条真实调用链（Phase 0 §2.1 要求逐条定位）

### 2.1 查询链（读路径）

| 步骤 | 位置 | 说明 |
| --- | --- | --- |
| HTTP/WS 入口 | `api/chat.py:53`（SSE）、`api/ws.py:54`（WS）、`chat.py:20`（同步） | WS 仅解 JWT，不回查 DB、不查 role [V] |
| → 转发壳 | `services/agent.py:26,33` | 无业务逻辑，纯转发到 `agent/core` |
| 外层 Agent 图 | `agent/core.py:217`：`START→intent_router→response_agent` | 意图分类只读 `classification`，`complexity` 字段从不使用（`:180`），与 `:3` 文档注释相反 [V] |
| ReAct 内循环 | `core.py:197`（`llm_call:103` ↔ `tool_node:115`），`should_continue:153` | 终止工具 = Answer/Question（`:46`），`bind_tools(tool_choice="any")`（`:96`） |
| 检索工具 | `services/tools.py:149` | **每轮只允许调用 1 次**（`:167`）[V] |
| 内层 RAG 图 | `rag/rag_pipeline.py:583`：`retrieve_initial→grade_documents→`（条件边 `:615`）`→[END \| rewrite_question→retrieve_expanded→回 grade]` | 循环上限 `MAX_RAG_RETRIES=3`（`:244`） |
| 检索实现 | `rag/rag_utils.py:703 retrieve_documents` | 公式检索 → Hybrid → Rerank → Auto-merge → Context-expansion → 引文提级 |
| Milvus | `vectordb/milvus_client.py:499 hybrid_retrieve` | 双 AnnSearchRequest（各 `top_k*2`）+ `RRFRanker(k=60)`（`:565`），失败降级 `dense_retrieve:605` |
| 引用校验 | `agent/verify.py:36 verify_citations` | **只校验 `[Source N]` 编号是否存在**，不做语义接地 [V] |
| SSE 下发 | `core.py:393,415,420,426,428` | 事件类型 `content`/`rag_step`/`citations`/`trace`/`error` + `data: [DONE]` |

**关键事实**：`content` 事件是**整段最终答案一次性下发**（`core.py:379`），不是 token 级增量 [V]。计划 §9.3 的"实时任务进度"若要逐 token 流，需改造 LangGraph 流的产出方式。

### 2.2 入库链（写路径）

`documents.py:410 upload/async` → `BackgroundTasks`（同进程线程池，`:444`）→ `_process_upload`：cleanup（`:152` Milvus delete + 父块删 + BM25 扣减）→ parse（`rag/document_loader.py`）→ parent_store（`:185`）→ vector_store（`vectordb/milvus_writer.py:108`）。

任务状态存于 `services/upload_jobs.py`：`USE_REDIS_JOB_MANAGER` 决定后端（`:487`），**默认 false = 进程内存 dict（`:102`）→ 重启即全丢、多 worker 不共享、无清理无上限** [V]。Redis 模式记录存活但执行线程已死，作业会**永远停在 running** [V]。

前端进度为 **1s REST 轮询**（`useDocuments.ts:135`、`:207`），非推送。`ws.py:4-5` 注释声称有 `/ws/upload/{job_id}` 端点，**代码中不存在** [V]。

### 2.3 认证链

`api/auth.py:81 login` → `core/auth.py` 签发 HS256 JWT。access claims = `{sub: 用户名(非 id), role, exp}`，**无 `type`/`iat`/`jti`/`iss`/`aud`**；refresh 额外带 `type:"refresh"`（`core/auth.py:202-208`）。

**安全缺陷（迁移到 Go 前必须先定策略）**：

- `get_current_user`（`core/auth.py:274-287`）只解 `sub` 回查 users，**不校验 `type`** → **refresh token 可直接当 access token 使用**。[V]
- `JWT_EXPIRE_MINUTES` 默认 **1440（24h）**，`JWT_SECRET_KEY` 默认值 `"replace-with-strong-random-secret"`。[V]
- `ADMIN_INVITE_CODE` 默认硬编码 `"paperrag-admin-2026"`（`core/auth.py:352`），知道它即可自助注册 admin。[V]
- `RATE_LIMIT` 环境变量**只用于打日志**（`app.py:67-70`），`Limiter(default_limits=[])`（`rate_limit.py:39`）→ **没有任何全局限流**，只有若干路由级装饰器。日志"全局速率限制已启用"是假的。[V]
- 限流 key = `get_remote_address`，nginx 未配置 trusted-proxy → 反代后所有客户端共享一个桶。[V]
- `documents.py:599 /ingest` 的 `directory` 参数接受**任意服务端路径**（admin 权限下的任意目录读取面）。[V]

---

## 3. 已验证的功能断链（计划 §17-Q8"哪些功能已经存在"的答案）

这是 Phase 0 最重要的产出。README 与 `docs/archive/plan-5-academic.md`（已归档）标 ✅ 的差异化功能，有 **5 处实际断链**。

| # | 宣称 | 实测 | 证据 |
| --- | --- | --- | --- |
| D1 | 公式感知检索 ✅ | **死代码**。`_build_formula_index` 全仓无调用点 → LSH 索引恒空 → `_formula_search` 恒返 `[]` | `rag_utils.py:644`（定义）、`:568`（消费）、grep 零调用 [V] |
| D2 | Auto-merging（结构分块默认路径） | **失效**。`_split_structural` 只产 `chunk_level=3`，从不产 1/2 → `parent_docs` 恒空 → ParentChunkStore 无写入 → 合并数恒 0 | `document_loader.py:496-587`、`:559`；`api/documents.py:173` [V] |
| D3 | 学术元数据入库 | **入库即丢弃**。`formulas`/`citations`/`glossary_terms`/`chapter_path`/`parent_content`/`has_figure`/`has_table` 均不在 Milvus 写入字段映射中 | `milvus_writer.py:130-159` vs `document_loader.py:566-582` [V] |
| D4 | 多模态（CLIP + 图表检索）✅ | **完全未接线**。`index_figures`/`search_by_text`/`get_multimodal_retriever` 除自身与测试外零调用者；`_init_collection:212` 还误用字符串 dtype | grep [V] |
| D5 | 论文知识图谱 ✅ | **死表**。`paper_nodes`/`citation_edges`/`glossary_entries` 有 ORM 有迁移，**零写入零读取**；`rag/glossary_extractor.py:13` 的 `GlossaryEntry` 是同名 NamedTuple，与 ORM 无关 | `models.py:322,360,396` [V] |
| D6 | ML 布局分析 ✅ | **装饰性**。`analyze_layout` 被调用，但结果只设 `has_figure/has_table`（随即被 D3 丢弃），整段包在 `try/except: pass` | `document_loader.py:622-640` [V] |
| D7 | workspaces/RBAC | **空壳**。`workspaces`/`workspace_members` 两表零写入；`_check_workspace_access`（`core/auth.py:365`）无调用点；无任何 workspace HTTP 端点 | grep [V] |
| D8 | 死配置 | `ENABLE_HYDE`、`RETRIEVAL_COARSE_K`、`RERANK_TOP_N`、`RRF_K` 全零引用（实际值硬编码 `top_k*3`/`k=60`/`5`）；`FAST_MODEL`、`AMAP_WEATHER_API`、`AMAP_API_KEY` 零引用；`config/dev.py`、`config/prod.py` **从未被任何代码导入**（仅出现在 `__init__.py:4-10` 的 docstring 里）→ 其中 6/5 条 `os.setdefault` 预设全部失效 | grep [V] |

**确认真实生效的能力**（重构必须保住的部分）：HyDE / Step-back 查询改写（`rag_pipeline.py:316-578`）、双轨 Rerank（`rag_utils.py:195`）、Context-expansion（`:304`，兄弟块+相邻父块+定理优先）、引文提级（`:670`，查询时从 chunk 文本重算，绕开了 D3，可用）、dense+手写 BM25 hybrid+RRF、`core/budget.py` 的 per-query LLM 预算（`MAX_LLM_CALLS=6`/`MAX_COST=0.05`，token 用 `len//4` 粗估）、语义缓存（进程内，阈值 0.92）。

**学术结构识别全部为纯正则，无 ML**：定理 `theorem_detector.py:73`（逐行匹配 + 前 8000 字符关键词回退）、公式 `formula_normalizer.py:158`（`$/$$/\[/equation` + 标准化 + MinHash LSH）、引文 `citation_extractor.py:33`（5 种格式）、清洗 `academic_cleaner.py:52`（页眉页脚模式 + 文末 ≥5 行带 DOI 引用块）。

---

## 4. 数据层现状与"真相归属"（决定 Go 能否接管）

| 数据 | 当前唯一真相 | 问题 |
| --- | --- | --- |
| 用户 | PG `users` | 可用 |
| 会话/消息 | PG `chat_sessions`/`chat_messages` | `conversation_storage.py:80` 是**先全删再整批重插**（覆盖式写，非 append-only）→ 无法承载 evidence/finding 关联 [V] |
| 父块 | PG `parent_chunks`（Cache-Aside + Redis） | 只有 level 1/2 入库，而 D2 使 PDF 路径根本不产 1/2 → **该表实际近空** |
| **叶子块文本** | **只在 Milvus**，`text VARCHAR(2000)`（`milvus_client.py:240`） | **超长被截断**；PG 无叶子块 → Go 侧无法从关系库读到 chunk 真相 [V] |
| 文档清单 | Milvus `query` 聚合 filename（`documents.py:384`）+ 文件 `backend/data/ingested.json`（md5 去重） | **没有 documents/papers 关系实体**；`ingested.json` 并发写无锁，多 worker 互相覆盖 [V] |
| BM25 词频 | 文件 `backend/data/bm25_state.json` | 与 DB 无事务关系 [V] |
| 上传/删除任务 | 内存 dict（默认）或 Redis `paperrag:job:{id}`（TTL 86400 仅 create 时设一次） | 非持久；Redis 模式下 upload 与 delete 两个实例**共用同一前缀**，`GET /upload/jobs` 会把删除任务一起返回 [V] |
| Redis 其余 | `paperrag:parent_chunk:*`、`chat_messages:*`、`chat_sessions:*`，TTL 300s | 纯缓存，Go 可视为可丢弃 [V] |
| Milvus 集合 | 主集合 `embeddings_collection` + `figure_embeddings`（后者无人用） | `drop_collection` 定义后零调用；**无 paper_version / 无双版本 / 无别名切换**，同名重传即硬覆盖，旧版本不可寻址 [V] |

**ORM 与迁移一致性**：9 表逐字段核对基本一致；漂移 3 处 —— ① ORM 要 `ix_paper_nodes_id` 而迁移未建；② `filename` 唯一性用唯一索引而非 UNIQUE 约束（sqlc 读 `information_schema` 时 `constraint_type='u'` 查不到）；③ 时间戳混用 naive `utcnow()`（`conversation_storage.py:85`）与 aware `now(UTC)`（`parent_chunk_store.py:95`），列类型却是 `timestamp without time zone`。[V]

**迁移链可信度**：`init_db()` 先 `subprocess` 跑 `alembic upgrade head`，**失败则静默回退 `Base.metadata.create_all`**（`core/database.py:99-120`）→ 生产库可能完全没有 `alembic_version` 行，Go 侧不能假定迁移历史可信，需要一次 schema 快照对齐。[V]

---

## 5. 对外契约盘点（Go 必须逐字节复刻的部分）

25 条路由（24 HTTP + 1 WS），**前端实际只依赖 13 条**。完整表格见 `01-current-architecture.md` §3。无人调用：`/auth/refresh`、`/chat`（同步）、两个同步文档端点、`/documents/ingest`、`/cache/clear`、`/stats/usage`、`/documents/upload/jobs`（列表）。

必须复刻的语义（不可"顺手改进"，否则前端与既有客户端断裂）：

- 错误信封：统一 `{"detail": ...}`，但 **429 是另一种信封** `{"error": "Rate limit exceeded: ..."}`（slowapi 内部）；422 是 FastAPI 校验数组。[V]
- **无分页**：全仓 grep `pagination|offset|page_size|total|has_more` = 0 命中，列表全量返回（`/documents` Milvus `limit=10000`）。[V]
- 密码哈希：`pbkdf2_sha256$<rounds>$<标准base64盐>$<标准base64摘要>`，兼容读旧 bcrypt 但新写入只用 PBKDF2 → **Go 必须实现同格式才能验旧密码**。[V]
- 无 Cookie；token 在 localStorage（`accessToken`/`currentUser`），WS 走 query `token`。[V]
- `rag_trace` **同一数据两种形状**：REST 路径按 pydantic `RagTrace` 校验（`schemas.py:167-248`），SSE/WS 直发原始 dict（`rag_pipeline.py:183-210`）；且 `ChatResponse`（`schemas.py:251`）**会静默丢弃 `source_map`/`citations`/`unsupported`**（`agent/core.py:325-331` 明明返回了）。Go 转发时不能套用 pydantic 过滤。[V]
- 静态挂载在 `/`（`html=True` SPA 回退）→ **任何未匹配 `/api/v1` 的路径都被静态吞掉**，这正是 §1.1 上传 404 的成因。[V]

---

## 6. 模块处置表（Phase 0 §2.2 要求的六档标注）

| 模块 | 处置 | 理由 |
| --- | --- | --- |
| `rag/document_loader.py`、`academic_cleaner.py`、`theorem_detector.py`、`formula_normalizer.py`、`citation_extractor.py`、`glossary_extractor.py` | **REUSE**（留在 Python AI Core） | 正则解析成熟、测试覆盖，重写无收益 |
| `rag/embedding.py`（dense + 手写 BM25）、`rag_utils.py` 的 hybrid/rerank/context-expansion | **REUSE** | 计划 §4.1 明确要求不重写 |
| `rag/rag_pipeline.py`、`agent/core.py`、`services/tools.py`、`agent/verify.py` | **EXTEND** | LangGraph 可复用为专用 Worker；需补语义接地校验、解掉"1 次工具调用"上限、按新 Agent 契约拆分 |
| `rag/multimodal.py`、`layout_analyzer.py`、`formula_index.py` | **DEFER** | D1/D4/D6 断链，当前无人消费；接线属新功能而非迁移 |
| `api/auth.py`、`core/auth.py`（JWT/PBKDF2/RBAC） | **MOVE** → Go | 计划 §3.4 要求 Go 统一鉴权；须复刻 §5 的哈希与 claims |
| `api/sessions.py`、`services/conversation_storage.py` | **MOVE** → Go | 纯 CRUD；顺带把覆盖式写改 append-only |
| `api/documents.py`、`services/upload_jobs.py` | **MOVE** → Go | 任务队列本就该由 Go Frontier 承担（计划 §5.3）；Python 只留 parse/index |
| `api/chat.py`、`api/ws.py`、`services/agent.py` | **MOVE**（门面）+ **REUSE**（内核） | Go 提供 SSE/WS 与事件持久化，转发到 Python `/internal/v1/ai/execute` |
| `api/cache.py`、`api/stats.py`、`core/stats.py`、`core/metrics.py` | **REFACTOR** | 现为进程内存，多副本无意义；Go 侧改为 PG/Redis 支撑 |
| `core/config/*` | **REFACTOR** | 全在 import 期读 env、8 项死配置、`dev.py`/`prod.py` 从未导入 → Go 用结构化配置，Python 侧收敛为启动期校验 |
| `core/models.py` 的 workspaces / paper_nodes / citation_edges / glossary_entries | **REFACTOR** | D5/D7 死表，保留骨架作为 knowledge_* 的迁移起点 |
| Research Run / Frontier / Planner / Discovery / Evidence / Report | **NEW** | 现系统完全没有：无 documents 实体、无任务持久化、无版本、无证据模型 |

---

## 7. 待确认事实（`[U]`）

- 实跑 8 项端到端流程（需要 `.env` + LLM key + Milvus/PG/Redis 起容器）。
- `docker-compose*.yml` / `.env.production.example` 的 env 集合与 `core/config/` 的差集（`.env.example` 已见 `AGENT_ENABLED`、`ENTAILMENT_BACKEND` 两项在 config 中无对应常量，疑遗留）。
- `docs/archive/` 下 4 份既有计划（`improvement_plan.md`、`code-review-action-items.md`、`architecture-review-and-improvement-plan.md`、`plan-5-academic.md`）与本文的结论冲突处：**已按本文为准并于 2026-10-09 归档**，归档件不再作为实施依据（见 `docs/archive/README.md`）。
