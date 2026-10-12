# 09 — P0 任务清单：架构骨架与契约（文件级）

> **性质**：待你确认的实施计划。按 `08` §1 原则③，本文件获得确认后才动代码。
> **目标**：搭起目标架构的骨架与契约，并跑通**第一条垂直切片**（浏览器 → Go 注册/登录/me）。
> **不写业务功能迁移**（那是 P1），**不碰 chunk 可信化**（那是 P2）。
> 基线：`main @ 106f17dd`（前端与鉴权安全修复已在 `996cf777` / `335aeb7e` 落地）。
> 规模：solo 15–20h/周，P0 约 2–2.5 周（W1–W2）。每张卡一个独立提交，前缀 `feat(p0):` / `test(p0):` / `docs(p0):`。

## 0. 退出标准（全部可机检；当前状态见 `docs/progress.json`，本节末行同步于 2026-10-12）

> **现状读数**（同步于 2026-10-12 本轮 P0-6 之后）：8 条里 **pass 5**（X3/**X5**/X6/X7/X8）、
> **fail 2**（X2 红在 `/api/` 还指向 Python；X4 的 Go 半侧已全绿，红在 `pytest -m chain -k go_auth` 收 0 项、rc=5）、
> **not_run 1**（X1，要 `docker compose up`）。此前本节写「当前状态一律 `not_run`」已失效，
> 上一版写的「pass 4 / fail 3」也已过期——**读数请用 `sync_progress.py --check` 的输出，别手抄本行**。
> `fail` 与 `not_run` 要分开读：前者是**已判定且不合格**，后者是**还没判**。

