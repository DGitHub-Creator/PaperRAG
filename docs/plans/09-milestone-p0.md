# 09 — P0 任务清单：架构骨架与契约（文件级）

> 文档性质：实施计划/运行参考。文中早期实跑与现状数字是 dated 记录，不自动代表当前工作区。
> 当前实现见 [13](../reference/13-frontend-backend-architecture.md)，状态见 [progress.json](../progress.json)，启动见 [README](../../README.md)。

> **性质**：待你确认的实施计划。按 `08` §1 原则③，本文件获得确认后才动代码。
> **目标**：搭起目标架构的骨架与契约，并跑通**第一条垂直切片**（浏览器 → Go 注册/登录/me）。
> **不写业务功能迁移**（那是 P1），**不碰 chunk 可信化**（那是 P2）。
> 基线：`main @ 106f17dd`（前端与鉴权安全修复已在 `996cf777` / `335aeb7e` 落地）。
> 规模：solo 15–20h/周，P0 约 2–2.5 周（W1–W2）。每张卡一个独立提交，前缀 `feat(p0):` / `test(p0):` / `docs(p0):`。
>
> ⚠️ **本文件只放卡片定义（输入 / 输出 / 依赖 / 验收 / 等级 / 规模），不放日志。**
> 卡片与退出标准的**状态与证据**以 [`../progress.json`](../progress.json) 为准（机检 `sync_progress.py --check`）；
> "哪一轮做了什么、实跑读数、踩了什么坑"在 [`../WORKLOG.md`](../WORKLOG.md)；
> 代码层问题与处置在 [`12-known-code-issues.md`](12-known-code-issues.md) 台账。

## 0. 退出标准（全部可机检）

> **状态与读数不在本表**：跑 `uv run python scripts/sync_progress.py --check`，它给出 pass/fail/not_run 的条数；
> 每条的 `result` 与 `evidence_note` 在 `progress.json` 里。**别把数字手抄进文档**——本节的旧读数已过期过四次
> （unit 310 → 458 → 490 → 527；契约 18 → 21 个操作），这就是为什么这里只写判据、不写结果。
> `fail` 与 `not_run` 要分开读：前者是**已判定且不合格**，后者是**还没判**。

