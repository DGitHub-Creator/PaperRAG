# 09 — P0 任务清单：架构骨架与契约（文件级）

> **性质**：待你确认的实施计划。按 `08` §1 原则③，本文件获得确认后才动代码。
> **目标**：搭起目标架构的骨架与契约，并跑通**第一条垂直切片**（浏览器 → Go 注册/登录/me）。
> **不写业务功能迁移**（那是 P1），**不碰 chunk 可信化**（那是 P2）。
> 基线：`main @ 6221147`（前端与鉴权安全修复已在 `2c3e583` / `d8f1563` 落地）。
> 规模：solo 15–20h/周，P0 约 2–2.5 周（W1–W2）。每张卡一个独立提交，前缀 `feat(p0):` / `test(p0):` / `docs(p0):`。

## 0. 退出标准（全部可机检；当前状态一律 `not_run`）

| # | 标准 | 判定命令（仓库根执行，除非注明） | 期望输出 | 等级 |
| --- | --- | --- | --- | --- |
| X1 | 骨架能起来 | `docker compose up -d` 后 `curl http://localhost/api/v1/health` 与 `/api/v1/ready` | 两条均 200；`compose ps` 里 `go-api`/`go-worker`/`ai-core` 为 healthy/running | real |
| X2 | Go 是唯一公开入口 | `docker compose exec nginx grep -R "proxy_pass" /etc/nginx/conf.d/`（或读 `nginx/nginx.conf`）+ 浏览器 Network 面板核对 | 所有 `/api/` upstream 指向 `go-api`；无指向 `ai-core` 的 location | e2e |
| X3 | 契约已锁定且有测试 | `uv run python scripts/check_contracts.py` | 退出 0：OpenAPI 覆盖 13 条在用接口 + `health/ready`（共 18 个操作）；`ai-execution.schema.json` 的 `code` 枚举与 `error-codes.md` 逐字一致；`table-acl.md` 无未标过渡期的双写；前端实调集合与契约**双向**吻合。**2026-10-09 本机 pass**（`tests/unit/test_check_contracts.py` 16 项，含 11 项负向篡改用例；CI backend job 已挂本门禁）。K1/K4 已定案落地，契约只剩 `{"detail": ...}` 一种信封；K2/K3 已定案，落点分别在 P0-3/P0-8，见 §3 | mock |
| X4 | 认证垂直切片可用 | `cd server && go test ./internal/auth/... ` + `uv run pytest -m chain -k go_auth` | Go 单测绿；对同一份 `users` 行，Python 签发的 token 能被 Go 校验，Go 签发的能被 Python 校验（golden vectors 双向） | real |
| X5 | 旧密码不被锁死 | `uv run python scripts/export_pbkdf2_golden.py` 后 `cd server && go test -run TestVerifyLegacyHash` | golden 向量全部通过后才允许 Go 接管 `users` | mock→real |
| X6 | Go 不重复建表 | `cd server && migrate -path migrations -database $DATABASE_URL version` 与 `uv run python scripts/audit_schema.py --check-baseline` | 基线迁移为**非破坏性**（无 DROP）；`schema_migrations` 版本与设计一致；alembic 与 golang-migrate 不冲突 | real |
| X7 | 测试分层可用（marker 已注册且目录即分层） | `uv run python scripts/dev.py test -m unit`；`… test -m integration`；`… test -- tests/unit/test_pytest_layering.py` | unit 310 / integration 23 / 分层机检 5 全绿，无 `PytestUnknownMarkWarning`。chain、e2e 两层的用例由 P0-5 与 P0-9 提供，此刻为 0 条属预期（`pytest -m chain --collect-only` 对空选择返回 rc=5，不能当判据） | mock |
| X8 | 进度已同步 | `uv run python scripts/sync_progress.py --check` | 退出 0，`docs/PROGRESS.md` 与 `docs/progress.html` 与 `progress.json` 一致 | mock |

## 1. 任务卡

### P0-0 统一命令入口与可复现环境（吸收旧 A0-0）