| # | 标准 | 判定命令（仓库根执行，除非注明） | 期望输出 | 等级 |
| --- | --- | --- | --- | --- |
| X1 | 骨架能起来 | `docker compose up -d` 后 `curl http://localhost/api/v1/health` 与 `/api/v1/ready` | 两条均 200；`compose ps` 里 `go-api`/`go-worker`/`ai-core` 为 healthy/running | real |
| X2 | Go 是唯一公开入口 | `uv run python scripts/check_nginx_routes.py`（默认同时读 `nginx/nginx.conf` 与 `docker-compose.yml`） | 所有 `/api/` upstream 指向 `go-api`；无指向 `ai-core` 的 location；compose 里 `ai-core` 不发布宿主端口。**2026-10-12 判定脚本已落**（`tests/unit/test_check_nginx_routes.py` 21 项，每条规则一正一篡改）；真配置今天**如实 exit 1**（R1：`/api/` 还指向 `backend`），这是 P0-8 的活，不是脚本缺陷。level 仍是 e2e：静态判定只证明"配置写对了"，运行中的 nginx 与配置一致要等 `docker compose up` | e2e |
| X3 | 契约已锁定且有测试 | `uv run python scripts/check_contracts.py` | 退出 0：OpenAPI 覆盖 13 条在用接口 + `health/ready`（共 18 个操作）；`ai-execution.schema.json` 的 `code` 枚举与 `error-codes.md` 逐字一致；`table-acl.md` 无未标过渡期的双写；前端实调集合与契约**双向**吻合。**2026-10-09 本机 pass**（`tests/unit/test_check_contracts.py` 16 项，含 11 项负向篡改用例；CI backend job 已挂本门禁）。K1/K4 已定案落地，契约只剩 `{"detail": ...}` 一种信封；K2/K3 已定案，落点分别在 P0-3/P0-8，见 §3 | mock |
| X4 | 认证垂直切片可用 | **判定命令以 `docs/progress.json` 的 X4 为准**：`uv run python scripts/export_jwt_golden.py --check && cd server && go test ./internal/auth/... && uv run pytest -m chain -k go_auth`（本行原先把两段写成 `A + B`，与 progress.json 的 `&&` 不一致，已按后者更正；前面那段 `--check` 是 2026-10-12 新加的——Go 的测试读的就是这份 golden 文件，文件漂了而测试还绿等于什么都没证明。expect 一字未改，属加固不属放水） | Go 单测绿；对同一份 `users` 行，Python 签发的 token 能被 Go 校验，Go 签发的能被 Python 校验（golden vectors 双向）。**2026-10-12 本轮：Go 半侧已全绿，整条仍 rc=5**——`server/internal/auth` 四件已落地，`go test ./internal/auth/...` 50 项 PASS；新增 `contracts/jwt_golden.json` 9 条（正 3 / 负 6），每条 `expect_accept` 由生产函数 `get_user_from_bearer_token` 现算（用只认一个用户的桩 db 跑**真函数**），`TestParseGoldenTokens` 逐条对上，`07` §兼容面表点名的三件事（type 语义 / 过期 / 错误 secret）各有向量。红点因此从"包不存在"移到 `pytest -m chain -k go_auth`：收 0 项、**rc=5**（不是 0，不能算绿），chain 层的容器 fixture 是 P0-5 的产出，且本机要先重建 Docker 环境（台账 C20）。两侧**结论不同**的两条轴写在 golden 文件的 `divergences` 段而不是塞进 vectors：缺 exp 的令牌 Python 收、Go 拒；alg 白名单 Go 写死 HS256 | real |
| X5 | 旧密码不被锁死 | **判定命令以 `docs/progress.json` 的 X5 为准**：`uv run python scripts/export_pbkdf2_golden.py && cd server && go test ./internal/auth/... -run TestVerifyLegacyHash`。⚠️ 本行原先写的是 `cd server && go test -run TestVerifyLegacyHash`——`server/` 根目录没有 Go 文件，那条命令 `no Go files` → `FAIL [setup failed]` → **rc 恒为 1，与测试是否存在无关**，即"这条判据永远不可能变绿"（台账 C22，已修） | golden 向量全部通过后才允许 Go 接管 `users`。**2026-10-12 本轮转 pass（实跑 rc=0）**：`contracts/pbkdf2_golden.json` 10 条向量（6 正 4 负），形状轴覆盖 `04` §风险表点名的三件事（标准 vs urlsafe base64、盐长 8/16/32、迭代数 40000/260000/310000）再加 UTF-8 口令；每条期望值由生产裁判 `backend/core/auth.py:verify_password` 现算，裁判不一致就拒绝导出。**文件里没有明文口令**：口令由 `vector_id` 按 `password_rule` 重建，真库 `password_hash` 有意不导出（`--from-db` 只取形状统计）。Go 侧 `internal/auth/password.go` 用标准库 `crypto/pbkdf2`（Go 1.24+，零新依赖），`hmac.Equal` 对上 `compare_digest`；重跑导出件逐字未变。反向那一半（Go 写、Python 验）也实跑取过证。<br>⚠️ **本条 pass 只覆盖 expect 那句话，`real` 那一档仍开着**：`--from-db` 的真库形状统计（迭代数/盐长分布、**是否还残留 bcrypt 族**）因原真库随 Docker 数据卷消失而无法执行（台账 C20），所以"库里还有没有 Go 验不了的行"没有答案。Go 侧不实现 bcrypt（无对象可验，引依赖就是死代码），处置是显式拒绝 + `family=bcrypt` 的 WARN 日志；**P1 接管 `users` 前必须先跑一次 `--from-db`** | mock→real |
| X6 | Go 不重复建表 | **判定命令以 `docs/progress.json` 的 X6 为准**：`uv run python scripts/audit_schema.py --check-baseline`；幂等那条用「临时库法」人工实跑（`pg_dump --schema-only \| psql -d <临时库>` 复制真库结构，再把 `000001_baseline.up.sql` 连跑两遍，两次都应 exit 0 且表数不变）。~~`cd server && migrate -path migrations -database $DATABASE_URL version`~~——**这一半今天跑不了**：golang-migrate 从未接线（PATH 上无 `migrate`，`server/go.mod` 无该依赖，`dev.py migrate` 实际执行的是容器内 `alembic upgrade head`）。所以本行此前写的命令与 progress.json 记录的命令**不一致**，已按后者更正；残余缺口记台账 C18（`schema_migrations` 版本与设计一致这一问要等执行器，落 P0-8/P1） | 基线迁移为**非破坏性**（无 DROP）；`schema_migrations` 版本与设计一致（**待执行器**）；alembic 与 golang-migrate 不冲突 | real |
| X7 | 测试分层可用（marker 已注册且目录即分层） | `uv run python scripts/dev.py test -m unit`；`… test -m integration`；`… test -- tests/unit/test_pytest_layering.py` | 三层全绿且无 `PytestUnknownMarkWarning`：**unit 458 / integration 57 / 分层机检 5**（2026-10-12 实测；本行此前写 unit 310 / integration 23，是 P0-4/P0-7/FE-1 之后没跟上的旧读数）。chain、e2e 两层的用例由 P0-5 与 P0-9 提供，此刻为 0 条属预期（`pytest -m chain --collect-only` 对空选择返回 rc=5，不能当判据） | mock |
| X8 | 进度已同步 | `uv run python scripts/sync_progress.py --check` | 退出 0，`docs/PROGRESS.md` 与 `docs/progress.html` 与 `progress.json` 一致 | mock |