| # | 标准 | 判定命令（仓库根执行，除非注明） | 期望输出 | 等级 |
| --- | --- | --- | --- | --- |
| X1 | 骨架能起来 | `uv run python scripts/dev.py infra` 起中间件，宿主**源码**起 `ai-core`（`dev.py serve`）与 `go-api`（`dev.py go-serve`），再 `curl http://localhost:8080/api/v1/health` 与 `/api/v1/ready` | 两条均 200，且 `/ready` 的 **PG 与 Redis** 依赖探活通过（两个键都要在、都要 ok）。<br>⚠️ 判据于 2026-10-13 从「`compose ps` 里三个应用服务 healthy」改写为上面这条（容器只跑中间件）；**改写后 X1 不再证明编排层**，它证明的是"进程在真机源码形态下能起来并互相打通"。编排证据只剩 `docker-compose.prod.yml` 那一份，属部署阶段（台账 C29） | real |
| X2 | Go 是唯一公开入口 | `uv run python scripts/check_nginx_routes.py`（默认读三份：`nginx/nginx.conf`、`docker-compose.yml`（判 R5）、`docker-compose.prod.yml`（判 R4）） | 所有 `/api/` upstream 指向 `go-api`；无指向 `ai-core` 的 location；`ai-core` 不对外可达。规则拆解：R1 `/api/` 必须指 `go-api`、R2 任何 location 不得指向 `ai-core`（含藏在 upstream 里）、R3 不得有 `/internal` 前缀的对外 location、R4 端口隔离。<br>⚠️ **两处口径随 2026-10-13 定案改写**：①R4 在**源码形态**下的等价判据是「`ai-core` 只绑 `127.0.0.1`、不对外监听」，prod compose 那份仍按端口判——脚本要对两份文件分别按各自形态判，否则 R4 会变成一条**永远找不到对象的空规则**（空规则比红规则危险）；②"运行中的 nginx 与配置一致"在 dev 路径上**没有承载物**（本机不跑 nginx 容器），运行时一致性只能等部署阶段验，所以 level 留在 **e2e** 是诚实的，别当成"P0-8 一跑就升 real" | e2e |
| X3 | 契约已锁定且有测试 | `uv run python scripts/check_contracts.py` | 退出 0：OpenAPI 覆盖 13 条在用接口 + 探针 + Go 自助面（**操作数现场取**：`grep -c operationId: contracts/openapi.yaml`）；`ai-execution.schema.json` 的 `code` 枚举与 `error-codes.md` 逐字一致；`table-acl.md` 无未标过渡期的双写；前端实调集合与契约**双向**吻合。<br>⚠️ 它**不校验服务侧**：契约声明的 `/api/v1/health`、`/api/v1/ready` 只有 Go 满足（Python 的 health 路由不带该前缀），`/metrics` 三不管——这类盲区记台账 C31，**别把 rc=0 读成"契约与实现一致"** | mock |
| X4 | 认证垂直切片可用且跨语言互验 token | **以 `progress.json` 的 X4 为准**：`uv run python scripts/export_jwt_golden.py --check && go -C server test ./internal/auth/... && uv run pytest -m chain -k go_auth` | Go 单测绿；对同一份 `users` 行，Python 签发的 token 能被 Go 校验、Go 签发的能被 Python 校验（golden vectors 双向 **+ chain 级进程互跑**）。<br>⚠️ 三段是 `&&` 不是 `+`；开头那段 `--check` 是加固——Go 的测试读的就是这份 golden 文件，文件漂了而测试还绿等于什么都没证明。**收 0 项时 pytest 返回 rc=5，不是 0，不能算绿** | real |
| X5 | Go 能验旧密码哈希（接管 `users` 的前置） | **以 `progress.json` 的 X5 为准**：`uv run python scripts/export_pbkdf2_golden.py && go -C server test ./internal/auth/... -run TestVerifyLegacyHash` | golden 向量全部通过后才允许 Go 接管 `users`。向量口径：**不含明文口令、也不含真库 `password_hash`**——口令由 `vector_id` 按文件里的 `password_rule` 重建，真库只在 `--from-db` 下贡献形状统计。<br>⚠️ 命令里**必须带包路径** `./internal/auth/...`：`server/` 根目录没有 Go 文件，少写它就 `no Go files` → **rc 恒为 1，与测试是否存在无关**，即"这条判据永远不可能变绿"（台账 C22）。<br>⚠️ **`real` 那一档仍开着**：`--from-db` 的真库形状统计（迭代数/盐长分布、**是否残留 bcrypt 族**）因原真库随数据卷消失而无法执行（C20）。Go 不实现 bcrypt（无对象可验，引依赖就是死代码），处置是显式拒绝 + `family=bcrypt` 的 WARN 日志；**P1 接管 `users` 前必须先跑一次 `--from-db`** | mock→real |
| X6 | Go 不重复建表，基线迁移非破坏且幂等 | **以 `progress.json` 的 X6 为准**：`uv run python scripts/audit_schema.py --check-baseline`；幂等那条用「临时库法」人工实跑（`pg_dump --schema-only \| psql -d <临时库>` 复制真库结构，再把 `000001_baseline.up.sql` 连跑两遍，两次都应 exit 0 且表数不变） | 基线迁移为**非破坏性**（无 DROP）；空库与存量形态上重复执行结果一致；`schema_migrations` 版本与设计一致（**待执行器**）。<br>⚠️ 三条口径：①`--check-baseline` 只校验**文件形态**，内容比对是另一条命令 `--verify-columns`（快照缺 `columns` 时如实 exit 2，这个行为要保留）；②~~`cd server && migrate -path migrations …`~~ **这一半今天跑不了**——golang-migrate 从未接线（PATH 无 `migrate`、`go.mod` 无该依赖、`dev.py migrate` 实为容器内 `alembic upgrade head`），残余缺口记台账 C18 / 决策 D8，落 P0-8；③**「存量库幂等」的原对象已永久失去**（C20），只能用"alembic 建出的库"这一存量形态近似，**不等于**当年那个 `create_all`+alembic 混合库 | real |
| X7 | 测试分层可用（marker 已注册且目录即分层） | `uv run python scripts/dev.py test -m unit`；`… test -m integration`；`… test -- tests/unit/test_pytest_layering.py` | 三层全绿且无 `PytestUnknownMarkWarning`。**各层条数现场取**（`--collect-only -m <层>` 数 `::`），本行不写数字。chain 层自 P0-5 起有用例（`tests/chain/`），e2e 层由 P0-9 提供 | mock |
| X8 | 进度产物与真相源一致 | `uv run python scripts/sync_progress.py --check` | 退出 0，`docs/PROGRESS.md` 与 `docs/progress.html` 与 `progress.json` 一致 | mock |

