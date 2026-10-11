# 06 — Milestone A0 任务清单（文件级）【已归档】

> ⚠️ **已归档（2026-10-09），不作为实施依据**（原位于 `docs/refactor/06-milestone-a0.md`）。
> 2026-10-09 用户《重构执行总纲》以原则①「端到端链路优先」推翻旧决策 Q1
> （"Go 之前先做一轮完整基线修复"），路线改为 **P0 架构与契约先行**，见
> [08-principles-and-conventions.md](../refactor/08-principles-and-conventions.md) §2 与
> [04-migration.md](../refactor/04-migration.md) §0/§3。本文件的任务表与 E1–E10 **保留作历史记录与文件级细节来源**，
> **不再作为排期依据**；每张卡的新归属见本文 §4。已完成项（A0-1 `996cf777`、A0-3 `335aeb7e`）不撤销。
> 现行任务卡与退出标准在 [09-milestone-p0.md](../refactor/09-milestone-p0.md)，进度真相源是 [progress.json](../progress.json)。
>
> 原文目标：**让"旧系统可用"变成可机检的事实，并让 chunk 数据可信**。A0 不写任何 Go 代码、不引入新框架。
> 规模：solo 15–20h/周，约 3–4 周。每个 `A0-x` 是一个独立提交（可含少量 fixup），提交信息前缀 `fix(a0):` / `feat(a0):` / `test(a0):` / `docs(a0):`。

## 0. 退出标准（全部必须机检通过）

| # | 标准 | 判定命令 |
| --- | --- | --- |
| E1 | 前端类型 0 error 且进 CI | `cd frontend && npm run typecheck`；`.github/workflows/ci.yml` frontend job 含 typecheck 步骤 |
| E2 | 真实浏览器 E2E 全绿 | `npm run test:e2e`（Playwright chromium）：登录 → 上传 PDF → 轮询到 completed → 提问 → 看到 `[Source N]` 与 citations |
| E3 | 上传→入库→查询链路测试通过 | `uv run pytest -m chain` |
| E4 | chunk 正文进 PG 且无截断 | `uv run python scripts/rebuild_chunks.py --verify-only` 退出码 0；§05 §5 验收的两条 SQL 成立 |
| E5 | 公式检索真实生效 | `uv run pytest -m chain -k formula` 且索引表 `formula_index_entries` 行数 > 0 |
| E6 | 无静默建表 | `uv run pytest -m unit -k init_db` 断言 alembic 失败时抛错 |
| E7 | refresh token 不能当 access token | `uv run pytest -m unit -k token_type` |
| E8 | 全局限流真实生效且日志诚实 | `uv run pytest -m integration -k rate_limit` + 启动日志与 `default_limits` 一致 |
| E9 | 原 280 项 mock 测试保持绿 | `uv run pytest -q` |
| E10 | README 功能状态三档化 | 人工 review + 无 ✅ 残留于未接线模块 |

### 0.1 当前状态（2026-10-09）

- **已通过**：E1（A0-1，`2c3e58e`）、E6/E7/E8/E9（A0-3，`335aeb7e`；测试 280 → 307 全绿）。
- **待人工复核**：E10 —— README 功能表已改三档，但需要你 review 口径。
- **未开始**：E2、E3、E4、E5（依赖 A0-0/A0-2/A0-4/A0-5/A0-6）。
- E6/E7/E8 的判定命令带 `-m unit|integration`，需先完成 A0-0 ③ 的 marker 注册；在此之前可用
  `uv run pytest -k "init_db or token_type or rate_limit"` 复现同样这批用例。

## 1. 任务表

### A0-0 可复现环境（前置，无它则后续无法验证）

| 项 | 内容 |
| --- | --- |
| 文件 | `.env.example`、`docker-compose.yml`、`docs/refactor/a0-environment.md`（新） |
| 改动 | ① `.env.example` 删除死键 `AGENT_ENABLED`、`ENTAILMENT_BACKEND`（00-audit D8），补 `AICORE_INTERNAL_TOKEN` 预留位；② 写一份"起容器 → migrate → 上传样例 PDF → 提问"的可复制命令序列，并**实跑一遍**；③ `pyproject.toml` 注册 pytest markers（`--strict-markers` 已开启，未注册的新 marker 会直接报错）：`unit`/`integration`/`chain`/`e2e`/`slow` |
| 依赖 | 无 |
| 验收 | 按文档从零启动成功；样例 PDF 可检索 |
| 风险 | 需要 LLM key；无 key 时以 `--dry-run`/mock 边界标注哪些步骤不可验 |

### A0-1 前端故障修复 + 类型门禁 ✅（`2c3e58e`）