## 1. 任务卡

### P0-0 统一命令入口与可复现环境（吸收旧 A0-0）

| 字段 | 内容 |
| --- | --- |
| 输入 | 无依赖。需要 `.env` 里可用的 `JWT_SECRET_KEY`（`335aeb7e` 后缺失即拒绝启动） |
| 输出 | `scripts/dev.py`（新，跨平台统一入口；**当前命令面 10 个子命令**：`doctor/up/infra/serve/down/ps/logs/migrate/test/gen`——本卡原先列的六项只是 P0-0 当时的面，`infra`/`serve` 由 2026-10-11 补、`gen` 由 P0-3 补；`seed` 顺延到 P1——种开发数据要先有上传链路，现在写只会是空壳命令）、`pyproject.toml`（注册 `unit/integration/chain/e2e/slow` marker）、`tests/conftest.py`（目录即分层的自动补标）、`.env.example`（删死键 `AGENT_ENABLED`/`ENTAILMENT_BACKEND`，补 `APP_ENV`，`AICORE_INTERNAL_TOKEN` 标为 P0-7 预留）、`.gitattributes`（`* text=auto eol=lf` + 二进制不转换）、`docs/refactor/p0-environment.md`（新，从零启动序列 + §3 实跑记录表） |
| 依赖 | 无 |
| 验收 | X7；按 `p0-environment.md` §2 从空仓库到 `/health` 200 全程可复制执行，且 §3 表格填完 |
| 等级 | real（启动序列必须**实跑**，不是照抄文档） |
| 规模/风险 | S–M / 需要 Docker Desktop；Windows 上 bind mount 权限与换行是第一坑，故 `.gitattributes` 必进本卡 |
| 当前状态 | 2026-10-11：脚本、分层、`.env.example` 清理、`.gitattributes` 均已落，**§3 的 up/ps、`/health` 200、`migrate` exit 0 已实跑并记录**，`evidence` 由 mock 升到 **real**；仍未标 done（`down`/`logs` 未逐个实跑）。2026-10-09 那份「daemon 起不来是因为 WSL2 组件待重启、缺一次重启」的结论**已被推翻**：真因是 Docker Desktop 没在运行（启动后 5 秒即就绪），安装形态是系统级而非 per-user，实测版本与本行旧记录不同（具体版本号已移除）。`doctor` 会把 compose 自身的错与环境没起来分开报（compose 侧走 `docker compose config`，不需要 daemon） |

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
| 规模/风险 | M / **风险高在存量库**：`create_all` 建出的库无版本行，`335aeb7e` 后 Python 侧已拒绝启动，必须在本卡给出人工补基准版本的操作步骤（否则开发环境起不来） |
| 当前状态 | 2026-10-09 部分：`scripts/audit_schema.py` 落地，两模式分离且不互相冒充——`--check-baseline`（离线，审 `.sql` 是否非破坏/幂等/down 配对）与 `--live`（只读连库，出 `schema-baseline.json`：表集合、`alembic_version` 三态、列级 diff、索引与约束分查、会话时区）。判定逻辑 19 项单测（今天这套是 37 项，见下），含"两套类型命名不是漂移""注释里的 DROP 不算 DDL"这类会把核查废掉的噪声点。本机 `--check-baseline` 如实返回 1（`server/migrations/` 还空着）。**基线文件不在没有真库时生成**：05 §1 末与 §2.2 明确"由核查出的实际结构生成，不由 ORM 生成"，用 ORM 声明冒充只会把已知漂移（`ix_paper_nodes_id` 缺失、`filename` 是 unique index 非 constraint）洗掉。`probe_timestamps.py` 同样留到真库：探针法/分布法/交叉法三种判定全都要往库里写或读，没有库时它只能产出假结论。<br>**2026-10-12 两处推进**：①列级失真终于有了机检——`--live` 的 payload 补 `columns`，新增离线模式 `--verify-columns` 逐列比类型/varchar 长度/NOT NULL/DEFAULT（`test_audit_schema.py` 由 19 项增至 **37 项**：15 项列级机检随 `--verify-columns` 落，另 3 项随 `000002` 落地补上——"每张已交付的 up 都能被解析器读懂""`ai_executions` 的 DDL 记的是 P0-7 拍板的那几条""后一张迁移新增的表只算提示不算漂移"；含"解析真基线得 10 表/59 列"这条防解析器脱节的用例），up/down 的注释规则也统一了（台账 C1/C2）；②本卡最后挂着的收尾（`sqlc.yaml` 指到 `migrations/` 并与 `dev.py gen --check` 同原子改动）已完成，临时参照删除（台账 C3/C4）。**仍未 done 的两条**：`--verify-columns` 只到 mock——仓库里现存那份 `schema-baseline.json` 是补 `columns` 之前导的，命令如实返回 2，要等 Docker 起来重导一次；`probe_timestamps.py` 与 `timestamp-audit.md` 未产（本机 Docker daemon 当前不可达，且"每表时间列判定"是 X6 验收明文要求的一项） |