## 1. 任务卡

### P0-0 统一命令入口与可复现环境（吸收旧 A0-0）

| 字段 | 内容 |
| --- | --- |
| 输入 | 无依赖。需要 `.env` 里可用的 `JWT_SECRET_KEY`（`335aeb7e` 后缺失即拒绝启动） |
| 输出 | `scripts/dev.py`（跨平台统一入口；**命令面现场取**：`grep -c sub.add_parser scripts/dev.py`。`seed`（种开发数据）顺延到 P1——要先有上传链路，现在写只会是空壳命令）、`pyproject.toml`（注册 `unit/integration/chain/e2e/slow` marker）、`tests/conftest.py`（目录即分层的自动补标）、`.env.example`（删死键 `AGENT_ENABLED`/`ENTAILMENT_BACKEND`，补 `APP_ENV`，`AICORE_INTERNAL_TOKEN` 标为 P0-7 预留）、`.gitattributes`（`* text=auto eol=lf` + 二进制不转换）、`docs/plans/p0-environment.md`（从零启动序列 + 实跑记录表） |
| 依赖 | 无 |
| 验收 | X7；按 `p0-environment.md` §2 从空仓库到 `/health` 200 全程可复制执行，且 §3 表格填完 |
| 等级 | real（启动序列必须**实跑**，不是照抄文档） |
| 规模/风险 | S–M / 需要 Docker Desktop；Windows 上 bind mount 权限与换行是第一坑，故 `.gitattributes` 必进本卡 |
| 当前状态 | 对应卡片状态以 [progress.json](../progress.json) 为准；历史过程见 [WORKLOG](../WORKLOG.md)。 |

### P0-1 Go 服务骨架

| 字段 | 内容 |
| --- | --- |
| 输入 | P0-0；`02` §1 目录律、`02` §2 进程表、`01` §6 兼容语义 |
| 输出 | `server/go.mod`、`server/cmd/api/main.go`、`server/cmd/worker/main.go`（先只起健康检查与空循环）、`server/internal/httpapi/{router,middleware,envelope,checks,redischeck,upstream}.go`、`server/internal/observability/{logging,trace}.go`、`server/internal/config/config.go`、`server/Dockerfile`（⚠️ 无任何验收路径引用它，处置属 C29）。行为：Chi 路由 + `log/slog` JSON + `trace_id` 注入 + `{"detail": ...}` 错误信封 + `/api/v1/health`、`/api/v1/ready`（**PG + Redis 两个探测键**，键名与 detail 文案与 `backend/api/health.py` 逐字对齐）+ 未迁移路径反代给 `PYTHON_UPSTREAM` |
| 依赖 | P0-0 |
| 验收 | X1；`cd server && gofmt -l . && go vet ./... && go test ./...` 绿 |
| 等级 | mock（单测）+ real（**宿主源码起 `go-api`** 后 `/ready` 200）——2026-10-13 定案：容器只跑中间件，real 那一档不以 compose 为承载物（C29） |
| 规模/风险 | M / `/ready` 的探测键集合必须与 Python 侧语义一致，别让前端或监控脚本发现语义漂移。**已知的不对称**：Go 探 `database`+`redis`，Python 还探 `milvus` |
| 当前状态 | 对应卡片状态以 [progress.json](../progress.json) 为准；历史过程见 [WORKLOG](../WORKLOG.md)。 |

### P0-2 Schema 基线与非破坏性收编（吸收旧 A0-2 的只读核查）

| 字段 | 内容 |
| --- | --- |
| 输入 | 存量 PG 库（可能无 `alembic_version`）；`05` §1/§2/§4 |
| 输出 | `scripts/audit_schema.py`（只读：表集合、时间列语义、有无 `alembic_version`；三种模式 `--check-baseline` / `--live` / `--verify-columns`）+ `docs/reference/schema-baseline.json`、`scripts/probe_timestamps.py` + `docs/reference/timestamp-audit.md`、`server/migrations/000001_baseline.{up,down}.sql`（把**现有**结构登记为基线，纯 `CREATE TABLE IF NOT EXISTS`，禁止 DROP）、`server/migrations/README.md`（后续 schema 唯一来源） |
| 依赖 | P0-0（需容器） |
| 验收 | X6；报告能回答：现库存不存在 `alembic_version`？实际表集合？每表时间列判定？基线迁移在**新空库**与**存量库**上都能幂等执行 |
| 等级 | real |
| 规模/风险 | M / **风险高在存量库**：`create_all` 建出的库无版本行，`335aeb7e` 后 Python 侧已拒绝启动，必须在本卡给出人工补基准版本的操作步骤。**基线文件不在没有真库时生成**（`05 §1` 末与 §2.2：由核查出的实际结构生成，不由 ORM 生成——用 ORM 声明冒充会把已知漂移洗掉） |
| 当前状态 | 对应卡片状态以 [progress.json](../progress.json) 为准；历史过程见 [WORKLOG](../WORKLOG.md)。 |

