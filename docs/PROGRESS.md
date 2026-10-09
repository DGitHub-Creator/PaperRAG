# 进度报告

> 本文件由 `scripts/sync_progress.py` 从 [`progress.json`](progress.json) 生成，**请勿手改**。
> 数据截止 2026-10-09 · 基线 `6221147` · 投入 15-20 小时/周

## 一句话现状

- **完成了多少**：8%（按工时加权；29/360 小时，任务完成 4/37，验收 3/24 通过）
- **现在在哪**：P0-4 契约目录 done；P0-2/P0-3 同日推到 mock 级上限：audit_schema.py（离线 --check-baseline + 只读 --live，19 项判定单测）与 Go 数据访问层（sqlc 生成物入库 + dev.py gen --check 漂移门禁 + 8 项 Go 用例）都已落地并有负向用例。两卡剩下的都锁在同一件事上——真实 PostgreSQL：基线 DDL 必须由实际结构抄录（05 §1 末明确禁止由 ORM 生成），当前 sqlc 用的是 server/sql/schema.sql 这份临时参照，P0-2 出基线后要重指 schema 并重跑 gen。本机无 Docker/PG，因此 P0-0/P0-1/P0-2 的 real 级与 P0-5 起各卡的容器证据一律 not_run（见 p0-environment.md §3）。K1–K4 已全部定案，剩 D1/D2/D3 三项待拍且均不阻塞当前工作
- **还差多少**：待办 29 项 / 306 小时（约 15.3-20.4 周），进行中 4 项；可立即开工：P0-7

## 阶段进度

| 阶段 | 目标 | 状态 | 完成度 | 验收 | 工时 | 周次 |
| --- | --- | --- | --- | --- | --- | --- |
| **P0** 架构与契约 | 搭起目标架构骨架与契约，跑通第一条垂直切片（浏览器 → Go 注册/登录/me） | 进行中 | █░░░░ 27% | 3/8 | 29/106h | W1–W2 |
| **P1** 后端迁移与最小原型 | Go 接管前端实际调用的 13 条接口，跑通上传→解析→索引→问答→引用的窄链路，全程只经 Go | 待办 | ░░░░░ 0% | 0/6 | 0/80h | W3–W6 |
| **P2** 功能拓展与数据可信化 | 正文真相进 PG、公式检索真实生效、事件可续传、预算持久化、引用可回溯到 PDF 位置 | 待办 | ░░░░░ 0% | 0/5 | 0/92h | W7 起（预计超 6 周日程） |
| **P3** 多 Agent 自主探索 | ResearchRun + Frontier + Planner/Discovery/Reader/Writer，产出可信带引用报告且崩溃可恢复 | 待办 | ░░░░░ 0% | 0/5 | 0/82h | P2 之后（未排具体周次） |

## P0 — 架构与契约（27%）

**可演示状态**：docker compose up → 前端注册 → 登录 → 侧栏显示用户名 → curl Go /api/v1/auth/me 返回同一用户；ai-core 只内网可达

### 退出标准

| # | 标准 | 判定命令 | 等级 | 结果 |
| --- | --- | --- | --- | --- |
| X1 | Go/ai-core/基础设施都能起来 | `docker compose up -d && curl http://localhost/api/v1/health` | 真实链路 | ⬜ 未跑 |
| X2 | Go 是唯一公开入口 | `uv run python scripts/check_nginx_routes.py` | 端到端 | ⬜ 未跑 |
| X3 | 契约已锁定且有结构校验 | `uv run python scripts/check_contracts.py` | mock | ✅ pass |
| X4 | 认证垂直切片可用且跨语言互验 token | `cd server && go test ./internal/auth/... && uv run pytest -m chain -k go_auth` | 真实链路 | ⬜ 未跑 |
| X5 | Go 能验旧密码哈希（接管 users 的前置条件） | `uv run python scripts/export_pbkdf2_golden.py && cd server && go test -run TestVerifyLegacyHash` | 真实链路 | ⬜ 未跑 |
| X6 | Go 不重复建表，基线迁移非破坏性且幂等 | `uv run python scripts/audit_schema.py --check-baseline` | 真实链路 | ⬜ 未跑 |
| X7 | 测试分层可用（marker 已注册且目录即分层） | `uv run python scripts/dev.py test -m unit && uv run python scripts/dev.py test -m integration && uv run python scripts/dev.py test -- tests/unit/test_pytest_layering.py` | mock | ✅ pass |
| X8 | 进度产物与真相源一致（每次提交的同步门禁） | `uv run python scripts/sync_progress.py --check` | mock | ✅ pass |

