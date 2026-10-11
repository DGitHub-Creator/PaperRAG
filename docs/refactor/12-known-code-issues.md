# 12 — 代码问题台账（本轮只记录，不改代码）

> **本文状态（2026-10-11）**：性质=**问题清单**。用来承接"按产品愿景（[11](11-product-vision.md)）检查仓库"时发现的**代码层**问题——
> 本轮**只改文档**，所以这些一律没有动手，逐条给出证据、影响、建议改法与归属卡片。
> 处置后请把对应条目移到已解决（或直接删除），别让它长期停留在"待办"里变成噪音。

## A. 阻塞当前阶段（P0）的问题

| # | 问题 | 证据（可复核） | 影响 | 建议改法 | 归属 |
| --- | --- | --- | --- | --- | --- |
| **C1** | `scripts/audit_schema.py --live` 导出的 `schema-baseline.json` **不含列清单** | 导出文件顶层键只有 `tables` / `alembic` / `session_timezone` / `log_timezone` / `server_version` / `indexes` / `constraints` / `column_diff` | 基线 DDL 的列名/类型/NOT NULL/DEFAULT 只能从 alembic 链推导；**`varchar` 长度与 NOT NULL 完全没有任何机检覆盖** | 给 payload 增加 `columns`（每表：name/type/nullable/default），并给 `--check-baseline` 加一个"与基线 JSON 逐列比对"的可选模式 | P0-2 收尾 |
| **C2** | `--check-baseline` 的判定规则**前后不一致**：up 先剥注释再判，down 用**原始全文**判 | 代码：up 路径剥 `--` 与 `/* */`；down 路径直接正则匹配 `DROP TABLE IF EXISTS` | 注释里写这四个词会被判违规（P0-2 的迁移首版就被误伤）；规则的"注释不算数"只对 up 成立 | down 的判定也先剥注释 | P0-2 收尾 |
| **C3** | `server/sql/schema.sql`（P0-3 的**临时参照**）在 `users.created_at` / `users.role` 两列上**失真** | 真库这两列有 `DEFAULT now()` / `DEFAULT 'user'`——依据是它们**没有**出现在 `column_diff` 的 23 条里（说明与 ORM 声明一致，否则会被登记为 `no_server_default`） | 切 sqlc 时若信这份参照，Go 侧会漏掉 DEFAULT 语义 | 切到真基线后重生成，在 diff 里专门核对这两列 | P0-3 |
| **C4** | `server/sqlc.yaml` 仍指向**临时参照** `sql/schema.sql`，未指向 `server/migrations/` | `sqlc.yaml` 内容 + P0-3 note | P0-3 无法 done；`dev.py gen --check` 这个漂移门禁建立在失真的 schema 源上 | 与 `dev.py gen --check` 作为**同一原子改动**切换（本机目前没有 sqlc 二进制，需 `go install …/cmd/sqlc@v1.30.0`） | P0-3 |
| **C5** | `backend/internal_api/` 的 7 条路径已就位，但缺 `ai_executions` 迁移 | P0-7 note；`server/migrations/` 目前只有 `000001_baseline` | P0-7 无法 done；内部执行面的幂等/取消/超时语义没有真实存储支撑 | 依赖 C3/C4 的 schema 源就绪后补 `000002_ai_executions`（注意 `contracts/table-acl.md` 里 `ai_executions` 是 **Python 独占写**） | P0-7 |
| **C6** | compose 里**还没有 Go 服务**；Python 后端仍是唯一 backend，且其镜像需构建（16.5 GB） | `docker-compose.yml` 只有 postgres/redis/etcd/minio/standalone/backend/attu；Dockerfile 的 backend 阶段用 `uv sync` 装 `sentence-transformers`（拖入 torch） | P0-8 未开工；镜像体积影响日常构建与磁盘 | P0-8 加 `go-api` / `go-worker` / `ai-core`（`ai-core` 不发布宿主端口）；镜像瘦身（CPU-only torch 索引 / 分层裁剪）可作为独立优化项 | P0-8 |