### P0-3 Go 数据访问层

| 字段 | 内容 |
| --- | --- |
| 输入 | P0-2 基线；`users` 表结构 |
| 输出 | `server/sql/queries/*.sql` + `server/sqlc.yaml` + 生成的 `server/internal/db/*`、pgx pool 初始化、`scripts/dev.py gen [--check]` 保证 `sqlc generate` 可复现 |
| 依赖 | ~~P0-2~~ → 无（摘除理由：本卡只取 P0-2 的基线 DDL 产物，该产物已落地并拿到 X6 的 real 证据；把 P0-2 未 done 的剩余项算成阻塞，会让一张已验完的卡永远不能 done） |
| 验收 | `uv run python scripts/dev.py gen --check`（生成物无漂移）+ `cd server && go test ./internal/db/...` |
| 等级 | mock |
| 规模/风险 | S / 生成物**入库**（K2：CI 不装 sqlc 也能构建），以 `--check` 式 diff 保一致性；sqlc 版本钉 v1.30.0，不匹配就拒绝生成。⚠️ **能力边界要记住**：sqlc 不把列默认值编码进 Go 类型，所以 `gen --check` 只能抓类型/可空性/列与表的存在性；DEFAULT 与 varchar 长度的机检是 `audit_schema.py --verify-columns` |
| 当前状态 | 对应卡片状态以 [progress.json](../progress.json) 为准；历史过程见 [WORKLOG](../WORKLOG.md)。 |

### P0-4 契约目录（含 429 信封定案）

| 字段 | 内容 |
| --- | --- |
| 输入 | `01` §3 的 25 条对外契约表与"前端实际依赖 13 条"、`02` §3 端点与请求体 |
| 输出 | `contracts/openapi.yaml`（Go 对浏览器：在用接口 + 探针 + Go 自助面）、`contracts/ai-execution.schema.json`（`execute`/`executions` 请求响应）、`contracts/error-codes.md`（9 个内部码 + `retryable` + HTTP 映射）、`contracts/table-acl.md`（`02` §6.2 表级写入矩阵的可校验形式）、`scripts/check_contracts.py`（结构校验：引用完整、路径与前端实调集合一致） |
| 依赖 | ~~P0-1（骨架形状）~~ → 无（摘除理由同 P0-3：本卡只取 detail 信封形状，它已在 `internal/httpapi/envelope.go` 落地并有单测） |
| 验收 | X3；并**在本卡内定案** 429 用 `{"detail": ...}` 还是保持现实现（影响 `useChat.ts`/`AuthPanel`），结论写进 `openapi.yaml` 与本文件 §3 |
| 等级 | mock |
| 规模/风险 | M / 契约先于实现锁定，否则 P1 会变成"边写边改架构"（违反原则③） |
| 当前状态 | 对应卡片状态以 [progress.json](../progress.json) 为准；历史过程见 [WORKLOG](../WORKLOG.md)。 |

### P0-5 跨语言契约测试骨架 + chain 级真实容器 fixture

| 字段 | 内容 |
| --- | --- |
| 输入 | P0-4 契约 |
| 输出 | `tests/chain/`：`_runtime.py`（地址解析 + preflight 策略，纯函数）、`conftest.py`（真库种子与两侧令牌）、`test_go_auth_cross_validation.py`、`test_contract_chain.py`、`test_go_read_sessions.py` ＋ `tests/unit/test_chain_runtime.py`。fixture 要求：真容器起中间件、两个应用**源码进程**、**不 mock**、函数级隔离 |
| 依赖 | ~~P0-1~~（摘除理由：本卡要的是"有一个能跑的 go-api 进程"，那已由 P0-6 交付并被用例真打过；P0-1 整体缺的是服务侧探测键与编排能力，与测试骨架无关）、P0-4 |
| 验收 | `uv run pytest -m chain -k contract` 绿。**"不伪装通过"要落成可证伪的三档**：①显式 `-m chain` 时基础设施不可达必须**红**（否则"全绿"可以是"一个都没跑"），被全量收集路过才 skip；②种子**直接写 PG**，不用被测面铺数据（否则接口坏了会以"铺数据失败"的形态报错）；③静态门禁带 `checked >= N` 兜"检查自己失效"。用例必须断言**结构与字段**，不断言业务文本 |
| 等级 | real |
| 规模/风险 | M / 判据选择器要与 `progress.json` 里的命令**逐字对得上**（`-k go_auth` / `-k contract` / `-k go_read` / `-k ai_executions`），否则"收 0 项 rc=5"会长期冒充"还没做" |
| 当前状态 | 对应卡片状态以 [progress.json](../progress.json) 为准；历史过程见 [WORKLOG](../WORKLOG.md)。 |