| 项 | 内容 |
| --- | --- |
| 文件 | `frontend/src/composables/useAuth.ts`、`frontend/src/services/api.ts`、`frontend/src/composables/useDocuments.ts`、`frontend/src/components/CitationChips.vue`、`.github/workflows/ci.yml` |
| 改动 | ① `useAuth.ts:2` 导入补 `apiFetch`（**已在 `api.ts:29` 导出**，仅缺 import）；② `api.ts` 导出 `BASE`，`useDocuments.ts:143` 改 `xhr.open("POST", `${BASE}/documents/upload/async`)`（保留 XHR 是为了 `upload.onprogress`）；③ `CitationChips.vue` props 给 `citations`/`unsupported` 加默认值 `() => []`，消除 4 处 TS18048；④ CI frontend job 在 build 前加 `- run: npm run typecheck` |
| 依赖 | 无 |
| 验收 | E1 |
| 风险 | 低。注意 `authFetch` 对 401 会清 token 并派发事件，登录/注册必须继续走 `apiFetch`（无鉴权头），不能"顺手统一" |

### A0-2 Schema 与时间戳核查（只读，为 A0-4 铺路）

| 项 | 内容 |
| --- | --- |
| 文件 | `scripts/audit_schema.py`（新）、`docs/refactor/schema-baseline.json`（新）、`scripts/probe_timestamps.py`（新）、`docs/refactor/timestamp-audit.md`（新） |
| 改动 | 实现 05 §1 的核查与 05 §4.1 的三种时区验证法，产出结论；**不改任何 DDL** |
| 依赖 | A0-0 |
| 验收 | 报告能回答：现库存不存在 `alembic_version`？实际表集合？每表时间列语义判定？ |
| 风险 | 无（只读） |

### A0-3 鉴权与运行安全修复 ✅（`335aeb7e`）

| 项 | 内容 |
| --- | --- |
| 文件 | `backend/core/auth.py`、`backend/api/ws.py`、`backend/core/config/auth.py`、`backend/core/config/__init__.py`、`backend/core/rate_limit.py`、`backend/app.py`、`backend/core/database.py`、`nginx/nginx.conf` |
| 改动 | ① `get_current_user`（`core/auth.py:274-287`）校验 `type` 缺失或 `=="access"` 才放行，refresh token 返回 401（E7）；② WS（`ws.py:43-48`）改为回查 `users` 并校验 role，与 HTTP 侧同语义；③ `ADMIN_INVITE_CODE` 去掉硬编码默认值：未配置时禁止 admin 注册并明确报错；④ `JWT_SECRET_KEY` 无默认值，缺失即启动失败（`validate_runtime_security` 扩展）；`JWT_EXPIRE_MINUTES` 默认降到 60（保留 env 覆盖，前端 localStorage 逻辑不变）；⑤ `RATE_LIMIT` 真正接入 `Limiter(default_limits=[...])`，日志与实配一致（E8）；⑥ 反代场景：`TRUST_PROXY_HEADERS` 开启时才取 `X-Forwarded-For` 首跳，nginx 补 `X-Forwarded-For` 与 `proxy_set_header Host`；⑦ `init_db()`（`database.py:99-120`）**删除 create_all 静默兜底**：alembic 缺失或失败 → 抛 `RuntimeError` 并打印差异（E6）；⑧ `config/__init__.py` 按 `APP_ENV` 显式导入 `config.dev`/`config.prod`（兑现 docstring 承诺），或二者删除并把预设合并进 `__init__` —— 二选一，**不许保留不生效的文件** |
| 依赖 | A0-0 |
| 验收 | E6、E7、E8；`tests/unit/test_auth.py` 新增 token-type 与 invite-code 用例 |
| 风险 | ④⑤⑧ 会改变启动行为：`RATE_LIMIT` 一旦真生效，dev 下 60/minute 可能打断 E2E 上传轮询 → E2E 用独立 env（`RATE_LIMIT=1000/minute`）。⑧ 若选"导入 dev"，dev 的 `setdefault("RATE_LIMIT","")` 会使 ⑤ 在 dev 下失效，属预期，需在文档写明 |

### A0-4 Chunk 可信化（最大项，A 的前置阻塞）