## B. 愿景驱动的代码缺口（V1–V3 依赖）

| # | 问题 | 证据 | 影响 | 建议改法 | 归属 |
| --- | --- | --- | --- | --- | --- |
| **C7** | **数据可信化四件事全未修**：公式索引零调用、结构分块不产父块、学术元数据入库即丢、叶子正文只在 Milvus 且 `VARCHAR(2000)` 截断 | `00-audit.md` D1–D3 / G10–G12；本轮实测 `milvus_client.py` 仍 `max_length=2000`、`paper_chunks` 零命中、`_build_formula_index` 无调用点 | 直接挡住产品愿景的 **V1.0 可信学术 RAG** 与 `11 §4.2 Deep Reader`（定理/公式级解析）、`§4.3 比较矩阵`（证据要能回原文） | 按 `05` 的七步收编：chunk 正文落 PG（`paper_chunks`）、公式索引接线并补链路测试、元数据写入映射补齐 | P2-1 / P2-2 / P2-3（**建议按愿景前移**，见 D4） |
| **C8** | `chain` 与 `e2e` 两层**各 0 条用例**；`-m chain` 收 0 项时 pytest 返回 **exit=5** | `pytest --collect-only -m chain` / `-m e2e`；P0-0 记录 | 上面 C7 的四件事**没有任何回归网**——这正是它们长期潜伏的原因；愿景的"证据可信"没有自动防线 | P0-5（跨语言契约）→ P0-9（浏览器 E2E）→ P2-4（10–15 题固定回归集） | P0-5 / P0-9 / P2-4 |
| **C9** | 上传/删除任务默认是**内存态**（`USE_REDIS_JOB_MANAGER=false`），进程重启即丢 | `backend/services/upload_jobs.py`、`01`/`00` 审计 | 与愿景「长期项目记忆」直接冲突 | P1-3：上传编排入 Go + PG 持久化（Frontier 在 P3 接管） | P1-3 |
| **C10** | 双图（Knowledge Graph / Exploration Graph）与 Evidence Registry 目前**只有死表骨架**（`paper_nodes` / `citation_edges` / `glossary_entries` 零写零读） | `00-audit.md` D5；`schema-baseline.json` 里这三张表存在 | 愿景 `§4.5` 与 `§4.6`（Gap Explorer）没有承载 | 按 `02` §8 的 P4 轮廓：先关系表、第一版不引入 Neo4j；升为一等模块见 D7 | P4（V3） |
| **C11** | 前端 `BASE = "/api/v1"`、vite **只监听 `::1`**、探针路由**不带 `/api/v1` 前缀**——三点都有踩坑记录但代码层未"根治" | 本轮实测：`http://localhost:5173/api/v1/auth/me` 401 正常、`127.0.0.1:5173` 连不上；`app.py` 里 `health_router` 裸挂载 | 不影响功能，但每个新 agent/新同事都会踩一次 | 可选：vite `server.host` 显式配 `127.0.0.1` 或 `0.0.0.0`；文档层已写清 | P0-9 / 文档已记 |

## C. 已修/已澄清（留作流程教训，不必再处理）

| # | 事项 | 结论 |
| --- | --- | --- |
| C12 | `.env.example` 的 `KEY= #值` 行内注释会让应用起不来 | 2026-10-10 已改为整行注释（11 行） |
| C13 | compose 的 backend 缺 `target: backend` → 构建出 nginx 镜像 | 已修（`2b38af35` 之前那批） |
| C14 | `progress.json` 的 `current` / `risks[0]` 与现状矛盾（"Docker 起不来""未安装 Docker Desktop"） | 2026-10-11 已改写并记入 `AGENTS.md` §4「已被推翻的旧结论」 |
| C15 | `.pytest-cache/` 目录权限被占，`Remove-Item` 被拒 | 纯本机整洁问题，已被 `.gitignore` 忽略；需用户在自有终端删除 |