### P0-3 Go 数据访问层

| 字段 | 内容 |
| --- | --- |
| 输入 | P0-2 基线；`users` 表结构 |
| 输出 | `server/sql/queries/*.sql` + `server/sqlc.yaml` + 生成的 `server/internal/db/*`、pgx pool 初始化、`Makefile` 或 `scripts/dev.py gen` 保证 `sqlc generate` 可复现 |
| 依赖 | P0-2 |
| 验收 | `cd server && sqlc generate && git diff --exit-code`（生成物无漂移）+ `go test ./internal/db/...` |
| 等级 | mock |
| 规模/风险 | S / 生成物是否入库需决策：建议**入库**（CI 不装 sqlc 也能构建），以 `--check` 式 diff 保一致性 |
| 当前状态 | 2026-10-09：**K2 已落地**——`server/sql/queries/users.sql`（3 条）+ `server/sqlc.yaml` + 生成的 `internal/db/{db,models,users.sql}.go` 全部入库；`internal/db/pool.go` 手写连接池（启动即 Ping，空串拒绝，`PoolOptions` 故意不放没人执行的 timeout 旋钮）；入口是 `uv run python scripts/dev.py gen [--check]`，sqlc 版本钉 `v1.30.0`，本机版本对不上就拒绝生成（跨版本重生成会让 diff 门禁以"你的改动有问题"的名义红）。7 项 Go 用例（`internal/db` 实数，原文档记的 8 项已核正）锁住三类可机检的东西：SQL 文本、参数顺序与个数、生成字段集合；其中 `GetUserByID` 不选 `password_hash` 这条是安全边界，不靠 handler 记得剔除。<br>**done（2026-10-12，mock）**：schema 源已从临时参照切到 `migrations/000001_baseline.up.sql`（P0-2 真基线），临时参照 `server/sql/schema.sql` 已删除。切换那次 `git diff` 就是本卡一直欠的"答案"，内容有三条必须记住：①**`User` struct 与 `users.sql.go` 逐字未变**——`role`/`created_at` 的 DEFAULT 失真在 Go 生成物里根本不可见，因为 **sqlc 不把列默认值编码进类型**，所以"靠 diff 核对这两列"这条改法做不到，DEFAULT 的机检移交 `audit_schema.py --verify-columns`；②一次性补回来的是此前完全缺席的 9 张表 / 54 个字段（`parent_chunks`、`chat_sessions`、`chat_messages`、`workspaces`、`workspace_members`、`paper_nodes`、`citation_edges`、`glossary_entries`、`alembic_version`），这是临时参照的实际代价；③切换本身零风险，因为新增的都是 model，没有一条查询被改写。<br>**顺带补了两条生成前置检查**（本机踩过才知道的坑）：`sql.schema` 里若有目录且含 `.down.sql` 直接拒绝（sqlc 按文件名顺序读目录，`000001_baseline.down.sql` 排在 `.up.sql` 前 → 先 DROP 再 CREATE，生成物是按"回退后的库"产出的）；`migrations/*.up.sql` 未登记进 schema 列表也拒绝（新迁移建了表但 Go 看不见，重生成不报错只静默少一张表）。外加孤儿输出检查：sqlc 只写不删 `X.sql.go`，删掉的查询会留下没人调用却每次重现的 Go 类型。三条都在 `dev.py gen` 的入口生效，各有负向用例 |

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
| 输入 | `backend/core/auth.py` 现状语义（`335aeb7e`）：token `type` 分型、角色以 DB 为准、`ADMIN_INVITE_CODE` 未配置则禁 admin 注册、`JWT_SECRET_KEY` 无默认值；P0-3 数据层 |
| 输出 | `server/internal/auth/{jwt.go,password.go,handler.go,service.go}`、`scripts/export_pbkdf2_golden.py`（**2026-10-12 已交付**，导出件 `contracts/pbkdf2_golden.json`；口径按 `07` §兼容面表"不含密码与盐明文"落成"**不含明文口令、也不含真库 password_hash**"——向量是合成口令的摘要，口令由 `vector_id` 按文件里的 `password_rule` 重建；真库只在 `--from-db` 下贡献**形状统计**，摘要一律不带出仓库）、`server/migrations/_auth_compat.*.sql`（仅在需要补列时；**号不预定**，按 `05 §2.6` 取当时的下一个空位——`000002` 已给 `ai_executions`） |
| 依赖 | P0-3、P0-4 |
| 验收 | X4、X5；`cd frontend && npm run typecheck` 仍 0 error（Go 侧响应形状与前端一致） |
| 等级 | real（Python↔Go 互验 token 必须真实跑） |
| 规模/风险 | L / 最高风险是 PBKDF2 编码差异（标准 vs urlsafe b64、盐长度、迭代数）。**Go 接管 `users` 的前置条件就是 X5 全绿**，未过则切片停在"只签发不接管"状态 |
| 当前状态 | **2026-10-12 本轮推到 mock 级上限：X5 转 pass，X4 只剩 chain 半侧红，卡片 pending → in_progress（evidence=mock，requires=real 故不 done）**。<br>**产出**：`server/internal/auth/{password,jwt,service,handler}.go` 四件；`internal/config` 扩七个认证键（`JWT_SECRET_KEY`/`JWT_ALGORITHM`/`JWT_EXPIRE_MINUTES`/`JWT_REFRESH_EXPIRE_DAYS`/`ADMIN_INVITE_CODE`/`MIN_PASSWORD_LENGTH`/`PASSWORD_PBKDF2_ROUNDS`，默认值与 `backend/core/config/auth.py` 逐字同构）＋ `ValidateAuth()` fail-fast（空密钥在**所有**环境拒绝启动；占位密钥与两个泄露过的邀请码只在生产拒绝，对齐 `validate_runtime_security`）；`cmd/api` 挂三条路由并接 `unavailableStore`（无库时认证接口回 500 而不是 404）；`sql/queries/users.sql` 新增 `GetProfileByUsername`（`/me` 专用、不选 `password_hash`；原先自称"/me 专用"的 `GetUserByID` 按 id 取，而 JWT 的 `sub` 是用户名，那个声明落不了地）；新判据件 `scripts/export_jwt_golden.py` → `contracts/jwt_golden.json`（9 条：正 3 / 负 6）＋ `tests/unit/test_export_jwt_golden.py` 32 项。<br>**实跑读数**：`go test ./internal/auth/...` **50 项 PASS**、`gofmt -l` 空、`go vet ./...` 0、全量 `pytest -q` **547 passed / 49.28s**（unit 490 / integration 57，新增 32 项全在 jwt golden 那个文件）、`npm run typecheck` 0 error，且 Go 的响应形状与 `frontend/src/api/types.ts` 逐字段吻合（`AuthResponse` 五项含 `token_type`、`CurrentUserResponse` 两项）。<br>**几条"照抄现状而不是顺手改好"的地方**，每条都有用例钉住：①register 会 strip、login **不 strip**（所以用 ` alice ` 登录失败，即使注册进去的是 `alice`）；②密码长度按**码点**算（生产侧 `len(password)` 是 Python 的 str 长度；Go 的 `len(string)` 是字节，会把含中文的口令判得更严）；③`role` 不做枚举校验，`role:"root"` 折叠成 `user`（实测生产侧 200；契约的 enum 是值域描述，见台账 C21）；④多余字段忽略；⑤用户不存在与密码错误同一个 401（不给用户名枚举机会）；⑥校验顺序是"重名 409 先于邀请码 403"（顺序反过来等于选择泄露另一条信息）；⑦400/401/403/409/500 的 detail **含中英文混用这个现状**，全部由生产侧 handler 现跑取数（`handler.go` 顶部那张八行实测表），不是照源码凭印象写的。<br>**两处结构性收口**：`/me` 走 `GetProfileByUsername`，并有 `TestMePathNeverReadsPasswordHash` 断言这条路径一次都没调过带哈希的那条查询；角色一律回库取，`ParseAccessToken` **连 role 都不返回**（比"返回了但注明别用"可靠）。<br>**golden 文件的两条纪律**：①`--check` 是**语义**校验不是字节比对——token 的 `exp` 是"签发时刻 + 有效期"，本文件**不能**像 `pbkdf2_golden.json` 那样逐字重建（正向向量有效期钉 10 年作补偿，这点写在文件的 `reproducibility` 字段里）；②负向量带 `rejected_by` 字段区分"令牌层拒"与"回库拒"，Go 侧两层各自认领断言——`unknown-user` 那条在令牌层是**放行**的，拒绝发生在 service 回库那一步。<br>**两条跨语言分歧如实记在 `contracts/jwt_golden.json` 的 `divergences` 段**（两侧都实跑核对过，方向都是 Go 更严）：缺 `exp` 的令牌 Python 接受、Go 拒绝（`WithExpirationRequired`）；alg 白名单 Go 写死 HS256、不给配置口子。另有一条**两侧一致**但极易写错的细节也钉进了用例：HS256 签名 32 字节 → base64url 43 字符，末字符低 2 位是填充位，只改它两侧都照常接受——导出脚本第一版把 `tampered-signature` 造成"末字符按字母表挪一位"，结果生产裁判判它**通过**、导出被顶回来。<br>**顺手修掉两处判据/实现缺陷**：X5 的命令写错包路径（rc 恒为 1，台账 C22）；Go 的 `Recover` 把 500 写成 `Internal Server Error` 而生产侧是 `Internal server error`（台账 C23）。<br>**仍未 done 的都要真环境**：X4 的 chain 半侧要 P0-5 的容器 fixture ＋ 重建 Docker 环境（台账 C20）；"对同一份 `users` 行两侧互验 token"这个 real 级动作今天无库可对。**本卡输出里列的 `server/migrations/_auth_compat.*.sql` 不需要**——`users` 表已有全部列，按 `05 §2.6` 的"条件性预留不占号"，不建空文件。<br>**一条如实登记的残余风险**：Go 不实现 bcrypt 族校验（原真库已消失，"库里还有没有这类行"无法核查；引依赖去验一批可能不存在的行就是死代码）。处置是显式拒绝 + `family=bcrypt` 的 WARN 日志（`Family.String()` 就是为了让这条日志在告警里可读），**P1 接管 `users` 前必须先跑 `export_pbkdf2_golden.py --from-db` 看 families**。<br>（沿革）2026-10-12 上一轮只动了输入件：`scripts/export_pbkdf2_golden.py` 与 `contracts/pbkdf2_golden.json` 落地（10 条向量），`tests/unit/test_export_pbkdf2_golden.py` 15 项把它钉在四件事上——期望值等于生产裁判的返回值、形状确实在变、文件可逐字重建（`--check`）、`coverage_check` 能指出未覆盖的 rounds/盐长与**残留 bcrypt 族** |