### P0-6 认证垂直切片（P0 的唯一业务切片）

| 字段 | 内容 |
| --- | --- |
| 输入 | `backend/core/auth.py` 现状语义（`335aeb7e`）：token `type` 分型、角色以 DB 为准、`ADMIN_INVITE_CODE` 未配置则禁 admin 注册、`JWT_SECRET_KEY` 无默认值；P0-3 数据层 |
| 输出 | `server/internal/auth/{jwt,password,handler,service,preferences,identify}.go`、`scripts/export_pbkdf2_golden.py` → `contracts/pbkdf2_golden.json`、`scripts/export_jwt_golden.py` → `contracts/jwt_golden.json`。**golden 文件口径**：不含明文口令、也不含真库 `password_hash`；向量是合成口令的摘要，口令由 `vector_id` 按文件里的 `password_rule` 重建；真库只在 `--from-db` 下贡献**形状统计**。`server/migrations/_auth_compat.*.sql` **不需要**（`users` 表已有全部列，按 `05 §2.6` 的"条件性预留不占号"，不建空文件） |
| 依赖 | P0-3、P0-4、A0-3 |
| 验收 | X4、X5；`cd frontend && npm run typecheck` 仍 0 error（Go 侧响应形状与前端一致） |
| 等级 | real（Python↔Go 互验 token 必须真实跑） |
| 规模/风险 | L / 最高风险是 PBKDF2 编码差异（标准 vs urlsafe b64、盐长度、迭代数）。**Go 接管 `users` 的前置条件就是 X5 全绿**，未过则切片停在"只签发不接管"状态。⚠️ 复刻现状时**照抄不顺手改好**（register 会 strip 而 login 不 strip、密码长度按**码点**、`role` 不做枚举校验、用户不存在与密码错同一个 401、重名 409 先于邀请码 403、detail 文案含中英混用），每条都要有用例钉住，且 detail 一律**由生产 handler 现跑取数** |
| 当前状态 | 对应卡片状态以 [progress.json](../progress.json) 为准；历史过程见 [WORKLOG](../WORKLOG.md)。 |

### P0-7 ai-core 内部执行面

| 字段 | 内容 |
| --- | --- |
| 输入 | `02` §3 端点与请求体、§3.4 幂等/取消/超时/租约语义、`backend/services/` 现有可复用能力（**实际接线的是 `document_loader` 与 `milvus_writer`，经 `core/dependencies.py` 的 `get_document_loader`/`get_milvus_writer` 取，见 `internal_api/registry.py:13`**；本行曾点名 `agent_runner.py`——该文件**不存在**，`backend/services/` 里只有 `agent.py`/`cache.py`/`conversation_storage.py`/`tools.py`/`upload_jobs.py`） |
| 输出 | `backend/internal_api/{router,schemas,registry,executions,codes,auth}.py`（`/internal/v1/ai/execute`、`POST /executions`、`GET /executions/{id}`、`GET /executions/{id}/result`、`POST /executions/{id}/cancel`、`healthz/readyz`）、`task_type` 注册表（P0 只接 `PARSE_PAPER`、`INDEX_PAPER`）、`AICORE_INTERNAL_TOKEN` 校验中间件（未配置即拒绝，比较走 `hmac.compare_digest`）、`ai_executions` 表迁移（`server/migrations/000002_*`，Python 侧只读写自己那张表）、**`ai-core` 不对外可达**（源码形态下的等价要求：只绑 `127.0.0.1`） |
| 依赖 | P0-4 |
| 验收 | `uv run pytest -m chain -k ai_executions`：提交→轮询→领取结果，重复 `task_id` 不重跑模型（幂等），`cancel` 后过期结果被丢弃；`GET /internal/v1/ai/healthz` 无 token 时 401 |
| 等级 | real |
| 规模/风险 | L / `PARSE_PAPER` 若走真实 LLM/embedding 需密钥；无密钥时以固定小 PDF + 本地 embedding 的降级路径验结构，并在 `progress.json` 标 `needs_secret: true` 与未验段落。⚠️ 内部面**不被 `check_contracts.py` 看见**，它唯一的门禁是三条机检：`x-endpoints` 的 7 条与真实注册路径一一对应、注册类型集合等于 `x-p0-registered-task-types`、`/internal/` 不出现在 `openapi.yaml` |
| 当前状态 | 对应卡片状态以 [progress.json](../progress.json) 为准；历史过程见 [WORKLOG](../WORKLOG.md)。 |