| 字段 | 内容 |
| --- | --- |
| 输入 | 无依赖。需要 `.env` 里可用的 `JWT_SECRET_KEY`（`d8f1563` 后缺失即拒绝启动） |
| 输出 | `scripts/dev.py`（新，跨平台统一入口：`doctor/up/down/ps/logs/migrate/test`；`seed` 顺延到 P1——种开发数据要先有上传链路，现在写只会是空壳命令）、`pyproject.toml`（注册 `unit/integration/chain/e2e/slow` marker）、`tests/conftest.py`（目录即分层的自动补标）、`.env.example`（删死键 `AGENT_ENABLED`/`ENTAILMENT_BACKEND`，补 `APP_ENV`，`AICORE_INTERNAL_TOKEN` 标为 P0-7 预留）、`.gitattributes`（`* text=auto eol=lf` + 二进制不转换）、`docs/refactor/p0-environment.md`（新，从零启动序列 + §3 实跑记录表） |
| 依赖 | 无 |
| 验收 | X7；按 `p0-environment.md` §2 从空仓库到 `/health` 200 全程可复制执行，且 §3 表格填完 |
| 等级 | real（启动序列必须**实跑**，不是照抄文档） |
| 规模/风险 | S–M / 需要 Docker Desktop；Windows 上 bind mount 权限与换行是第一坑，故 `.gitattributes` 必进本卡 |
| 当前状态 | 2026-10-09：脚本与分层已落且过单元级验证（9 项新增用例）；**本机未安装 Docker Desktop**，`dev.py doctor` 实测 exit=1，§2 的 up/health/migrate 尚未实跑，故 `status=in_progress`、`evidence=mock`，不标 done |

### P0-1 Go 服务骨架

| 字段 | 内容 |
| --- | --- |
| 输入 | P0-0；`02` §1 目录律、`02` §2 进程表、`01` §6 兼容语义 |
| 输出 | `server/go.mod`、`server/cmd/api/main.go`、`server/cmd/worker/main.go`（先只起健康检查与空循环）、`server/internal/httpapi/{router.go,middleware.go,envelope.go,checks.go}`、`server/internal/observability/{logging.go,trace.go}`、`server/internal/config/config.go`、`server/Dockerfile`。行为：Chi 路由 + `log/slog` JSON + `trace_id` 注入 + `{"detail": ...}` 错误信封 + `/api/v1/health`、`/api/v1/ready`（PG ping） |
| 依赖 | P0-0 |
| 验收 | X1；`cd server && go vet ./... && go test ./...` 绿 |
| 等级 | mock（单测）+ real（compose 起服务后 `/ready` 200） |
| 规模/风险 | M / `/ready` 若沿用 Python 侧三依赖探活语义（PG/Redis/Milvus）需与 `01` #2 一致，别让前端或监控脚本发现语义漂移 |
| 当前状态 | 2026-10-09：骨架已落，`gofmt`/`go vet`/`go test` 本地全绿（16 项 Go 用例：信封形状、503 失败带 `detail`、单项超时、trace 透传、panic 兜底、配置 fail-fast）。语义对齐已写进测试：`database` 键名、`timeout after Ns`、404/405 用 FastAPI 同款文案。real 级（compose 起服务 + `/ready` 200）待 Docker → `in_progress`、`evidence=mock` |

### P0-2 Schema 基线与非破坏性收编（吸收旧 A0-2 的只读核查）

| 字段 | 内容 |
| --- | --- |
| 输入 | 存量 PG 库（可能无 `alembic_version`）；`05` §1/§2/§4 |
| 输出 | `scripts/audit_schema.py`（新，只读：表集合、时间列语义、有无 `alembic_version`）+ `docs/refactor/schema-baseline.json`、`scripts/probe_timestamps.py` + `docs/refactor/timestamp-audit.md`、`server/migrations/000001_baseline.up.sql`/`.down.sql`（把**现有**结构登记为基线，纯 `CREATE TABLE IF NOT EXISTS` 或 `-- 已存在，仅登记`，禁止 DROP）、`server/migrations/README.md`（后续 schema 唯一来源） |
| 依赖 | P0-0（需容器） |
| 验收 | X6；报告能回答：现库存不存在 `alembic_version`？实际表集合？每表时间列判定？基线迁移在**新空库**与**存量库**上都能幂等执行 |
| 等级 | real |
| 规模/风险 | M / **风险高在存量库**：`create_all` 建出的库无版本行，`d8f1563` 后 Python 侧已拒绝启动，必须在本卡给出人工补基准版本的操作步骤（否则开发环境起不来） |
| 当前状态 | 2026-10-09 部分：`scripts/audit_schema.py` 落地，两模式分离且不互相冒充——`--check-baseline`（离线，审 `.sql` 是否非破坏/幂等/down 配对）与 `--live`（只读连库，出 `schema-baseline.json`：表集合、`alembic_version` 三态、列级 diff、索引与约束分查、会话时区）。判定逻辑 19 项单测，含"两套类型命名不是漂移""注释里的 DROP 不算 DDL"这类会把核查废掉的噪声点。本机 `--check-baseline` 如实返回 1（`server/migrations/` 还空着）。**基线文件不在没有真库时生成**：05 §1 末与 §2.2 明确"由核查出的实际结构生成，不由 ORM 生成"，用 ORM 声明冒充只会把已知漂移（`ix_paper_nodes_id` 缺失、`filename` 是 unique index 非 constraint）洗掉。`probe_timestamps.py` 同样留到真库：探针法/分布法/交叉法三种判定全都要往库里写或读，没有库时它只能产出假结论 |