### P0-7 ai-core 内部执行面

| 字段 | 内容 |
| --- | --- |
| 输入 | `02` §3 端点与请求体、§3.4 幂等/取消/超时/租约语义、`backend/services/` 现有可复用能力（**实际接线的是 `document_loader` 与 `milvus_writer`，经 `core/dependencies.py` 的 `get_document_loader`/`get_milvus_writer` 取，见 `internal_api/registry.py:13`**；本行此前点名 `agent_runner.py`——该文件不存在，`backend/services/` 里只有 `agent.py`/`cache.py`/`conversation_storage.py`/`tools.py`/`upload_jobs.py`） |
| 输出 | `backend/internal_api/{router.py,schemas.py,registry.py,executions.py}`（新：`/internal/v1/ai/execute`、`POST /executions`、`GET /executions/{id}`、`GET /executions/{id}/result`、`POST /executions/{id}/cancel`、`healthz/readyz`）、`task_type` 注册表（P0 只接 `PARSE_PAPER`、`INDEX_PAPER` 两种，内部调用现有 `document_loader`/`milvus_writer`）、`AICORE_INTERNAL_TOKEN` 校验中间件、`ai_executions` 表迁移（出自 `server/migrations/`，Python 侧只读写自己那张表）、compose 中 `ai-core` **不发布宿主端口** |
| 依赖 | P0-4 |
| 验收 | `uv run pytest -m chain -k ai_executions`：提交→轮询→领取结果，重复 `task_id` 不重跑模型（幂等），`cancel` 后过期结果被丢弃；`GET /internal/v1/ai/healthz` 无 token 时 401 |
| 等级 | real |
| 规模/风险 | L / `PARSE_PAPER` 若走真实 LLM/embedding 需密钥；无密钥时以固定小 PDF + 本地 embedding 的降级路径验结构，并在 `progress.json` 标 `needs_secret: true` 与未验段落 |
| 当前状态 | 2026-10-09 推到 mock 级上限：`backend/internal_api/{router,schemas,registry,executions,codes,auth,__init__}.py` 七件挂上 7 条 `/internal/v1/ai` 路径；`AICORE_INTERNAL_TOKEN` **未配置即拒绝**（比较走 `hmac.compare_digest`），healthz/readyz 复用 `backend/api/health.py` 不另造探活。§3.4 三条语义都有断言兜着：幂等——假 loader 记调用次数，重复 `task_id` 与重复 `(run_id, idempotency_key)` 两条索引各自命中且次数恒为 1；取消——`succeed()` 见 `cancelled` 返回 None，`/result` 于是 409 带 `errors[].code=CANCELLED`，与"尚未结束"那个 detail-only 的 409 靠 code 分开；超时——deadline 已过不起跑、置 failed 并仍写 `usage{0,0,0}`（504 `MODEL_TIMEOUT`）。错误体 `{"detail","errors[]"}`：`detail` 让全仓仍只有一种信封，`errors[].code` 让 Go 不解析文本；九码由用例与 `contracts/error-codes.md` §1 及 schema 的 `ErrorCode` 三方逐码比对；实现也被钉在契约上——`x-endpoints` 的 7 条与真实注册路径一一对应、注册类型集合等于 `x-p0-registered-task-types`、`/internal/` 不出现在 `openapi.yaml`（内部面不被 `check_contracts.py` 看见，这三条是它唯一的门禁）。**2026-10-12：`server/migrations/000002_ai_executions.{up,down}.sql` 已落地**——17 列逐条回指 `backend/internal_api/executions.py:26-42` 的 dataclass（这张表的列清单**没有任何一处文档逐字写过**，所以出处只能是实现＋契约），三个时间列按新表口径走 `TIMESTAMPTZ`，`run_id NOT NULL DEFAULT ''` 以保证 `UNIQUE(run_id, idempotency_key)` 真的成立（可空列上 NULL 互不相等，唯一约束会静默失效），只建 `lease_token` 不建 `lease_owner`/`lease_expires_at`（实现里没有的列不预先建），`status` CHECK 与 `result`/`result_ref` 互斥 CHECK，不写 `GRANT`（角色尚未定义）。已注册进 `server/sqlc.yaml` 的 `schema`，`dev.py gen` 生成 `AiExecution`（17 字段，三个时间列为 `pgtype.Timestamptz`），`audit_schema.py --check-baseline` 对两个 up 文件均 exit 0。**但这份 DDL 从未在真 PG 上执行过**（本轮 Docker daemon 不可达），所以它只是"能过离线形态检查的文件"。**剩余两件要真环境的事**：迁移在真库上 apply 两次验幂等，compose 里"ai-core 不发布宿主端口"是 P0-8 的文件改动；所以 `uv run pytest -m chain -k ai_executions` 本机收集 0 项，如实 `not_run`。`BUDGET_EXCEEDED` 暂只存在于码表与契约，拦截随 P1 的 LLM 任务类型落地 |