### P0-8 Go 服务接线与跨环境实跑（源码形态，不新增应用容器）

| 字段 | 内容 |
| --- | --- |
| 输入 | P0-1、P0-6、P0-7 |
| 输出 | `scripts/dev.py` 的 **Go 侧源码启动路径**（`go-serve`；`infra` 仍只管中间件）、`nginx/nginx.conf`（`/api/` upstream 切 `go-api`；`TRUST_PROXY_HEADERS` 相关头部保持 `335aeb7e` 语义）、`.env.example` 补 Go 侧变量、`docs/plans/p0-environment.md` 更新为「中间件容器 + 应用源码」的完整序列。<br>⚠️ **2026-10-13 定案**：原卡列的「compose 新增 `go-api`/`go-worker`/`ai-core` 三个服务」**取消**。随之 `docker-compose.yml` 里现存的 `backend`（16.5 GB 镜像）与 `nginx` 两个服务、`dev.py up` 这条命令、`server/Dockerfile`、`check_nginx_routes.py` 的 R4，都成为与定案冲突的**遗留物，按台账 C29 处置**（要么删、要么明确标注为"仅 prod/部署用，不参与任何验收"） |
| 依赖 | P0-1、P0-6、P0-7 |
| 验收 | X1、X2；**在 Windows + Docker Desktop 上实跑**并把结果记进 `progress.json`（Linux CI 复跑同一序列作为交叉证据）。⚠️ X1/X2 的判据已随定案改写，本卡按改写后的判据收 |
| 等级 | real |
| 规模/风险 | M / 切换 upstream 是 P0 里唯一会影响现网可用性的动作：保留"一条配置回退到 Python"的回滚路径（`04` §5），且必须在切换前后各跑一次 X2 与前端手测 |
| 当前状态 | 对应卡片状态以 [progress.json](../progress.json) 为准；历史过程见 [WORKLOG](../WORKLOG.md)。 |

### P0-9 P0 端到端演示与退出复核

| 字段 | 内容 |
| --- | --- |
| 输入 | 上述全部 |
| 输出 | `frontend/e2e/p0-auth.spec.ts`（Playwright，新。**原计划写 `tests/e2e/`，实做时改到 `frontend/e2e/`**：Node 从仓库根的 `tests/e2e/` 往上找不到 `node_modules`，`import '@playwright/test'` 直接解析失败——spec 必须待在工具链所在的那棵树里；`tests/e2e/` 因此仍归 pytest 的 e2e marker 层，今天 0 条，口径见 `07`）+ `frontend/playwright.config.ts` + `frontend/package.json` 的 `test:e2e` 脚本、`docs/plans/p0-demo.md`（§2 的 30 秒演示脚本）、`docs/progress.json` 里 X1–X8 的状态与证据等级收口 |
| 依赖 | P0-8 |
| 验收 | X2、X8 + `cd frontend && npm run test:e2e` 在 Go 后端全绿；`uv run pytest -q` 全量保持绿（**读数现场取**，本行不写数字） |
| 等级 | e2e |
| 规模/风险 | M / ⚠️ 两条要先探明：①本机能否装 Playwright 浏览器（无网/镜像受限就**如实记 `not_run`**，别用 mock 冒充）；②无头浏览器视口是 **0×0、截图不可用**（实测 `NATIVE_BROWSER_VIEWPORT_UNAVAILABLE`），若 Playwright 走同一引擎则像素级判据拿不到，只能算**结构级 e2e**，要如实写进证据等级 |
| 当前状态 | 对应卡片状态以 [progress.json](../progress.json) 为准；历史过程见 [WORKLOG](../WORKLOG.md)。 |

