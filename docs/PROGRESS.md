# 进度报告

> 本文件由 `scripts/sync_progress.py` 从 [`progress.json`](progress.json) 生成，**请勿手改**。
> 数据截止 2026-10-11 · 基线 `6221147` · 投入 15-20 小时/周

## 一句话现状

- **完成了多少**：11%（按工时加权；41/372 小时，任务完成 5/38，验收 4/24 通过）
- **现在在哪**：2026-10-11 现场实况：Docker Desktop 可正常运行（启动后 5 秒引擎就绪），数据盘在 D:（29 GB，不占 C:），中间件 6 个容器与 dev.py infra / serve 两条路径均已实跑通过。P0-0 证据等级已由 mock 升到 real：doctor 全绿 → up 起 7 容器、backend healthy → /health 容器内与宿主机均 200 → migrate exit 0；未标 done 只因 down/logs 未逐个实跑。P0-4 契约目录 done、FE-1 前端结构 done、A0-1/A0-3/SPEC-1 done。P0-7 ai-core 内部执行面推到 mock 级上限（backend/internal_api/ 七件 + 29 条 HTTP 用例，三条机检把实现钉回契约），距 done 只差 ai_executions 迁移（阻塞于 P0-2 真库基线）与 compose 端口（属 P0-8）。P0-2 已完成真库审计：docs/refactor/schema-baseline.json 由 --live 从真实 PG 15.18 导出（10 张表、alembic head=add_paper_knowledge_graph、ORM 与真库漂移 23 处），下一步是把基线 DDL 抄进 server/migrations/ 并让 --check-baseline 通过。P0-1 / P0-3 仍 in_progress（P0-3 的 schema 源仍是临时参照 server/sql/schema.sql）。当前测试基线：449 passed（unit + integration；chain 与 e2e 各 0 条用例，-m chain 收 0 项时 pytest 返回 exit=5 而不是 0，不能算绿）。日常开发走源码运行（dev.py infra + serve），全栈容器只用于 P0-8/P0-9 的容器级验收。K1–K4 已定案，剩 D1/D2/D3 待拍且均不阻塞
- **还差多少**：待办 28 项 / 292 小时（约 14.6-19.5 周），进行中 5 项；可立即开工：无

## 阶段进度

| 阶段 | 目标 | 状态 | 完成度 | 验收 | 工时 | 周次 |
| --- | --- | --- | --- | --- | --- | --- |
| **P0** 架构与契约 | 搭起目标架构骨架与契约，跑通第一条垂直切片（浏览器 → Go 注册/登录/me） | 进行中 | ██░░░ 35% | 4/8 | 41/118h | W1–W2 |
| **P1** 后端迁移与最小原型 | Go 接管前端实际调用的 13 条接口，跑通上传→解析→索引→问答→引用的窄链路，全程只经 Go | 待办 | ░░░░░ 0% | 0/6 | 0/80h | W3–W6 |
| **P2** 功能拓展与数据可信化 | 正文真相进 PG、公式检索真实生效、事件可续传、预算持久化、引用可回溯到 PDF 位置 | 待办 | ░░░░░ 0% | 0/5 | 0/92h | W7 起（预计超 6 周日程） |
| **P3** 多 Agent 自主探索 | ResearchRun + Frontier + Planner/Discovery/Reader/Writer，产出可信带引用报告且崩溃可恢复 | 待办 | ░░░░░ 0% | 0/5 | 0/82h | P2 之后（未排具体周次） |

## P0 — 架构与契约（35%）

**可演示状态**：docker compose up → 前端注册 → 登录 → 侧栏显示用户名 → curl Go /api/v1/auth/me 返回同一用户；ai-core 只内网可达

### 退出标准

| # | 标准 | 判定命令 | 等级 | 结果 |
| --- | --- | --- | --- | --- |
| X1 | Go/ai-core/基础设施都能起来 | `docker compose up -d && curl http://localhost/api/v1/health` | 真实链路 | ⬜ 未跑 |
| X2 | Go 是唯一公开入口 | `uv run python scripts/check_nginx_routes.py` | 端到端 | ⬜ 未跑 |
| X3 | 契约已锁定且有结构校验 | `uv run python scripts/check_contracts.py` | mock | ✅ pass |
| X4 | 认证垂直切片可用且跨语言互验 token | `cd server && go test ./internal/auth/... && uv run pytest -m chain -k go_auth` | 真实链路 | ⬜ 未跑 |
| X5 | Go 能验旧密码哈希（接管 users 的前置条件） | `uv run python scripts/export_pbkdf2_golden.py && cd server && go test -run TestVerifyLegacyHash` | 真实链路 | ⬜ 未跑 |
| X6 | Go 不重复建表，基线迁移非破坏性且幂等 | `uv run python scripts/audit_schema.py --check-baseline` | 真实链路 | ✅ pass |
| X7 | 测试分层可用（marker 已注册且目录即分层） | `uv run python scripts/dev.py test -m unit && uv run python scripts/dev.py test -m integration && uv run python scripts/dev.py test -- tests/unit/test_pytest_layering.py` | mock | ✅ pass |
| X8 | 进度产物与真相源一致（每次提交的同步门禁） | `uv run python scripts/sync_progress.py --check` | mock | ✅ pass |