### P0-8 compose 与跨环境实跑

| 字段 | 内容 |
| --- | --- |
| 输入 | P0-1、P0-6、P0-7 |
| 输出 | `docker-compose.yml`（新增 `go-api`/`go-worker`/`ai-core` 服务；`backend` 服务改为 `ai-core` 角色并去掉宿主端口）、`nginx/nginx.conf`（`/api/` upstream 切 `go-api`；`TRUST_PROXY_HEADERS` 相关头部保持 `335aeb7e` 语义）、`.env.example` 补 Go 侧变量、`docs/refactor/p0-environment.md` 更新为含 Go 的完整序列 |
| 依赖 | P0-1、P0-6、P0-7 |
| 验收 | X1、X2；**在 Windows + Docker Desktop 上实跑**并把结果记进 `progress.json`（Linux CI 复跑同一序列作为交叉证据） |
| 等级 | real |
| 规模/风险 | M / 切换 upstream 是 P0 里唯一会影响现网可用性的动作：保留"一条配置回退到 Python"的回滚路径（`04` §5），且必须在切换前后各跑一次 X2 与前端手测 |
| 当前状态 | 2026-10-12 只落了它的**判据**：`scripts/check_nginx_routes.py`（X2 与 Y4 共用）把"Go 是唯一公开入口"拆成 R1 `/api/` 必须指 `go-api`、R2 任何 location 不得指向 `ai-core`（含藏在 upstream 里）、R3 不得有 `/internal` 前缀的对外 location、R4 compose 里 `ai-core` 不发布宿主端口；今天跑真仓库配置如实 **exit 1**（R1 中，`/api/` 还指向 `backend:8000`），R2/R3 已过，R4 因为 `ai-core` 还没进 compose 只记提示。本卡本体（三个新服务、upstream 切换）一行未动。<br>**开工前必须先拍 D8**（台账 C18）：`server/migrations/` 现在有文件、**没有执行器**——PATH 上无 `migrate`、`server/go.mod` 无 golang-migrate 依赖、`dev.py migrate` 实为容器内 `alembic upgrade head`（`dev.py:257-259`）。所以本卡除了三个服务定义，还要一并决定"Go 迁移由谁执行、什么时候执行、失败怎么办"，`09` X6 那句"`schema_migrations` 版本与设计一致"才有判据可依 |

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