**FE-1（2026-10-09 指令插入，不在原 P0 序列里）**：前端结构重构。它不改后端也不改契约，所以不进依赖图。

| 字段 | 内容 |
| --- | --- |
| 输入 | 指令「前端要重构，先按核心原则把前端结构做完整做完善」+ `10-frontend-structure.md` §1 缺陷表 F1–F11 |
| 输出 | `frontend/src/api/` 七件（types/token/events/http/sse/ws/client）、`composables/*` 统一模块单例、`utils/{dialog,errors,fileIcon,theme}.ts`、`scripts/check_frontend.py` 与其负向用例；删除 `services/`、`MessageBubble.vue`、`frontend/style.css`、axios。**2026-10-14 起范围扩到整站页面**：`router/index.ts` 13 条懒加载路由 + `AppShell`/`AppRail`/`TopBar` 外壳 + `views/` 13 页 + `Icon.vue` 内联 SVG 图标集；设置页五个板块组件（`SettingsAccountBoard`/`ThemeBoard`/`PreferencesBoard`/`PasswordBoard`/`KnowledgeBoard`）+ `ToastHost`/`ConfirmHost` |
| 依赖 | 无 |
| 验收 | `10` §4 的 FE-a…FE-e：`npm run typecheck`、`npm run build`、`check_frontend.py`、`check_contracts.py`、`sync_progress.py --check` 全部退出 0 |
| 等级 | mock。浏览器级 FE-f 属 P0-9 的 X7；**不拿静态检查冒充端到端** |
| 规模/风险 | L / 中：一次性替换请求边界与状态层，风险全在运行时等价性，只能由 P0-9 收口 |
| 当前状态 | 对应卡片状态以 [progress.json](../progress.json) 为准；历史过程见 [WORKLOG](../WORKLOG.md)。 |

## 2. 依赖顺序与里程碑

```
P0-0 ─→ P0-1 ─→ P0-4 ─→ P0-5
  │      └→ P0-2 ─→ P0-3 ─→ P0-6 ─┐
  └─────────────────→ P0-7 ───────┴→ P0-8 ─→ P0-9
```

| 里程碑 | 覆盖卡 | 到达时的可演示状态 |
| --- | --- | --- |
| M0.0 骨架可运行 | P0-0、P0-1 | `dev.py infra` 起中间件后，**源码跑的** Go 进程 `/api/v1/health` 与 `/ready` 返回 200（2026-10-13 定案：不再是 `compose up`） |
| M0.1 契约锁定 | P0-4、P0-5 | `check_contracts.py` 绿；跨语言契约测试跑在真容器与两个真进程上 |
| M0.2 数据基线 | P0-2、P0-3 | 基线迁移在空库与存量形态上都幂等；`dev.py gen --check` 无漂移 |
| M0.3 第一条垂直切片 | P0-6 | 浏览器经 Go 完成注册/登录/me；旧密码哈希可被 Go 验证 |
| M0.4 P0 收口 | P0-7、P0-8、P0-9 | X1–X8 全绿；`ai-core` 只绑 `127.0.0.1`、不对外提供入口（源码形态下的等价要求）；Playwright 演示通过 |

可独立提交的顺序：**P0-0 → P0-1 → P0-4 → P0-2 → P0-3 → P0-5 → P0-6 → P0-7 → P0-8 → P0-9**。
（P0-4 提前到 P0-2 之前：契约先于数据层，避免 P1 期间改契约。）

## 3. 决策记录（K1–K4 已定案；待拍决策**以 `progress.json` 的 `decisions_pending` 为准**）

> ⚠️ **两个 D Namespace 别混**：`03` 里的 D1/D2/D3 指**功能断链**（公式检索、分层分块、元数据入库），
> 本节与 `progress.json` 里的 D1–D8 指**待拍决策**。