### P0-3 Go 数据访问层

| 字段 | 内容 |
| --- | --- |
| 输入 | P0-2 基线；`users` 表结构 |
| 输出 | `server/sql/queries/*.sql` + `server/sqlc.yaml` + 生成的 `server/internal/db/*`、pgx pool 初始化、`Makefile` 或 `scripts/dev.py gen` 保证 `sqlc generate` 可复现 |
| 依赖 | P0-2 |
| 验收 | `cd server && sqlc generate && git diff --exit-code`（生成物无漂移）+ `go test ./internal/db/...` |
| 等级 | mock |
| 规模/风险 | S / 生成物是否入库需决策：建议**入库**（CI 不装 sqlc 也能构建），以 `--check` 式 diff 保一致性 |
| 当前状态 | 2026-10-09：**K2 已落地**——`server/sql/queries/users.sql`（3 条）+ `server/sqlc.yaml` + 生成的 `internal/db/{db,models,users.sql}.go` 全部入库；`internal/db/pool.go` 手写连接池（启动即 Ping，空串拒绝，`PoolOptions` 故意不放没人执行的 timeout 旋钮）；入口是 `uv run python scripts/dev.py gen [--check]`，sqlc 版本钉 `v1.30.0`，本机版本对不上就拒绝生成（跨版本重生成会让 diff 门禁以"你的改动有问题"的名义红）。8 项 Go 用例锁住三类可机检的东西：SQL 文本、参数顺序与个数、生成字段集合；其中 `GetUserByID` 不选 `password_hash` 这条是安全边界，不靠 handler 记得剔除。**未 done 的原因只有一条**：schema 源是 `server/sql/schema.sql` 这份临时参照（形状来自 ORM 声明，本机无 PG 无法核查），P0-2 出真基线后要把 `sqlc.yaml` 的 schema 指到 `migrations/` 并重跑 gen——字段真有变，那次 diff 就是答案 |

### P0-4 契约目录（含 429 信封定案）

| 字段 | 内容 |
| --- | --- |
| 输入 | `01` §3 的 25 条对外契约表与"前端实际依赖 13 条"、`02` §3 端点与请求体 |
| 输出 | `contracts/openapi.yaml`（Go 对浏览器：13 条在用 + `health/ready/metrics`）、`contracts/ai-execution.schema.json`（`execute`/`executions` 请求响应）、`contracts/error-codes.md`（9 个内部码 + `retryable` + HTTP 映射）、`contracts/table-acl.md`（`02` §6.2 表级写入矩阵的可校验形式）、`scripts/check_contracts.py`（新，结构校验：引用完整、路径与前端实调集合一致） |
| 依赖 | ~~P0-1（骨架形状）~~ → 无（2026-10-09 摘除：本卡只取 P0-1 的 detail 信封形状，该形状已在 `server/internal/httpapi/envelope.go` 落地并有 Go 单测；把 P0-1 的 real 级缺口（Docker）算成契约的阻塞项，会让一张已验完的卡永远不能 done） |
| 验收 | X3；并**在本卡内定案** 429 用 `{"detail": ...}` 还是保持现实现（决策影响 `useChat.ts`/`AuthPanel`），结论写进 `openapi.yaml` 与本文件 §3 |
| 等级 | mock |
| 规模/风险 | M / 契约先于实现锁定，否则 P1 会变成"边写边改架构"（违反原则③） |
| 当前状态 | **done（2026-10-09）**：五件产物齐（`contracts/{openapi.yaml,ai-execution.schema.json,error-codes.md,table-acl.md}` + `scripts/check_contracts.py`），X3 本机 pass 且每条规则都有负向用例。抽取器现场数出前端实调恰为 13 条，与 `01` §3 口径一致；顺带查实 `01` #20 的出处行号已漂（文档写 `:207`，实为 `useDocuments.ts:192`）、#13 WS 已从 `useChat.ts` 移入 `useWebSocket.ts`。K1/K4 同日定案并落进代码，契约里的 As-Is 例外（429 `{"error": ...}`、422 数组）已删除，`info.x-pending-decisions` 改为 `info.x-decisions` 记录 |