## 3. 决策记录（K1–K4 已于 2026-10-09 定案；待拍决策**以 `docs/progress.json` 的 `decisions_pending` 为准，现为 D1–D8**）

> ⚠️ **两个 D  Namespace 别混**：`03` 里的 D1/D2/D3 指**功能断链**（公式检索、分层分块、元数据入库），
> 本节与 `progress.json` 里的 D1–D8 指**待拍决策**。本轮新增 **D8**（Go 侧迁移由谁执行，见台账 C18），
> 它把 P0-8 的一张子问题正式挂进了排期。本行此前写"D1–D3 待拍"，是只数了最早的三条。

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

## 5. 与产品愿景的关系

> 对照 [11-product-vision.md](11-product-vision.md)。**P0 属工程架构轴，不产出任何产品版本**（`11 §7`：两条轴编号不得混用）；产品级缺口集中记在 `11 §8`。

**已覆盖**：**只有两条架构前提，没有产品能力**。① `11 §2` 的三层能力演进要求"项目状态必须可持久、可查询、可审计（L3）、模型输出必须被证据绑定后才算事实（L4）"——P0-4 的契约与 `table-acl.md`、P0-7 的 `evidence_candidates` 只作为**建议**上报，是这条的骨架形态；② `11 §4.4 Research Mission` 的**长期项目记忆**与 `§6` 的 Go Research Engine —— P0-1 的 `cmd/worker` 空循环与 P0-1 的 `/ready` 是它的第一步（真正的 Run/Frontier 属 P3）。另有 `11 §4.10` 隐含的可复现环境前提（P0-0）。