| 项 | 内容 |
| --- | --- |
| 文件 | `backend/core/models.py`、`backend/rag/document_loader.py`、`backend/rag/parent_chunk_store.py`、`backend/vectordb/milvus_writer.py`、`backend/vectordb/milvus_client.py`、`backend/api/documents.py`、`server/migrations/000003_paper_chunks.*.sql`（新，纯 SQL） |
| 改动 | ① 新增 `Paper`/`PaperVersion`/`PaperFile`/`PaperSection`/`PaperChunk` ORM 与建表脚本（结构照 05 §3）；② `_split_structural`（`document_loader.py:496-587`）除叶级外**同时产出 level 1/2 父块**（修 D2/G11），并保持 `chunk_id = "{version}:{level}:{ordinal:06d}"`（05 §3.1），旧格式留 `legacy_chunk_id`；③ 入库链路把 ①的全部 chunk 写 PG（**含叶级**，修 G10），`ParentChunkStore` 改读写 `paper_chunks`（05 §3.4）；④ `milvus_writer.py:130-159` 字段映射补齐 `level/page_number/chapter_path/has_formula/has_citation/has_glossary/has_theorem/has_proof`（修 D3/G12），`text` 明确降级为展示副本（修 G10 的另一半：读取一律回 PG）；⑤ `api/documents.py` 的 job 步骤改按新链路（cleanup→parse→pg_store→vector_store→formula_index→verify），失败时 `index_state='failed'` + `index_error`；⑥ `scripts/rebuild_chunks.py`（05 §5），带 `--dry-run`/`--verify-only`；⑦ `models.py:207-210` docstring 层级语义改正（修 G18/§3.3） |
| 依赖 | A0-2 |
| 验收 | E4；`uv run pytest -m chain -k "chunks and not formula"` |
| 风险 | **最高**。④ 改了 Milvus schema 字段 → 需 `--reindex` 全量重建，存在检索空窗；对策：新版本 ready 后才切 `current_version_id`（05 §5.7），旧版本 chunk 保留可回退。② 改动会影响 `rag_utils.py:727` 的 `chunk_level==3` 过滤 → 同步改列名 `level` 并跑 `tests/unit/test_rag_utils*.py`。至此后 alembic 冻结（05 §2.4）：A0 的新表全部走 `server/migrations/` 纯 SQL + `migrate` CLI，**只新增表、不改旧表**，与 Go 基线不冲突 |

### A0-5 公式索引接通（D1）

| 项 | 内容 |
| --- | --- |
| 文件 | `backend/rag/rag_utils.py`、`backend/rag/formula_index.py`、`backend/services/upload_jobs.py`、`backend/api/documents.py` |
| 改动 | ① 入库链路在 chunk 落 PG 后调用 `_build_formula_index`（`rag_utils.py:644`，当前**零调用点**）；② LSH 索引从进程内单例改为以 PG 表 `formula_index_entries(formula_norm, chunk_id, version_id)` 为持久真相、内存 LSH 为热缓存（重启即空是 D1 的第二重病因）；③ 删除文档时同事务清理索引条目；④ `_formula_search` 命中后按 `chunk_id` 回 PG 取正文（不再依赖 Milvus `output_fields` 里的截断 `text`） |
| 依赖 | A0-4 |
| 验收 | E5；`_build_formula_index` 的调用点可在 grep 中查到 |
| 风险 | 中。规范化过窄会漏召回；用 E3 的真实链路测试固定行为，避免只测函数不测链路 |

### A0-6 真实链路测试与科研回归集

| 项 | 内容 |
| --- | --- |
| 文件 | `tests/conftest.py`、`tests/integration/`（扩）、`tests/chain/`（新）、`tests/e2e/`（新，Playwright）、`frontend/package.json`、`tests/fixtures/research_questions.json`（新，10–15 题）、`docs/refactor/baseline-results.md`（新） |
| 改动 | ① 真实 PG/Redis/Milvus 的 integration fixture（compose 起服务，随机端口，函数级隔离），**不 mock**；② `tests/chain/test_upload_to_answer.py`：上传样例 PDF → 入库 → `retrieve_documents` → Agent 回答 → 引用可回溯到 `paper_chunks` 行；③ 公式链路用例（问题含 LaTeX）；④ Playwright：登录/上传/问答/引用四条主路径；⑤ 固定科研问题集跑分并记录基线（不作门禁阈值，决策 Q8）；⑥ 现有 280 项保留，全部归入 `unit` marker |
| 依赖 | A0-1、A0-3（E2E 需登录可用）、A0-4/A0-5（链路测试需数据可信） |
| 验收 | E2、E3、E5、E9、E10 之外的全部；CI 增加 `-m "unit or integration"`（chain/e2e 需密钥，先在带密钥的 job 或 nightly） |
| 风险 | chain/e2e 依赖 LLM key 与真实模型输出 → 断言只针对**结构与可追溯性**，不断言文本内容；科研回归集记录而非断言 |

### A0-7 文档与状态修正

| 项 | 内容 |
| --- | --- |
| 文件 | `README.md`、`docs/plan-5-academic.md`、`docs/architecture-review-and-improvement-plan.md`、`backend/agent/core.py`（docstring `:3`）、`backend/api/ws.py`（docstring `:4-5`） |
| 改动 | ① README 功能表改三档（**已实现/部分实现/规划中**）：公式检索与分层分块在 A0 后升"已实现"；多模态、ML 布局分析、知识图谱降为"规划中（代码存在未接线）"；② `plan-5-academic.md` 的 ✅ 逐项复核并改正（当前 4 处误标，见 03 §3）；③ 删除"已实现"中对 D4/D6 的宣传；④ 修 `core.py:3`（实现只读 `classification`，不读 `complexity`）与 `ws.py:4-5`（不存在的 `/ws/upload/{job_id}`）；⑤ README "当前已知问题"替换为真实断链清单并指向 00-audit |
| 依赖 | A0-1…A0-6 结论稳定后 |
| 验收 | E10 |
| 风险 | 低 |