### P0-5 跨语言契约测试骨架

| 字段 | 内容 |
| --- | --- |
| 输入 | P0-4 契约 |
| 输出 | `tests/contract/test_go_vs_python.py`（新）：同一请求分别打 Python 现实现与 Go 骨架，比对错误信封形状、`/health` `/ready` 字段、JWT claims 集合；`tests/conftest.py` 增加 `chain` 级 fixture（compose 起服务、随机端口、函数级隔离，**不 mock**） |
| 依赖 | P0-1、P0-4 |
| 验收 | `uv run pytest -m chain -k contract` 绿（此时允许 Go 侧只有 health/auth 端点，其余以"未实现即跳过"的显式白名单标注，不伪装通过） |
| 等级 | real |
| 规模/风险 | M / 用例必须断言**结构与字段**，不断言业务文本 |

### P0-6 认证垂直切片（P0 的唯一业务切片）

| 字段 | 内容 |
| --- | --- |
| 输入 | `backend/core/auth.py` 现状语义（`d8f1563`）：token `type` 分型、角色以 DB 为准、`ADMIN_INVITE_CODE` 未配置则禁 admin 注册、`JWT_SECRET_KEY` 无默认值；P0-3 数据层 |
| 输出 | `server/internal/auth/{jwt.go,password.go,handler.go,service.go}`、`scripts/export_pbkdf2_golden.py`（新，从真实库导出 N 条哈希做 golden vectors，**不含密码与盐明文**）、`server/migrations/000002_auth_compat.*.sql`（仅在需要补列时） |
| 依赖 | P0-3、P0-4 |
| 验收 | X4、X5；`cd frontend && npm run typecheck` 仍 0 error（Go 侧响应形状与前端一致） |
| 等级 | real（Python↔Go 互验 token 必须真实跑） |
| 规模/风险 | L / 最高风险是 PBKDF2 编码差异（标准 vs urlsafe b64、盐长度、迭代数）。**Go 接管 `users` 的前置条件就是 X5 全绿**，未过则切片停在"只签发不接管"状态 |

### P0-7 ai-core 内部执行面

| 字段 | 内容 |
| --- | --- |
| 输入 | `02` §3 端点与请求体、§3.4 幂等/取消/超时/租约语义、`backend/services/agent_runner.py` 等现有可复用能力 |
| 输出 | `backend/internal_api/{router.py,schemas.py,registry.py,executions.py}`（新：`/internal/v1/ai/execute`、`POST /executions`、`GET /executions/{id}`、`GET /executions/{id}/result`、`POST /executions/{id}/cancel`、`healthz/readyz`）、`task_type` 注册表（P0 只接 `PARSE_PAPER`、`INDEX_PAPER` 两种，内部调用现有 `document_loader`/`milvus_writer`）、`AICORE_INTERNAL_TOKEN` 校验中间件、`ai_executions` 表迁移（出自 `server/migrations/`，Python 侧只读写自己那张表）、compose 中 `ai-core` **不发布宿主端口** |
| 依赖 | P0-4 |
| 验收 | `uv run pytest -m chain -k ai_executions`：提交→轮询→领取结果，重复 `task_id` 不重跑模型（幂等），`cancel` 后过期结果被丢弃；`GET /internal/v1/ai/healthz` 无 token 时 401 |
| 等级 | real |
| 规模/风险 | L / `PARSE_PAPER` 若走真实 LLM/embedding 需密钥；无密钥时以固定小 PDF + 本地 embedding 的降级路径验结构，并在 `progress.json` 标 `needs_secret: true` 与未验段落 |
| 当前状态 | 2026-10-09 推到 mock 级上限：`backend/internal_api/{router,schemas,registry,executions,codes,auth,__init__}.py` 七件挂上 7 条 `/internal/v1/ai` 路径；`AICORE_INTERNAL_TOKEN` **未配置即拒绝**（比较走 `hmac.compare_digest`），healthz/readyz 复用 `backend/api/health.py` 不另造探活。§3.4 三条语义都有断言兜着：幂等——假 loader 记调用次数，重复 `task_id` 与重复 `(run_id, idempotency_key)` 两条索引各自命中且次数恒为 1；取消——`succeed()` 见 `cancelled` 返回 None，`/result` 于是 409 带 `errors[].code=CANCELLED`，与"尚未结束"那个 detail-only 的 409 靠 code 分开；超时——deadline 已过不起跑、置 failed 并仍写 `usage{0,0,0}`（504 `MODEL_TIMEOUT`）。错误体 `{"detail","errors[]"}`：`detail` 让全仓仍只有一种信封，`errors[].code` 让 Go 不解析文本；九码由用例与 `contracts/error-codes.md` §1 及 schema 的 `ErrorCode` 三方逐码比对；实现也被钉在契约上——`x-endpoints` 的 7 条与真实注册路径一一对应、注册类型集合等于 `x-p0-registered-task-types`、`/internal/` 不出现在 `openapi.yaml`（内部面不被 `check_contracts.py` 看见，这三条是它唯一的门禁）。**未 done 的两件事都要真环境**：`ai_executions` 迁移出自 `server/migrations/`（P0-2 得先从实际库结构抄基线），compose 里"ai-core 不发布宿主端口"是 P0-8 的文件改动；所以 `uv run pytest -m chain -k ai_executions` 本机收集 0 项，如实 `not_run`。`BUDGET_EXCEEDED` 暂只存在于码表与契约，拦截随 P1 的 LLM 任务类型落地 |

