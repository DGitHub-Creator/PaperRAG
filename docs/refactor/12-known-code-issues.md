# 12 — 代码问题台账（记录 → 逐条处置）

> **本文状态（2026-10-12）**：性质=**问题清单 + 处置记录**。用来承接"按产品愿景（[11](11-product-vision.md)）检查仓库"时发现的**代码层**问题。
> 2026-10-11 那轮**只改文档**，所以 A 组当时一律没有动手；2026-10-12 起按 P0 顺序逐条处置，
> **处置完的条目移进 §C 并写清证据等级**，别让它长期停留在"待办"里变成噪音。

## A. 阻塞当前阶段（P0）的问题

| # | 问题 | 证据（可复核） | 影响 | 建议改法 | 归属 |
| --- | --- | --- | --- | --- | --- |
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
| C1 | `--live` 快照不含列清单 ⇒ 基线 DDL 的 varchar 长度与 NOT NULL 无机检覆盖 | **2026-10-12 已补机制**：payload 增加 `columns`；新增离线模式 `--verify-columns` 逐列比类型/长度/NOT NULL/DEFAULT，SERIAL 的 nextval 按库侧口径算，快照缺 `columns` 时如实 exit 2（不把"比不了"说成"比过了"）。⚠️ **证据等级只到 mock**（15 条新单测，`test_audit_schema.py` 共 34 项，含"解析真基线得 10 表/59 列"这条防解析器脱节的用例）；实跑要等 Docker 重导快照——仓库里现存那份仍是旧版导出的，命令现在返回 2 |
| C2 | `--check-baseline` 的 up 剥注释、down 用原文匹配，两套规则 | **2026-10-12 已统一**：两者都走 `_strip_comments()`。`000001_baseline.down.sql` 头注释里"校验器按原文匹配、连注释一起算"那句随之失效，已改写 |
| C3 | 临时参照 `server/sql/schema.sql` 在 `users.created_at` / `users.role` 上失真（库里其实有 DEFAULT） | **2026-10-12 已消解，但原建议改法被证伪**。该文件已删除，schema 源换成真基线。切过去之后那次 `git diff` **一个字都没变**——`User` struct 与三条查询的生成类型完全一致。原因是 **sqlc 不把列默认值编码进 Go 类型**，所以"切到真基线后在 diff 里专门核对这两列"这条改法物理上做不到：diff 门禁能抓的只有类型、可空性、列/表存在性。DEFAULT 的核查因此改由 `--verify-columns` 承担（见 C1）。业务层的后果单独记在 `05 §4.2.1`：`role`/`created_at` 仍显式给值，因为 `DEFAULT now()` 取会话时区而 §4 的 UTC 审计未完成 |
| C4 | `sqlc.yaml` 仍指向临时参照，P0-3 无法 done | **2026-10-12 已切**并与 `dev.py gen --check` 同批落地；P0-3 转 done（mock）。实际收益不是字段纠偏而是**覆盖面**：此前 Go 只看得见 `users` 一张表，切换后 10 张表 / 59 字段全部进 model。⚠️ 顺带推翻一条工具记录：本卡原写「本机目前没有 sqlc 二进制，需 `go install`」——**错**，`$HOME/go/bin/sqlc.exe` 就是钉的 v1.30.0，`dev.py` 早就优先用本机二进制、找不到才退回 `go run`。同批补三条生成前置检查（schema 目录含 `.down.sql` 拒绝、`migrations/*.up.sql` 未登记拒绝、`internal/db/X.sql.go` 孤儿输出拒绝），前两条是本机真踩出来的：把目录整个交给 sqlc 会按文件名顺序先执行 down 再执行 up，生成物等于按回退后的库产出 |
| C5 | `backend/internal_api/` 七条路径已就位，但缺 `ai_executions` 迁移，P0-7 的幂等/取消/超时语义没有真实存储支撑 | **2026-10-12 已交付迁移文件（证据等级 mock）**：`server/migrations/000002_ai_executions.{up,down}.sql`，17 列**逐列回指** `executions.py:26-42` 的 dataclass（这张表的列清单此前没有任何文档逐字写过）；已登记进 `sqlc.yaml` 并生成 `AiExecution` model。四个拍板与新表规则记在 `05 §2.6`：TIMESTAMPTZ、`run_id NOT NULL DEFAULT ''`（否则 `UNIQUE(run_id, idempotency_key)` 在 NULL 行上静默失效）、新表三个时间戳不给库侧 DEFAULT、只建实现读写的列且不写 GRANT。⚠️ **未在真 PG 上执行过**——本机 Docker daemon 本轮不可达，"PG 15 接受这份 DDL"目前只有两个间接证据：sqlc 的 PG 解析器吃下了它、`parse_ddl_columns` 吃下了它（`test_audit_schema.py` 增至 37 项，新增 3 条把「整个 migrations/ 可解析」与「`check_baseline` 对真目录返回空」钉进用例）。P0-7 仍 in_progress：`-m chain -k ai_executions` 要等 compose 里的 PG。编号分配同时改了 `05 §2.5/§3` 与 `09:100`（`000003=fix_drift`、`000004=paper_chunks`、条件式的 `auth_compat` **不占号**） |
| C12 | `.env.example` 的 `KEY= #值` 行内注释会让应用起不来 | 2026-10-10 已改为整行注释（11 行） |
| C16 | X2/X4/X5 三条退出标准**挂着判定命令，但命令引用的脚本不存在**（`check_nginx_routes.py`、`export_pbkdf2_golden.py`），所以它们永远只能 `not_run`——看起来"有验收办法"，实际无判据 | **2026-10-12 已闭**：两个脚本落地（`check_nginx_routes.py` 21 项单测、`export_pbkdf2_golden.py`＋`contracts/pbkdf2_golden.json` 15 项单测），X2/X4/X5 的 `result` 相应从 `not_run` 改成 **`fail` 并写明红在哪**（X2：`/api/` 仍指 Python，P0-8；X4/X5：`server/internal/auth` 这个 Go 包不存在，P0-6）。同批给 `sync_progress.py` 加机检：**in_progress/done 阶段**的退出命令里 `scripts/*.py` 必须存在。范围刻意收窄——P2 的 Z1 引用的 `rebuild_chunks.py` 是那一阶段要新建的，要求它今天就存在会把未来的活变成今天的违规，门禁长红就人人绕过 |
| C17 | "跑一条引用不存在包/不存在测试的 `go test`，rc 是 0 还是 1"没核过——如果是 0，X4/X5 会变成**天然假绿**的判据 | **2026-10-12 已核实：两种情况都 rc=1**。`go test ./internal/auth/...` 报 `GetFileAttributesEx ... cannot find the file specified` → `FAIL [setup failed]`；`cd server && go test -run TestVerifyLegacyHash`（该目录无 Go 文件）报 `no Go files` → `FAIL [setup failed]`。所以这两条命令的绿必须是真跑出来的绿。⚠️ 与之对照的是 **pytest 会假绿**：`-m chain` 收 0 项返回 exit=5（不算过，已记 `AGENTS.md`），而 `pytest -k <拼错的用例名>` 收 0 项同样返回 5——凡是"选择器可能落空"的判据都必须另外断言收集数不为 0 |
| C13 | compose 的 backend 缺 `target: backend` → 构建出 nginx 镜像 | 已修（`542fd77a` 之前那批） |
| C14 | `progress.json` 的 `current` / `risks[0]` 与现状矛盾（"Docker 起不来""未安装 Docker Desktop"） | 2026-10-11 已改写并记入 `AGENTS.md` §4「已被推翻的旧结论」 |
| C15 | `.pytest-cache/` 目录权限被占，`Remove-Item` 被拒 | 纯本机整洁问题，已被 `.gitignore` 忽略；需用户在自有终端删除 |