**未覆盖**：P0 **全部**产品能力——`11 §3` 五个入口 · `§4.1`–`§4.10` 十项能力 · `§5` 三个惊艳功能。P0 里的 `auth` 切片是 §4.10 Workspace 的必要条件、不是它的实现。全部指向 `11 §8`。

**需拍板/冲突**：**有，两处**。① **P0 与 V1.0 的时序错位**：`11 §10` 要求 V1.0（可信学术 RAG）**先于** V2.0 完成，而 V1.0 的可信化依赖 **P2-1/P2-2**（chunk 真相层、公式索引），排在 P0-2 之后的 P2。也就是说**P0 结束时 V1.0 完成度仍是 0**，这条关系必须在 `progress.json` 与对外表述里写明，否则"P0 完成"极易被读成"V1.0 完成"。选项 A：把 P2-1/P2-2 前移进 P0 序列（`11 §7`/`04 §9` 的建议）；选项 B：V1.0 显式改为"在现有 Python 链路上先可信化"，P0 保持纯架构。② **X1–X8 与产品验收无关，不得混淆**：X1–X8 全是架构/契约/进程门禁（`compose up`、契约机检、golden vectors、进度同步），**没有一条断言用户可感知的产品能力**；`11 §3` 的五个入口在 P0 里没有任何退出标准。若把 X1–X8 全绿宣传为"产品可用"，即违反 `08` 原则②与 `11 §11` 的诚实口径。