## 2. 依赖顺序

```
A0-0 ──┬─→ A0-1 ──┐
       ├─→ A0-2 ──┴─→ A0-4 ─→ A0-5 ──┐
       └─→ A0-3 ──────────────────────┴─→ A0-6 ─→ A0-7
```

关键路径：**A0-0 → A0-2 → A0-4 → A0-5 → A0-6**。A0-1、A0-3 可与 A0-2/A0-4 并行（无数据耦合），且**建议最先做**——它们是 S/M 档、立刻改善可验证性，并为 E2E 扫清阻塞。

可独立提交的顺序（每个一次提交、一次测试）：A0-1 → A0-3 → A0-0 → A0-2 → A0-4 → A0-5 → A0-6 → A0-7。

## 3. A0 明确不做

不写 Go 服务代码（A0 的建表只用 `server/migrations/` 纯 SQL + `migrate` CLI，见 05 §2）· 不删 `parent_chunks`/`multimodal.py`/`layout_analyzer.py` · 不激活 workspace（留给 Go `auth`）· 不重写 `upload_jobs`（由 Frontier 取代）· 不把 `≥95%/≥90%` 设成 CI 门禁 · 不做 `git mv backend→ai-core`（决策 Q2）· 不改前端框架 · 不做 A/B/C 三组实验与消融（决策 Q8，DEFER 到 C 之后）。

## 4. 重映射到新阶段（2026-10-09，权威口径见 04 §3）

| 旧卡 | 新归属 | 变化点 |
| --- | --- | --- |
| A0-0 可复现环境 | **P0-0** | 内容不变（`.env.example` 死键清理、启动序列实跑、pytest marker 注册），但提前到 P0：后续每条验收命令都依赖 `-m` 过滤 |
| A0-1 前端故障 + typecheck 门禁 ✅ | 已完成 `996cf777` | E1 已通过；作为 P0/P1 的前端基址切换前置 |
| A0-2 Schema 与时间戳只读核查 | **P0-2 前置子项** | 由"为 A0-4 铺路"改为"为 Go 基线迁移铺路"；产出物不变（`audit_schema.py`、`schema-baseline.json`、`probe_timestamps.py`、`timestamp-audit.md`） |
| A0-3 鉴权与运行安全 ✅ | 已完成 `335aeb7e` | E6/E7/E8 已通过；现状语义成为 **P0-6 Go 侧认证的行为基线**（Go 必须复刻 token 分型、DB 角色为准、fail-fast 密钥校验） |
| A0-4 Chunk 可信化 | **P2-1** | **两处改动**：① 建表从"Python 侧 alembic"改为 **Go 侧 `server/migrations/` 纯 SQL**（Q4/L3）；② 不再是 P0/P1 的前置阻塞。ORM 与链路改造清单（本文 §1 A0-4 的 ①–⑦）继续作为实施细节来源 |
| A0-5 公式索引接通 | **P2-2** | 不变，但依赖关系改为依赖 P2-1 的 chunk 真相层；`formula_index_entries` DDL 同样出自 `server/migrations/` |
| A0-6 真实链路测试与科研回归集 | **拆三块**：端到端 E2E 骨架 → **P1-6**；chunk/公式链路用例 → **P2-3**；10–15 题固定回归集 → **P2-4** | 原则①要求 P1 就拿出端到端证据，测试不能排在被测对象之后 |
| A0-7 文档与状态修正 | **持续项** | README 三档口径第一轮已在 `106f17dd` 完成；每阶段收口时复核一次（`08` §4 第 5 条） |

本文的 E1–E10 判据仍然有效，只是**归属阶段变了**：E1/E6/E7/E8/E9 已完成；E2/E3 属 P1；E4/E5 属 P2；E10 为持续项。

## 5. 历史遗留（改版前记录，保留原文以便追溯）

- §0.1 的状态记录截至 2026-10-09：E1/E6/E7/E8/E9 通过，E10 待人工复核，E2–E5 未开始。
- E6/E7/E8 的判定命令带 `-m unit|integration`，依赖 P0-0 的 marker 注册；在此之前可用
  `uv run pytest -k "init_db or token_type or rate_limit"` 复现同一批用例。
- 用 `create_all` 建出、无 `alembic_version` 的存量库在 `335aeb7e` 之后**拒绝启动**，需人工补基准版本；
  该项并入 P0-2 的核查清单。