| # | 决策 | 结论与落点 | 状态 |
| --- | --- | --- | --- |
| K1 | 429 错误信封：统一到 `{"detail": ...}` 还是保留 `{"error": ...}` | **统一为 `detail`**。落点 `backend/core/exceptions.py:rate_limit_exceeded_handler`。⚠️ 两个坑：handler **必须写成同步**（`SlowAPIMiddleware` 走 `sync_check_limits()`，一遇协程 handler 就退回 slowapi 自带的 `{"error": ...}`）；429 路径不执行 `_inject_headers()`，`X-RateLimit-*` 得在 handler 里自己拼 | 已落地，用例 `tests/integration/test_rate_limit_enforcement.py` |
| K2 | `sqlc` 生成物是否入库 | **入库**：`server/sql/queries/*.sql` + `sqlc.yaml` + 生成代码一起提交，CI 用 `dev.py gen --check` 保证一致性，不要求 CI 装 sqlc（版本钉 v1.30.0，不匹配就拒绝生成） | 定案，落点在 P0-3 |
| K3 | P0-8 切 nginx upstream 的时机 | **放在 P0-8 末、P0-9 之前**，且切前完成 X5。理由：只有认证切片可用才谈得上"Go 是唯一入口"，否则 X2 无法演示 | 定案，落点在 P0-8 |
| K4 | 422 校验失败：Go 复刻 FastAPI 的 `{"detail": [{loc,msg,type}]}` 数组，还是降级 | **降级为 400 + 字符串 `detail`**。落点 `request_validation_error_handler`。理由：chi 不会天然产生那个数组，为复刻它写一套格式化器正是原则④禁止的无关工作量；前端从不按 422 分支 | 已落地，用例 `tests/integration/test_error_envelope.py` |

> `contracts/openapi.yaml` 的 `info.x-decisions` 是本表的机器可读副本；两处不一致时以本表为准
> （K 项属流程决策，不属响应 schema）。

## 4. P0 明确不做

不迁移 13 条业务接口中的其余 12 条（属 P1）· 不做 chunk 可信化与 `paper_chunks`（属 P2）·
不做 Frontier/ResearchRun/ResearchTask（属 P3）· 不动 `upload_jobs.py`（P1 由 Go 编排取代）·
不做 `git mv backend → ai-core`（决策 Q2 + `08` §5）· 不改前端框架 · 不改 `backend/rag/*` 的算法实现 ·
不把 `≥95%/≥90%` 设成门禁（决策 Q8）。

⚠️ **这一节是机检对象**：`sync_progress.py --check` 按 `08 §2` 的阶段顺序律拦截"P0 未收口就开工 P1 的卡"，
所以把 P1 卡标 `in_progress` 会直接红。要提前开工 P1，必须先由用户明确推翻顺序律——**别在实现里顺手绕开**。

## 5. 与产品愿景的关系

> 对照 [11-product-vision.md](../rules/11-product-vision.md)。**P0 属工程架构轴，不产出任何产品版本**
> （`11 §7`：两条轴编号不得混用）；产品级缺口集中记在 `11 §8`。

**已覆盖**：**只有两条架构前提，没有产品能力**。① `11 §2` 的三层能力演进要求"项目状态必须可持久、可查询、
可审计（L3）、模型输出必须被证据绑定后才算事实（L4）"——P0-4 的契约与 `table-acl.md`、P0-7 的
`evidence_candidates` 只作为**建议**上报，是这条的骨架形态；② `11 §4.4 Research Mission` 的**长期项目记忆**
与 `§6` 的 Go Research Engine——P0-1 的 `cmd/worker` 空循环与 `/ready` 是它的第一步（真正的 Run/Frontier 属 P3）。
另有 `11 §4.10` 隐含的可复现环境前提（P0-0）。

**未覆盖**：P0 **全部**产品能力——`11 §3` 五个入口 · `§4.1`–`§4.10` 十项能力 · `§5` 三个惊艳功能。
P0 里的 `auth` 切片是 §4.10 Workspace 的必要条件、不是它的实现。全部指向 `11 §8`。

**需拍板/冲突**：**有，两处**。① **P0 与 V1.0 的时序错位**：`11 §10` 要求 V1.0（可信学术 RAG）**先于** V2.0
完成，而 V1.0 的可信化依赖 **P2-1/P2-2**（chunk 真相层、公式索引）。也就是说**P0 结束时 V1.0 完成度仍是 0**，
这条关系必须在 `progress.json` 与对外表述里写明，否则"P0 完成"极易被读成"V1.0 完成"。选项 A：把 P2-1/P2-2
前移进 P0 序列；选项 B：V1.0 显式改为"在现有 Python 链路上先可信化"，P0 保持纯架构。
② **X1–X8 与产品验收无关，不得混淆**：X1–X8 全是架构/契约/进程门禁，**没有一条断言用户可感知的产品能力**；
`11 §3` 的五个入口在 P0 里没有任何退出标准。若把 X1–X8 全绿宣传为"产品可用"，即违反 `08` 原则②与
`11 §11` 的诚实口径。