### 任务

| # | 任务 | 状态 | 证据 | 工时 | 依赖 | 验收命令 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A0-1 | 前端故障修复 + typecheck 进 CI 门禁（旧 A0-1） | 完成 | mock（要求 mock） | 3h | — | `cd frontend && npm run typecheck` | 提交 2c3e583；apiFetch/BASE 未导入与上传路径缺前缀已修，4 处 TS18048 消除。typecheck 进 CI 门禁 |
| A0-3 | 鉴权与运行安全修复（旧 A0-3） | 完成 | mock（要求 mock） | 10h | — | `uv run pytest -q` | 提交 d8f1563；当时 307 项全绿（2026-10-11 复跑 449 passed）。token 分型/WS 回查/密钥 fail-fast/限流真生效/删静默 create_all 均只在 mock+integration 层验证，真实链路属 P1 |
| SPEC-1 | spec 按四条原则重排 + 进度与可视化机制（08/09/04/06/README + progress.json/html/sync_progress.py） | 完成 | mock（要求 mock） | 8h | — | `uv run python scripts/sync_progress.py --check` | 路线改为 P0–P3；旧 Q1 与 Q5 的排期含义被取代，技术决策 Q2–Q8 沿用 |
| FE-1 | 前端结构重构：唯一请求出口 api/ + 模块单例状态层 + R1–R11 机检门禁（docs/refactor/10） | 完成 | mock（要求 mock） | 12h | — | `cd frontend && npm run typecheck && npm run build && uv run python scripts/check_frontend.py && uv run python scripts/check_contracts.py` | 2026-10-09 指令「前端要重构，先按核心原则把前端结构做完整做完善」。api/ 七件（types/token/events/http/sse/ws/client）取代 services/api.ts；六个 composable 统一为模块级单例并把 DOM/对话框外移 utils/dialog；DTO 按契约纠形（rag_trace 是对象不是数组，此前 trace 面板恒空白即 F7）；axios 与 style.css、MessageBubble.vue 删除。check_frontend.py 执行 R1–R11，配套 tests/unit/test_check_frontend.py 每条规则一负一正，证明门禁会红不是恒过。浏览器级回归（FE-f）本机无 Docker/PG/LLM key，如实留到 P0-9 的 X7。 |
| P0-0 | 统一命令入口与可复现环境（scripts/dev.py + marker 分层 + .env.example 清理 + .gitattributes + p0-environment.md） | 进行中 | 真实链路（要求 real） | 5h | — | `uv run python scripts/dev.py test -m unit` | 吸收旧 A0-0。dev.py 命令面 doctor/up/down/ps/logs/migrate/test 已落（seed 顺延 P1：种数据要先有上传链路）；marker 注册 + tests/conftest.py 目录即分层 + 9 项新用例；.env.example 删死键 AGENT_ENABLED/ENTAILMENT_BACKEND、补 APP_ENV、AICORE_INTERNAL_TOKEN 标注为 P0-7 预留；.gitattributes 钉 eol=lf 并清掉原来的 gitignore 语法行。X7 已 pass（2026-10-09 记 391/57/5、全量 448；2026-10-11 复跑 449 passed）。**环境实况更正（2026-10-10 二次更正，推翻上一版「缺一次重启」）**：真因是 Docker Desktop 根本没在运行——拉起后 5 秒引擎就绪；安装形态为系统级（`（Docker Desktop 安装目录）/`，`com.docker.service` Manual/Stopped），实测 Client（本机实测） / Compose（本机实测） / Desktop（本机实测），与上一版记的「per-user 安装 / CLI 29.8.2 / Desktop 4.94」不符。doctor 现在把两类失败分开报：compose 自身的错走 `docker compose config`（不需要 daemon，本机已实跑通过；顺手删掉废弃的 `version:` 字段，免得每次调用都吐告警），环境没起来另说；配一条用例证明这条校验会红而不是恒过。实测 exit=1 且只列两条阻塞（daemon 没跑、缺 .env）。**2026-10-10 本机实跑补齐**：doctor 全绿 → `up` 起 7 个容器、backend 转 healthy → `/health` 容器内与宿主机均 200（`{"status":"ok","version":"0.1.0"}`）→ `migrate` exit 0；unit 361/395 通过（另 34 项受沙箱临时目录限制，非仓库缺陷）、integration 56/57（余 1 项是「断言服务不可用」的旧设计，宿主上服务已在跑必然失败，已改为显式模拟依赖不可达）。起栈过程修掉三处真实缺陷：`.env.example` 行内注释被 dotenv 当成值（应用起不来 + 13 个测试文件收集失败）、compose 缺 `target: backend`（构建出 nginx 镜像 → 永远 unhealthy）、镜像名仍按旧目录名推导（已钉为 researchpilot-backend）。证据等级 real 已达成；仍不标 done——`down`/`logs` 未在本轮逐个实跑。**2026-10-11 路径补充**：新增 `dev.py infra`（只起中间件，postgres/redis/etcd/minio/milvus/attu）与 `dev.py serve`（宿主源码跑后端 uvicorn --reload），把「源码运行 + 中间件容器」列为一等路径——免于构建含 torch 的 16.5 GB backend 镜像，改代码也不必重建；同时修正 `up` 的健康等待：只请求部分服务时按实际请求的那几个等健康，原实现写死含 backend 的 HEALTH_CONTAINERS，会让 `dev.py up postgres` 一直等一个从未创建的容器直到超时。本机实测：infra 起 6 容器全 healthy 且零构建、serve 后 /health 与 /ready 均 200（database/redis/milvus 全 connected）、经 vite 代理的 /api/v1/* 与直连后端逐字一致；顺带记录两个坑——vite 5 只监听 ::1（访问用 localhost 而非 127.0.0.1）、探针路由不带 /api/v1 前缀。 |
| P0-1 | Go 服务骨架（cmd/api + cmd/worker + Chi 路由 + slog + trace_id + detail 错误信封 + health/ready） | 进行中 | mock（要求 real） | 8h | P0-0 | `cd server && gofmt -l . && go vet ./... && go test ./...` | 16 项 Go 用例绿：/ready 失败用 {"detail":{...}} 信封、成功平铺；探测键名 database 与超时文案 "timeout after Ns" 逐字对齐 backend/api/health.py；404/405/500 都走 FastAPI 同款信封；trace_id 生成与透传；panic 兜底；生产缺 DATABASE_URL 拒绝启动。real 部分（compose 起服务后 /ready 200、Dockerfile 能否构建）本机无 Docker → 未验，不标 done |
| P0-2 | Schema 基线与非破坏性收编（audit_schema.py + probe_timestamps.py + migrations/000001_baseline） | 进行中 | 真实链路（要求 real） | 8h | P0-0 | `uv run python scripts/audit_schema.py --check-baseline` | 含 create_all 建出的无 alembic_version 存量库的人工补版本步骤。2026-10-09：scripts/audit_schema.py 落地（离线 --check-baseline + 只读 --live 两模式，判定逻辑 19 项单测），本机 --check-baseline 现在如实返回 1（migrations/ 还空着）。剩下的都必须有真库：基线 DDL 由实际结构抄录而非 ORM 声明（05 §1 末、§2.2），故 X6 仍 not_run。**2026-10-11 真库审计已跑通**：--live 需显式导出 DATABASE_URL（脚本不读 config 默认值，已写进 .env.example），导出 docs/refactor/schema-baseline.json —— PG 15.18、10 张表、alembic head=add_paper_knowledge_graph、ORM 与真库漂移 23 处。剩余交付：server/migrations/000001_baseline.{up,down}.sql 按真实结构抄录并让 --check-baseline 返回 0，X6 才能转 pass。**2026-10-11 已完成并转 pass**（X6），同时暴露三处必须记下的事实：①`audit_schema.py` 的 `--live` payload **不含列清单**（只有 tables/alembic/tz/server_version/indexes/constraints/column_diff），所以基线的列名/类型/NOT NULL/DEFAULT 是抄自真正建库的 alembic 链（head 与 baseline 的 `alembic: head:add_paper_knowledge_graph` 一致），再用 column_diff 机器交叉验证（DDL 里「无 DEFAULT」的列集合 = 漂移 23 条，完全一致；无 type/only_in_orm 漂移）——**要让基线可直接抄录，应给 payload 补 `columns`**，否则 varchar 长度与 NOT NULL 无机检覆盖；②`--check-baseline` 只判文件形态，且 down 规则不剥注释、up 规则剥注释（注释里写 DROP TABLE IF EXISTS 会被误判成违规），这是校验器自身的不一致；③真库是 **10 表**（含 `alembic_version`），`05 §2.2` 写的「现存 9 表」应更新；`alembic_version` 是否算 Go 基线对象、down 能否作用于存量库，两项待拍。剩余收尾：`sqlc.yaml` 指到 `migrations/` 并与 `dev.py gen --check` 作为同一原子改动（本机没有 sqlc 二进制） |
| P0-3 | Go 数据访问层（sqlc + pgx pool，生成物入库并以 diff 校验一致性） | 进行中 | mock（要求 mock） | 4h | P0-2 | `uv run python scripts/dev.py gen --check` | 决策 K2 已落地：生成物入库，dev.py gen --check 作为漂移门禁（sqlc 版本钉 v1.30.0，不匹配就拒绝生成）。2026-10-09 已完成 users 认证切片的 queries + 生成物 + pgx 池 + 8 项 Go 用例；未 done 的原因只有一个——schema 源是 server/sql/schema.sql 这份**临时参照**（形状取自 ORM 声明，本机无 PG 无法核查），P0-2 出真基线后要把 sqlc.yaml 指到 migrations/ 并重跑 gen，字段有变就是那次 diff 的内容。**2026-10-11 真基线落地后的反查结论**：`server/sql/schema.sql` 这份临时参照在 `users.created_at` 与 `users.role` 两列上**失真**——真库有 `DEFAULT now()` 与 `DEFAULT 'user'`（否则这两列会出现在 column_diff 里），而该文件与 `05 §4` 写成「库里无 DEFAULT」。切 `sqlc.yaml` 时必须以这份已知差异核对 diff；真库还有两处「如实登记不修正」的漂移：**没有** `ix_paper_nodes_id`（ORM 声明了但真库没落库）、`paper_nodes.filename` 与 `users.username` 的唯一性由 unique index 承载而非 UNIQUE 约束 |
| P0-4 | 契约目录（openapi.yaml + ai-execution.schema.json + error-codes.md + table-acl.md + check_contracts.py）含 429 信封定案 | 完成 | mock（要求 mock） | 8h | — | `uv run python scripts/check_contracts.py` | 五件产物齐且 X3 本机 pass；K1/K4 已于 2026-10-09 落地（backend/core/exceptions.py 两个 handler + tests/integration/{test_error_envelope,test_rate_limit_enforcement}.py），契约里不再有 As-Is 例外，故 done。原先挂的 deps:[P0-1] 已摘除：本卡只取 P0-1 的 detail 错误信封形状，该形状已在 server/internal/httpapi/envelope.go 落地并有 Go 单测，不要求 P0-1 整体（real 级 compose 证据）先完成——P0-1 的 real 缺口由 Docker Desktop 决定，与契约内容无关 |
| P0-5 | 跨语言契约测试骨架 + chain 级真实容器 fixture | 待办 | 未验证（要求 real） | 6h | P0-1、P0-4 | `uv run pytest -m chain -k contract` | 未实现端点走显式白名单跳过，不伪装通过 |
| P0-6 | 认证垂直切片（Go register/login/me + PBKDF2 golden vectors + JWT claims 兼容） | 待办 | 未验证（要求 real） | 16h | P0-3、P0-4、A0-3 | `cd server && go test -run TestVerifyLegacyHash` | P0 的唯一业务切片；X5 未全绿前 Go 不接管 users |
| P0-7 | ai-core 内部执行面（/internal/v1/ai/execute + executions 异步 + task_type 注册表 + 内部令牌 + ai_executions 表） | 进行中 | mock（要求 real） | 14h | P0-4 | `uv run pytest -m chain -k ai_executions` | 2026-10-09 推到本机 mock 级上限：`backend/internal_api/` 七件（router/schemas/registry/executions/codes/auth/__init__）挂上 7 条 `/internal/v1/ai` 路径；29 条 HTTP 级用例覆盖鉴权 401（含 healthz）、幂等重放不重跑 handler、取消后结果被丢弃、过期 deadline 不起跑但仍写 usage、目录穿越被夹在 UPLOAD_DIR 内、未注册类型 400 `UNSUPPORTED_TASK_TYPE`、多余字段 400（K4 只有字符串 detail）；另有 3 条机检把实现钉回契约（`x-endpoints` 的 7 条与真实注册路径一一对应、注册类型集合等于 `x-p0-registered-task-types`、`/internal/` 不出现在 openapi.yaml——内部面不被 `check_contracts.py` 看见，这三条是它唯一的门禁）；store 另有 6 项单测，码表由 2 项用例与 `contracts/error-codes.md` §1 + schema 的 `ErrorCode` 三方逐码比对。全仓 444 项 pytest 与 ruff 绿。**未 done 的两件事都要真环境**：`ai_executions` 迁移出自 `server/migrations/`（P0-2 必须先由实际库结构抄基线，禁止由 ORM 生成），compose 里「ai-core 不发布宿主端口」是 P0-8 的文件改动；因此 `uv run pytest -m chain -k ai_executions` 本机收集 0 项，如实 not_run。`BUDGET_EXCEEDED` 目前只存在于码表与契约，真正拦截随 P1 的 LLM 任务类型落地。 （需密钥） |
| P0-8 | compose 与 Windows 实跑（新增 go-api/go-worker/ai-core，nginx upstream 切 Go，ai-core 不发布宿主端口） | 待办 | 未验证（要求 real） | 8h | P0-1、P0-6、P0-7 | `uv run python scripts/dev.py up && curl http://localhost/api/v1/health` | P0 里唯一影响现网可用性的动作；保留一条配置回退 Python 的路径 |
| P0-9 | P0 端到端演示与退出复核（Playwright p0-auth.spec + p0-demo.md + 状态收口） | 待办 | 未验证（要求 e2e） | 8h | P0-8 | `cd frontend && npm run test:e2e` | 同时要求全量 uv run pytest -q 保持绿（2026-10-11 基线 449 passed） |

**本阶段不做**：不迁移其余 12 条业务接口（P1）· 不做 chunk 可信化与 paper_chunks（P2）· 不做 Frontier/ResearchRun（P3）· 不 git mv backend → ai-core（决策 Q2）· 不改前端框架，不改 backend/rag 算法实现

## P1 — 后端迁移与最小原型（0%）

**可演示状态**：上传一篇 PDF → 进度到 completed → 提问 → 流式回答带 [Source 1] 与 citations 列表；前端不再直连 Python

### 退出标准

| # | 标准 | 判定命令 | 等级 | 结果 |
| --- | --- | --- | --- | --- |
| Y1 | Go 覆盖 13 条在用接口 + health/ready/metrics | `uv run python scripts/check_contracts.py --implemented` | 真实链路 | ⬜ 未跑 |
| Y2 | 真实浏览器 E2E 全绿（旧 E2/E3） | `cd frontend && npm run test:e2e` | 端到端 | ⬜ 未跑 |
| Y3 | 跨语言契约测试通过（含 SSE 字节级帧序列） | `uv run pytest -m chain -k contract` | 真实链路 | ⬜ 未跑 |
| Y4 | ai-core 不对浏览器暴露 | `uv run python scripts/check_nginx_routes.py` | 端到端 | ⬜ 未跑 |
| Y5 | 12 条未调用接口逐条留有调用方审计记录并带 Deprecation 头 | `uv run pytest -m chain -k deprecation` | 真实链路 | ⬜ 未跑 |
| Y6 | 既有测试不退化 | `uv run pytest -q` | mock | ⬜ 未跑 |

### 任务

| # | 任务 | 状态 | 证据 | 工时 | 依赖 | 验收命令 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P1-0 | Go 反向代理（阶段 1）：透传 Python + 鉴权 + trace_id 注入 | 待办 | 未验证（要求 real） | 6h | P0-9 | `uv run pytest -m chain -k proxy` |  |
| P1-1 | Go 接管读接口：/auth/me /sessions /sessions/{id} /documents | 待办 | 未验证（要求 real） | 10h | P1-0 | `uv run pytest -m chain -k go_read` | 保持无分页全量列表形状 |
| P1-2 | Go 接管写接口：/auth/register /login /sessions DELETE /documents/delete/* | 待办 | 未验证（要求 real） | 10h | P1-1 | `uv run pytest -m chain -k go_write` | 单写者原则：切换窗口内该接口只允许单边写 |
| P1-3 | 上传编排移到 Go（任务状态持久化 PG，取代 upload_jobs 进程内存态） | 待办 | 未验证（要求 real） | 14h | P1-2、P0-7 | `uv run pytest -m chain -k upload_orchestration` |  |
| P1-4 | 流式接管：/chat/stream SSE + /ws/chat WS 的 Go 门面 | 待办 | 未验证（要求 real） | 14h | P1-3、P0-7 | `uv run pytest -m chain -k sse_shape` | X-Accel-Buffering 语义与 rag_trace 两种形状必须逐字节对齐 |
| P1-5 | 前端基址切换与 nginx 收口：移除 app.py 静态挂载，业务 API 退出 Python | 待办 | 未验证（要求 e2e） | 6h | P1-4 | `cd frontend && npm run test:e2e` |  |
| P1-6 | 真实 E2E 骨架（Playwright 四条主路径 + chain 级 CI 分工） | 待办 | 未验证（要求 e2e） | 10h | P1-5 | `cd frontend && npm run test:e2e` | 吸收旧 A0-6 的端到端部分（旧 E2/E3） （需密钥） |
| P1-7 | 12 条未调用接口的调用方审计与 Deprecation 头 | 待办 | 未验证（要求 real） | 6h | P1-5 | `uv run pytest -m chain -k deprecation` |  |
| P1-8 | P1 退出复核与文档口径收口 | 待办 | 未验证（要求 real） | 4h | P1-6、P1-7 | `uv run python scripts/sync_progress.py --check` |  |

**本阶段不做**：不做 Frontier 与多轮规划（P3）· 不做 chunk 可信化（P2）· 不宣称引用为证据链（P1 引用为非证据级）

## P2 — 功能拓展与数据可信化（0%）

**可演示状态**：点击某条引用 → 显示 PG 里的完整 chunk 正文（无 2000 字截断）与 PDF 页码/章节路径；Monitor 页断线后按 Last-Event-ID 续传

### 退出标准

| # | 标准 | 判定命令 | 等级 | 结果 |
| --- | --- | --- | --- | --- |
| Z1 | chunk 正文进 PG 且无截断（旧 E4） | `uv run python scripts/rebuild_chunks.py --verify-only` | 真实链路 | ⬜ 未跑 |
| Z2 | 公式检索真实生效（旧 E5） | `uv run pytest -m chain -k formula` | 真实链路 | ⬜ 未跑 |
| Z3 | 引用可回溯到 paper_chunks 行与 PDF 位置 | `cd frontend && npm run test:e2e` | 端到端 | ⬜ 未跑 |
| Z4 | 进程重启后任务状态可从 PG 恢复 | `uv run pytest -m chain -k restart_recovery` | 真实链路 | ⬜ 未跑 |
| Z5 | README 能力表三档口径与实际一致（旧 E10） | `uv run python scripts/sync_progress.py --check` | mock | ⬜ 未跑 |

### 任务

| # | 任务 | 状态 | 证据 | 工时 | 依赖 | 验收命令 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P2-1 | Chunk 真相层：papers/paper_versions/paper_files/paper_sections/paper_chunks 走 server/migrations + 重建脚本（旧 A0-4） | 待办 | 未验证（要求 real） | 24h | P1-8 | `uv run python scripts/rebuild_chunks.py --verify-only` | 在 Go 侧新 schema 上做，Python 不再建表；旧文献从原始 PDF 重解析 |
| P2-2 | 公式索引接通并以 PG 为持久真相（旧 A0-5） | 待办 | 未验证（要求 real） | 10h | P2-1 | `uv run pytest -m chain -k formula` | _build_formula_index 当前零调用点；内存 LSH 重启即空 |
| P2-3 | chunk/公式链路测试（旧 A0-6 的数据部分） | 待办 | 未验证（要求 real） | 8h | P2-1、P2-2 | `uv run pytest -m chain -k chunks` |  |
| P2-4 | 10–15 题固定科研回归集与基线记录（不设门禁阈值） | 待办 | 未验证（要求 real） | 8h | P2-1 | `uv run python scripts/evaluate_rag.py --questions tests/fixtures/research_questions.json` | 决策 Q8：记录而非断言 （需密钥） |
| P2-5 | 会话 append-only + 持久事件日志 + SSE Last-Event-ID 续传 | 待办 | 未验证（要求 real） | 14h | P1-4 | `uv run pytest -m chain -k event_cursor` | Redis 不得作为唯一事件源 |
| P2-6 | 预算与 usage 持久化（model_usage_records，Run/会话级汇总移到 Go） | 待办 | 未验证（要求 real） | 8h | P1-3 | `uv run pytest -m chain -k usage_records` | 现状 budget.py 仅 contextvars 内存，零持久化 |
| P2-7 | 前端产品化：Monitor / Paper Reader / 引用回溯视图 | 待办 | 未验证（要求 e2e） | 16h | P2-1、P2-5 | `cd frontend && npm run test:e2e` |  |
| P2-8 | P2 退出复核与文档口径收口 | 待办 | 未验证（要求 real） | 4h | P2-3、P2-4、P2-6、P2-7 | `uv run python scripts/sync_progress.py --check` |  |

**本阶段不做**：不做自主探索与 Frontier 多轮规划（P3）· 不引入 Neo4j/双图（P4）· 不删 parent_chunks/multimodal.py/layout_analyzer.py

## P3 — 多 Agent 自主探索（0%）

**可演示状态**：输入研究问题 → Run RUNNING → Frontier 多轮派发 → 中途强杀 worker → 重启后从租约过期处继续 → 产出带引用报告与未解决问题清单

### 退出标准

| # | 标准 | 判定命令 | 等级 | 结果 |
| --- | --- | --- | --- | --- |
| W1 | 固定多阶段工作流端到端产出带引用报告（需密钥） | `uv run pytest -m chain -k mission_report` | 端到端 | ⬜ 未跑 |
| W2 | Go/Python 强杀后崩溃恢复测试通过 | `uv run pytest -m chain -k crash_recovery` | 真实链路 | ⬜ 未跑 |
| W3 | 幂等：重复派发不产生重复实体 | `uv run pytest -m chain -k idempotency` | 真实链路 | ⬜ 未跑 |
| W4 | 暂停/继续/取消语义正常 | `uv run pytest -m chain -k run_control` | 真实链路 | ⬜ 未跑 |
| W5 | 预算耗尽产出 PARTIAL 报告并列出未解决问题 | `uv run pytest -m chain -k budget_partial` | 真实链路 | ⬜ 未跑 |

### 任务

| # | 任务 | 状态 | 证据 | 工时 | 依赖 | 验收命令 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P3-1 | research_projects/runs/plans/tasks/task_dependencies 与事件表 schema + sqlc | 待办 | 未验证（要求 real） | 10h | P2-8 | `uv run pytest -m chain -k run_schema` |  |
| P3-2 | Frontier 队列：FOR UPDATE SKIP LOCKED + 租约 + 幂等 + 重试退避 | 待办 | 未验证（要求 real） | 16h | P3-1 | `uv run pytest -m chain -k frontier` |  |
| P3-3 | Worker Pool：有限 goroutine + context + fencing token + 结果与完成同事务 | 待办 | 未验证（要求 real） | 14h | P3-2 | `uv run pytest -m chain -k worker_fencing` |  |
| P3-4 | Planner/Discovery/Reader/Writer 接入 ai-core task_type（Go 重校验 proposed_tasks） | 待办 | 未验证（要求 real） | 16h | P3-3、P0-7 | `uv run pytest -m chain -k agent_tasks` | 建议不携带写权限 （需密钥） |
| P3-5 | 报告生成与 PARTIAL 语义、未解决问题清单 | 待办 | 未验证（要求 real） | 10h | P3-4 | `uv run pytest -m chain -k report` |  |
| P3-6 | 崩溃恢复与强杀测试（事件日志重放） | 待办 | 未验证（要求 real） | 10h | P3-3 | `uv run pytest -m chain -k crash_recovery` |  |
| P3-7 | 固定工作流基线（Explorer 上线的前置条件） | 待办 | 未验证（要求 real） | 6h | P3-5 | `uv run pytest -m chain -k sequential_baseline` |  |

**本阶段不做**：不做双图与 Knowledge Explorer（P4）· 不引入 Kafka/RabbitMQ· 不做 A/B/C 对照实验与消融

## 日程

| 周 | 日期 | 目标 | 阶段 | 状态 |
| --- | --- | --- | --- | --- |
| W1 | 10/12–10/18 | 骨架：统一命令入口 + Go 服务 + compose + 契约目录 + marker 注册 | P0-0…P0-4 | planned |
| W2 | 10/19–10/25 | 契约锁定与跨语言测试 + 认证垂直切片 + ai-core 内部面 | P0-5…P0-9 | planned |
| W3 | 10/26–11/01 | 最小原型：Go 接管读/写接口，窄链路端到端跑通 | P1-0…P1-4 | planned |
| W4 | 11/02–11/08 | 流式与上传编排、前端基址切换、E2E 全绿 | P1-5…P1-7 | planned |
| W5 | 11/09–11/15 | 前端产品化骨架、弃用接口收口 | P1-8 + P2 前端项 | planned |
| W6 | 11/16–11/22 | 回归与发布：P1 退出标准全绿、文档口径复核 | P1 收口 | planned |
| W7+ | 11/23 起 | P2 数据可信化与功能拓展（chunk 真相层、公式索引、回归集） | P2 | overtime_expected |

## 待你拍板

- **D1** 总纲要求 ai-core/ 独立目录，路线建议保留 backend/ 物理目录、ai-core 只作角色名，是否接受？ → 建议：接受（决策 Q2 + 原则④），改名留到 P2 后作为可单独回滚的提交（P0 目录结构）
- **D2** 13 条在用接口在 P1 迁完、其余 12 条在 P1 末统一 Deprecation，是否符合总纲 P0 完成标准里「旧接口必须迁移或标记 deprecated」？ → 建议：符合原则①；若要求 P0 内完成则 P0 估时翻倍（P0 退出标准 X2）
- **D3** chunk 可信化移到 P2 且改在 Go 侧 schema，接受 P1 引用为非证据级？ → 建议：接受；证据级引用属 P2 的 Z1/Z3（P1 演示口径与 README 表述）

## 风险登记（前 8）

- **开发机没有容器运行时，P0 的 real 级验收整体阻塞（2026-10-11 已解除）** ｜触发：2026-10-09 判为「本机未安装 Docker Desktop / WSL 组件装完待重启」；2026-10-10 现场核查**推翻**：Docker Desktop（本机实测）（系统级安装，Client（本机实测） / Compose（本机实测））一直都在，只是没在运行——启动后 5 秒引擎即就绪。真实阻塞是缺 .env（且 LLM_API_KEY / LLM_MODEL 是硬要求，只验骨架也必须有值）与 docker.io 的 DNS 污染 ｜缓解：已解除并留下证据：p0-environment.md §3 的 up/ps、/health 200、migrate 均已实跑记录；中间件 6 容器 healthy；镜像源与本地代理（本机代理 7890）已配好。剩余风险转移到数据面：chunk 正文仍只在 Milvus 且 VARCHAR(2000) 截断，见 G10/G11/G12
- **Go 依赖拉不动，P0-1 之后每张 Go 卡都开不了工** ｜触发：proxy.golang.org 在中国大陆不可达（本机 dial tcp 实测超时）；go mod tidy 连依赖的测试依赖一起解析 ｜缓解：机器级 `go env -w GOPROXY=https://goproxy.cn,direct`，容器构建用 --build-arg GOPROXY；已写进 p0-environment.md §4 第 7 条。go.sum 入库保证离线也能 build
- **Go 验不了旧密码，接管后用户登录全挂** ｜触发：PBKDF2 base64 编码差异（标准 vs urlsafe）、盐长度、迭代数 ｜缓解：先导出 golden vectors，X5 全绿前 Go 不接管 users
- **SSE 形状漂移导致前端流式显示异常** ｜触发：Go 侧缓冲/flush 策略、nginx X-Accel-Buffering ｜缓解：P1 契约测试比对 Python 与 Go 的字节级帧序列
- **同一份业务状态被双写** ｜触发：切换窗口内 Python 仍在写 chat_messages ｜缓解：单写者原则 + feature flag + 写路径断言，接口逐个切换
- **P1 的引用被当成证据链宣传** ｜触发：chunk 真相层尚未建立，引用来自 Milvus 截断副本 ｜缓解：前端与 README 显式标注非证据级；证据级属 P2 验收（Z1/Z3）
- **6 周日程与 solo 投入不匹配** ｜触发：总纲按全职强度估 6 周；solo 15–20h/周下 P0+P1≈5–6.5 周，P2 落在 W7 后 ｜缓解：不可压缩项固定（P0 骨架/契约/认证、P1 E2E），日程在 progress.json 里显式标 overtime 而非偷改日期
- **存量库拒绝启动导致开发中断** ｜触发：d8f1563 删除静默 create_all 后，无 alembic_version 的库启动失败 ｜缓解：P0-2 给出人工补基准版本的操作步骤并写进 p0-environment.md

## 图例

- 状态：待办 / 进行中 / 完成 / 延期 / 取消。**只有达到要求证据等级才能标完成**（`--check` 强制）。
- 证据等级：`mock` 单元级（外部依赖全 mock）< `real` 真实容器链路 < `e2e` 真实浏览器。
- 完成度按工时加权，`deferred`/`cancelled` 不计入分母。