### P0-8 compose 与跨环境实跑

| 字段 | 内容 |
| --- | --- |
| 输入 | P0-1、P0-6、P0-7 |
| 输出 | `docker-compose.yml`（新增 `go-api`/`go-worker`/`ai-core` 服务；`backend` 服务改为 `ai-core` 角色并去掉宿主端口）、`nginx/nginx.conf`（`/api/` upstream 切 `go-api`；`TRUST_PROXY_HEADERS` 相关头部保持 `d8f1563` 语义）、`.env.example` 补 Go 侧变量、`docs/refactor/p0-environment.md` 更新为含 Go 的完整序列 |
| 依赖 | P0-1、P0-6、P0-7 |
| 验收 | X1、X2；**在 Windows + Docker Desktop 上实跑**并把结果记进 `progress.json`（Linux CI 复跑同一序列作为交叉证据） |
| 等级 | real |
| 规模/风险 | M / 切换 upstream 是 P0 里唯一会影响现网可用性的动作：保留"一条配置回退到 Python"的回滚路径（`04` §5），且必须在切换前后各跑一次 X2 与前端手测 |

### P0-9 P0 端到端演示与退出复核

| 字段 | 内容 |
| --- | --- |
| 输入 | 上述全部 |
| 输出 | `tests/e2e/p0-auth.spec.ts`（Playwright，新）+ `frontend/package.json` 的 `test:e2e` 脚本、`docs/refactor/p0-demo.md`（§2 的 30 秒演示脚本）、`docs/progress.json` 里 X1–X8 的状态与证据等级收口 |
| 依赖 | P0-8 |
| 验收 | X2、X8 + `cd frontend && npm run test:e2e` 在 Go 后端全绿；`uv run pytest -q` 原 307 项保持绿 |
| 等级 | e2e |
| 规模/风险 | M | 

**FE-1（2026-10-09 指令插入，不在原 P0 序列里）**：前端结构重构。它不改后端也不改契约，
所以不进下面的依赖图；契约的「前端实调集合」在重构前后都是同一批 18 个操作。

| 字段 | 内容 |
| --- | --- |
| 输入 | 指令「前端要重构，先按核心原则把前端结构做完整做完善」+ `10-frontend-structure.md` §1 缺陷表 F1–F11 |
| 输出 | `frontend/src/api/` 七件（types/token/events/http/sse/ws/client）、六个 `composables/*` 统一模块单例、`utils/{dialog,errors,fileIcon}.ts`、`scripts/check_frontend.py` 与其负向用例；删除 `services/`、`MessageBubble.vue`、`frontend/style.css`、axios |
| 依赖 | 无 |
| 验收 | `10` §4 的 FE-a…FE-e：`npm run typecheck`、`npm run build`、`check_frontend.py`、`check_contracts.py`、`sync_progress.py --check` 全部退出 0 |
| 等级 | mock。浏览器级 FE-f 属 P0-9 的 X7；本机无 Docker/PG/LLM key，不拿静态检查冒充端到端 |
| 规模/风险 | L / 中：一次性替换请求边界与状态层，风险全在运行时等价性，只能由 P0-9 收口 |