### 任务

| # | 任务 | 状态 | 证据 | 工时 | 依赖 | 验收命令 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A0-1 | 前端故障修复 + typecheck 进 CI 门禁（旧 A0-1） | 完成 | mock（要求 mock） | 3h | — | `cd frontend && npm run typecheck` | 提交 2c3e583；apiFetch/BASE 未导入与上传路径缺前缀已修，4 处 TS18048 消除。typecheck 进 CI 门禁 |
| A0-3 | 鉴权与运行安全修复（旧 A0-3） | 完成 | mock（要求 mock） | 10h | — | `uv run pytest -q` | 提交 d8f1563；307 项全绿。token 分型/WS 回查/密钥 fail-fast/限流真生效/删静默 create_all 均只在 mock+integration 层验证，真实链路属 P1 |
| SPEC-1 | spec 按四条原则重排 + 进度与可视化机制（08/09/04/06/README + progress.json/html/sync_progress.py） | 完成 | mock（要求 mock） | 8h | — | `uv run python scripts/sync_progress.py --check` | 路线改为 P0–P3；旧 Q1 与 Q5 的排期含义被取代，技术决策 Q2–Q8 沿用 |
| P0-0 | 统一命令入口与可复现环境（scripts/dev.py + marker 分层 + .env.example 清理 + .gitattributes + p0-environment.md） | 进行中 | mock（要求 real） | 5h | — | `uv run python scripts/dev.py test -m unit` | 吸收旧 A0-0。dev.py 命令面 doctor/up/down/ps/logs/migrate/test 已落（seed 顺延 P1：种数据要先有上传链路）；marker 注册 + tests/conftest.py 目录即分层 + 9 项新用例；.env.example 删死键 AGENT_ENABLED/ENTAILMENT_BACKEND、补 APP_ENV、AICORE_INTERNAL_TOKEN 标注为 P0-7 预留；.gitattributes 钉 eol=lf 并清掉原来的 gitignore 语法行。X7 已 pass，但 p0-environment.md §3 的实跑记录表全空：本机未安装 Docker Desktop，doctor 实测 exit=1，up/health/migrate 未实跑 → 等级 real 达不到，不标 done |
| P0-1 | Go 服务骨架（cmd/api + cmd/worker + Chi 路由 + slog + trace_id + detail 错误信封 + health/ready） | 进行中 | mock（要求 real） | 8h | P0-0 | `cd server && gofmt -l . && go vet ./... && go test ./...` | 16 项 Go 用例绿：/ready 失败用 {"detail":{...}} 信封、成功平铺；探测键名 database 与超时文案 "timeout after Ns" 逐字对齐 backend/api/health.py；404/405/500 都走 FastAPI 同款信封；trace_id 生成与透传；panic 兜底；生产缺 DATABASE_URL 拒绝启动。real 部分（compose 起服务后 /ready 200、Dockerfile 能否构建）本机无 Docker → 未验，不标 done |
| P0-2 | Schema 基线与非破坏性收编（audit_schema.py + probe_timestamps.py + migrations/000001_baseline） | 进行中 | mock（要求 real） | 8h | P0-0 | `uv run python scripts/audit_schema.py --check-baseline` | 含 create_all 建出的无 alembic_version 存量库的人工补版本步骤。2026-10-09：scripts/audit_schema.py 落地（离线 --check-baseline + 只读 --live 两模式，判定逻辑 19 项单测），本机 --check-baseline 现在如实返回 1（migrations/ 还空着）。剩下的都必须有真库：基线 DDL 由实际结构抄录而非 ORM 声明（05 §1 末、§2.2），故 X6 仍 not_run |
| P0-3 | Go 数据访问层（sqlc + pgx pool，生成物入库并以 diff 校验一致性） | 进行中 | mock（要求 mock） | 4h | P0-2 | `uv run python scripts/dev.py gen --check` | 决策 K2 已落地：生成物入库，dev.py gen --check 作为漂移门禁（sqlc 版本钉 v1.30.0，不匹配就拒绝生成）。2026-10-09 已完成 users 认证切片的 queries + 生成物 + pgx 池 + 8 项 Go 用例；未 done 的原因只有一个——schema 源是 server/sql/schema.sql 这份**临时参照**（形状取自 ORM 声明，本机无 PG 无法核查），P0-2 出真基线后要把 sqlc.yaml 指到 migrations/ 并重跑 gen，字段有变就是那次 diff 的内容 |
| P0-4 | 契约目录（openapi.yaml + ai-execution.schema.json + error-codes.md + table-acl.md + check_contracts.py）含 429 信封定案 | 完成 | mock（要求 mock） | 8h | — | `uv run python scripts/check_contracts.py` | 五件产物齐且 X3 本机 pass；K1/K4 已于 2026-10-09 落地（backend/core/exceptions.py 两个 handler + tests/integration/{test_error_envelope,test_rate_limit_enforcement}.py），契约里不再有 As-Is 例外，故 done。原先挂的 deps:[P0-1] 已摘除：本卡只取 P0-1 的 detail 错误信封形状，该形状已在 server/internal/httpapi/envelope.go 落地并有 Go 单测，不要求 P0-1 整体（real 级 compose 证据）先完成——P0-1 的 real 缺口由 Docker Desktop 决定，与契约内容无关 |
| P0-5 | 跨语言契约测试骨架 + chain 级真实容器 fixture | 待办 | 未验证（要求 real） | 6h | P0-1、P0-4 | `uv run pytest -m chain -k contract` | 未实现端点走显式白名单跳过，不伪装通过 |
| P0-6 | 认证垂直切片（Go register/login/me + PBKDF2 golden vectors + JWT claims 兼容） | 待办 | 未验证（要求 real） | 16h | P0-3、P0-4、A0-3 | `cd server && go test -run TestVerifyLegacyHash` | P0 的唯一业务切片；X5 未全绿前 Go 不接管 users |
| P0-7 | ai-core 内部执行面（/internal/v1/ai/execute + executions 异步 + task_type 注册表 + 内部令牌 + ai_executions 表） | 待办 | 未验证（要求 real） | 14h | P0-4 | `uv run pytest -m chain -k ai_executions` | P0 只接 PARSE_PAPER / INDEX_PAPER；无 LLM 密钥时走固定小 PDF 的降级路径并标注未验段落 （需密钥） |
| P0-8 | compose 与 Windows 实跑（新增 go-api/go-worker/ai-core，nginx upstream 切 Go，ai-core 不发布宿主端口） | 待办 | 未验证（要求 real） | 8h | P0-1、P0-6、P0-7 | `uv run python scripts/dev.py up && curl http://localhost/api/v1/health` | P0 里唯一影响现网可用性的动作；保留一条配置回退 Python 的路径 |
| P0-9 | P0 端到端演示与退出复核（Playwright p0-auth.spec + p0-demo.md + 状态收口） | 待办 | 未验证（要求 e2e） | 8h | P0-8 | `cd frontend && npm run test:e2e` | 同时要求全量 uv run pytest -q 保持绿（2026-10-09 基线 333 项） |

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

- **开发机没有容器运行时，P0 的 real 级验收整体阻塞** ｜触发：本机未安装 Docker Desktop（2026-10-09 `where docker` 无结果、daemon 不存在） ｜缓解：P0-0 的 p0-environment.md §3 需要实跑记录；装上 Docker Desktop（WSL2 后端，宿主内存 ≥12GB）后按 §2 走一遍，X1/X6/X7 的容器部分与 P0-2/P0-8 才能开工
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