## 2. 依赖顺序与里程碑

```
P0-0 ─→ P0-1 ─→ P0-4 ─→ P0-5
  │      └→ P0-2 ─→ P0-3 ─→ P0-6 ─┐
  └─────────────────→ P0-7 ───────┴→ P0-8 ─→ P0-9
```

| 里程碑 | 覆盖卡 | 到达时的可演示状态 |
| --- | --- | --- |
| M0.0 骨架可运行 | P0-0、P0-1 | `compose up` 后 Go 的 `/api/v1/health` 与 `/ready` 返回 200 |
| M0.1 契约锁定 | P0-4、P0-5 | `check_contracts.py` 绿；跨语言契约测试跑在真实容器上 |
| M0.2 数据基线 | P0-2、P0-3 | 基线迁移在空库与存量库上都幂等；`sqlc generate` 无 diff |
| M0.3 第一条垂直切片 | P0-6 | 浏览器经 Go 完成注册/登录/me；旧密码哈希可被 Go 验证 |
| M0.4 P0 收口 | P0-7、P0-8、P0-9 | X1–X8 全绿；`ai-core` 只内网可达；Playwright 演示通过 |

可独立提交的顺序：**P0-0 → P0-1 → P0-4 → P0-2 → P0-3 → P0-5 → P0-6 → P0-7 → P0-8 → P0-9**。
（P0-4 提前到 P0-2 之前：契约先于数据层，避免 P1 期间改契约。）

## 3. 决策记录（K1–K4 已于 2026-10-09 定案，D1–D3 待拍）

| # | 决策 | 结论与落点 | 状态 |
| --- | --- | --- | --- |
| K1 | 429 错误信封：统一到 `{"detail": ...}` 还是保留现实现的 `{"error": ...}` | **统一为 `detail`**。落点 `backend/core/exceptions.py:rate_limit_exceeded_handler`。**2026-10-09 更正**：先前说"要改前端两处"是推测，现场核查后是**零改动**——全仓前端不读 `.error` 响应字段、不按 429 分支（`api.ts:19` 只特判 401，`useAuth.ts:40/51` 只读 `data.detail`）。踩到的坑：handler **必须写成同步**，`SlowAPIMiddleware` 走 `sync_check_limits()`，一遇协程 handler 就退回 slowapi 自带的 `{"error": ...}`；且 429 路径不执行 `_inject_headers()`，`X-RateLimit-*` 得在 handler 里自己拼 | 已落地，用例 `tests/integration/test_rate_limit_enforcement.py` |
| K2 | `sqlc` 生成物是否入库 | **入库**：`server/sql/queries/*.sql` + `sqlc.yaml` + 生成代码一起提交，CI 用 `sqlc generate` 后的 `git diff --exit-code` 保证一致性，不要求 CI 装 sqlc | 定案，落点在 P0-3 |
| K3 | P0-8 切 nginx upstream 的时机 | **放在 P0-8 末、P0-9 之前**，且切前完成 X5。理由：只有认证切片可用才谈得上"Go 是唯一入口"，否则 X2 无法演示 | 定案，落点在 P0-8 |
| K4 | 422 校验失败：Go 复刻 FastAPI 的 `{"detail": [ {loc,msg,type} ]}` 数组，还是降级为 400 + 字符串 `detail` | **降级为 400 + 字符串**。落点 `request_validation_error_handler`。理由：chi 不会天然产生那个数组，为复刻它而写一套校验错误格式化器，正是原则④禁止的无关工作量；前端从不按 422 分支 | 已落地，用例 `tests/integration/test_error_envelope.py` |

> `contracts/openapi.yaml` 的 `info.x-decisions` 是本表的机器可读副本；两处不一致时以本表为准（K 项属流程决策，不属响应 schema）。

## 4. P0 明确不做

不迁移 13 条业务接口中的其余 12 条（属 P1）· 不做 chunk 可信化与 `paper_chunks`（属 P2）·
不做 Frontier/ResearchRun/ResearchTask（属 P3）· 不动 `upload_jobs.py`（P1 由 Go 编排取代）·
不做 `git mv backend → ai-core`（决策 Q2 + `08` §5）· 不改前端框架 · 不改 `backend/rag/*` 的算法实现 ·
不把 `≥95%/≥90%` 设成门禁（决策 Q8）。
