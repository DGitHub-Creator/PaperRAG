# 进度报告

> 本文件由 `scripts/sync_progress.py` 从 [`progress.json`](progress.json) 生成，**请勿手改**。
> 数据截止 2026-10-17 · 基线 `106f17dd` · 投入 15-20 小时/周

## 一句话现状

- **完成了多少**：30%（按工时加权；118/394 小时，任务完成 14/40，验收 8/25 通过）
- **现在在哪**：全局开发计划已按用户确认的 24 个模块整理，入口为 docs/plans/14-feature-modules.md；后续 agent 开工先读模块、依赖、相对日程与任务交接要求。

P0 与质量整改沿用既有验收；P1/P2/P3 正式任务状态和依赖保持不变。下一步先完成 P1 五维设计人工确认，再按 G02/G03/G04 推进 Go 接管与最小研究链路。模块范围确认不自动将 proposed 改为 approved。

当前 schedule 取代旧六周公历：T0 为设计批准且环境就绪，采用每周 15–20 小时容量假设及集成缓冲；后续研究、Lab 与协作按依赖滚动重估，不承诺完整 Research OS 在前 24 周完成。产品完成度不因计划文档增加。
- **还差多少**：待办 26 项 / 276 小时（约 13.8-18.4 周），进行中 0 项；可立即开工：P1-0

## 阶段进度

| 阶段 | 目标 | 状态 | 完成度 | 验收 | 工时 | 周次 |
| --- | --- | --- | --- | --- | --- | --- |
| **P0** 架构与契约 | 搭起目标架构骨架与契约，跑通第一条垂直切片（浏览器 → Go 注册/登录/me） | 完成 | █████ 100% | 8/8 | 118/118h | 历史基线：已验收，不重排 |
| **P1** 后端迁移与最小原型 | Go 接管前端实际调用的 13 条接口，跑通上传→解析→索引→问答→引用的窄链路，全程只经 Go | 待办 | ░░░░░ 0% | 0/6 | 0/80h | T0 后 W1–W7 |
| **P2** 功能拓展与数据可信化 | 正文真相进 PG、公式检索真实生效、事件可续传、预算持久化、引用可回溯到 PDF 位置 | 待办 | ░░░░░ 0% | 0/6 | 0/114h | T0 后 W8–W17；P1 验收后 |
| **P3** 多 Agent 自主探索 | ResearchRun + Frontier + Planner/Discovery/Reader/Writer，产出可信带引用报告且崩溃可恢复 | 待办 | ░░░░░ 0% | 0/5 | 0/82h | T0 后 W18–W24；P2 验收后 |

## P0 — 架构与契约（100%）

**可演示状态**：docker compose up → 前端注册 → 登录 → 侧栏显示用户名 → curl Go /api/v1/auth/me 返回同一用户；ai-core 只内网可达

### 退出标准

| # | 标准 | 判定命令 | 等级 | 结果 |
| --- | --- | --- | --- | --- |
| X1 | 骨架能起来（2026-10-13 定案：中间件用容器、应用层源码跑，不再验容器拓扑） | `（三个终端）uv run python scripts/dev.py infra ；uv run python scripts/dev.py serve ；cd server && go run ./cmd/api —— 然后 curl http://localhost:8080/api/v1/health 与 /api/v1/ready` | 真实链路 | ✅ pass |
| X2 | Go 是唯一公开入口 | `uv run python scripts/check_nginx_routes.py` | 端到端 | ✅ pass |
| X3 | 契约已锁定且有结构校验 | `uv run python scripts/check_contracts.py` | mock | ✅ pass |
| X4 | 认证垂直切片可用且跨语言互验 token | `uv run python scripts/export_jwt_golden.py --check && cd server && go test ./internal/auth/... && uv run pytest -m chain -k go_auth` | 真实链路 | ✅ pass |
| X5 | Go 能验旧密码哈希（接管 users 的前置条件） | `uv run python scripts/export_pbkdf2_golden.py && cd server && go test ./internal/auth/... -run TestVerifyLegacyHash` | 真实链路 | ✅ pass |
| X6 | Go 不重复建表，基线迁移非破坏性且幂等 | `uv run python scripts/audit_schema.py --check-baseline` | 真实链路 | ✅ pass |
| X7 | 测试分层可用（marker 已注册且目录即分层） | `uv run python scripts/dev.py test -m unit && uv run python scripts/dev.py test -m integration && uv run python scripts/dev.py test -- tests/unit/test_pytest_layering.py` | mock | ✅ pass |
| X8 | 进度产物与真相源一致（每次提交的同步门禁） | `uv run python scripts/sync_progress.py --check` | mock | ✅ pass |

### 任务

| # | 任务 | 状态 | 证据 | 工时 | 依赖 | 验收命令 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A0-1 | 前端故障修复 + typecheck 进 CI 门禁（旧 A0-1） | 完成 | mock（要求 mock） | 3h | — | `cd frontend && npm run typecheck` | 提交 996cf777；apiFetch/BASE 未导入与上传路径缺前缀已修，4 处 TS18048 消除。typecheck 进 CI 门禁 |
| A0-3 | 鉴权与运行安全修复（旧 A0-3） | 完成 | mock（要求 mock） | 10h | — | `uv run pytest -q` | 提交 335aeb7e；当时 307 项全绿（2026-10-11 复跑 449 passed）。token 分型/WS 回查/密钥 fail-fast/限流真生效/删静默 create_all 均只在 mock+integration 层验证，真实链路属 P1 |
| SPEC-1 | spec 按四条原则重排 + 进度与可视化机制（08/09/04/06/README + progress.json/html/sync_progress.py） | 完成 | mock（要求 mock） | 8h | — | `uv run python scripts/sync_progress.py --check` | 路线改为 P0–P3；旧 Q1 与 Q5 的排期含义被取代，技术决策 Q2–Q8 沿用 |
| FE-1 | 前端结构重构：唯一请求出口 api/ + 模块单例状态层 + R1–R11 机检门禁；2026-10-14 引入 vue-router 重建为 13 个可深链接功能页（docs/rules/10-frontend-structure.md） | 完成 | mock（要求 mock） | 12h | — | `cd frontend && npm run typecheck && npm run build && uv run python scripts/check_frontend.py && uv run python scripts/check_contracts.py` | 2026-10-09 指令「前端要重构，先按核心原则把前端结构做完整做完善」。api/ 七件（types/token/events/http/sse/ws/client）取代 services/api.ts；六个 composable 统一为模块级单例并把 DOM/对话框外移 utils/dialog；DTO 按契约纠形（rag_trace 是对象不是数组，此前 trace 面板恒空白即 F7）；axios 与 style.css、MessageBubble.vue 删除。check_frontend.py 执行 R1–R11，配套 tests/unit/test_check_frontend.py 每条规则一负一正，证明门禁会红不是恒过。浏览器级回归（FE-f）本机无 Docker/PG/LLM key，如实留到 P0-9 的 X7。**2026-10-14（第九轮）：用户拍板引入 vue-router，FE-1 的范围扩到整站页面**——`AppRail`/`TopBar`/`AppShell` 外壳 + `views/` 13 个功能页（研究/分析/运行/产出/管理五组）、内联 SVG 图标集 `Icon.vue`（顺带查实 Font Awesome 从未被引入，旧模板的图标 `<i>` 一直渲染成空白）、设计令牌重写（语义色 + `.card/.badge/.table/.tabs` 等基础类）、i18n 扩到 283 键 × 两语言。未实现的后端能力一律以「示例数据」徽标 + 归属卡号标注，mock 数据放 `src/mock/` 且只用英文以过 R9；`api/client.ts` 仍是契约里那 18 个操作，`check_contracts.py` 保持绿。**2026-10-14（第十二轮）：视图层再进一步**——设置页从「文档管理」单页重做成用户设置四板块（账号 / 外观·主题 / 偏好 / 改密码，管理员页尾多一块「知识库管理」），站内 `alert`/`confirm` 全站退役换成 `useToast`/`useConfirm` + `ToastHost`/`ConfirmHost`，新增 `variables.css` 的 `[data-theme="dark"]` 令牌块与 `utils/theme.ts`（DOM 接缝），页宽统一 1280px（删 `.page-inner.wide`，10 个视图去 `wide`）——`check_contracts.py` 现为 21 个操作。 |
| P0-0 | 统一命令入口与可复现环境（scripts/dev.py + marker 分层 + .env.example 清理 + .gitattributes + p0-environment.md） | 完成 | 真实链路（要求 real） | 5h | — | `uv run python scripts/dev.py test -m unit` | 吸收旧 A0-0。dev.py 命令面已扩到 10 个子命令 doctor/up/infra/serve/down/ps/logs/migrate/test/gen（seed 顺延 P1：种数据要先有上传链路）；marker 注册 + tests/conftest.py 目录即分层 + 9 项新用例；.env.example 删死键 AGENT_ENABLED/ENTAILMENT_BACKEND、补 APP_ENV、AICORE_INTERNAL_TOKEN 标注为 P0-7 预留；.gitattributes 钉 eol=lf 并清掉原来的 gitignore 语法行。X7 已 pass（2026-10-09 记 391/57/5、全量 448；2026-10-11 复跑 449 passed）。**环境实况更正（2026-10-10 二次更正，推翻上一版「缺一次重启」）**：真因是 Docker Desktop 根本没在运行——拉起后 5 秒引擎就绪；安装形态为系统级（`（Docker Desktop 安装目录）`，`com.docker.service` Manual/Stopped），实测 Client（本机实测） / Compose Compose（本机实测） / Desktop（本机实测），与上一版记的「per-user 安装 / CLI 29.8.2 / Desktop 4.94」不符。doctor 现在把两类失败分开报：compose 自身的错走 `docker compose config`（不需要 daemon，本机已实跑通过；顺手删掉废弃的 `version:` 字段，免得每次调用都吐告警），环境没起来另说；配一条用例证明这条校验会红而不是恒过。实测 exit=1 且只列两条阻塞（daemon 没跑、缺 .env）。**2026-10-10 本机实跑补齐**：doctor 全绿 → `up` 起 7 个容器、backend 转 healthy → `/health` 容器内与宿主机均 200（`{"status":"ok","version":"0.1.0"}`）→ `migrate` exit 0；unit 361/395 通过（另 34 项受沙箱临时目录限制，非仓库缺陷）、integration 56/57（余 1 项是「断言服务不可用」的旧设计，宿主上服务已在跑必然失败，已改为显式模拟依赖不可达）。起栈过程修掉三处真实缺陷：`.env.example` 行内注释被 dotenv 当成值（应用起不来 + 13 个测试文件收集失败）、compose 缺 `target: backend`（构建出 nginx 镜像 → 永远 unhealthy）、镜像名仍按旧目录名推导（已钉为 researchpilot-backend）。证据等级 real 已达成；仍不标 done——`down`/`logs` 未在本轮逐个实跑。**2026-10-11 路径补充**：新增 `dev.py infra`（只起中间件，postgres/redis/etcd/minio/milvus/attu）与 `dev.py serve`（宿主源码跑后端 uvicorn --reload），把「源码运行 + 中间件容器」列为一等路径——免于构建含 torch 的 16.5 GB backend 镜像，改代码也不必重建；同时修正 `up` 的健康等待：只请求部分服务时按实际请求的那几个等健康，原实现写死含 backend 的 HEALTH_CONTAINERS，会让 `dev.py up postgres` 一直等一个从未创建的容器直到超时。本机实测：infra 起 6 容器全 healthy 且零构建、serve 后 /health 与 /ready 均 200（database/redis/milvus 全 connected）、经 vite 代理的 /api/v1/* 与直连后端逐字一致；顺带记录两个坑——vite 5 只监听 ::1（访问用 localhost 而非 127.0.0.1）、探针路由不带 /api/v1 前缀。**2026-10-11 README 补充**：§3 重写为「从一台全新电脑跑起来」——宿主依赖与版本要求（Docker Desktop 需运行中 / uv / Node 20+；Go 1.25.1 与 sqlc v1.30.0 仅在动 Go 侧时需要）、五步命令（clone → .env → uv sync → doctor → infra → serve，前端 npm install + npm run dev）、跑起来后的验收表、起不来的三处排查。**2026-10-12 第三轮转 done**：本卡唯一欠的证据是「`down`/`logs` 没逐个实跑」，环境重建后补齐，全部在 Windows + Docker Desktop 上真跑：`doctor`（.env 重建后全绿）→ `up postgres redis` 两容器 healthy → `ps` 表格正常 → `logs postgres` exit 0（30 行带容器前缀的输出，其中 `PostgreSQL Database directory appears to contain a database; Skipping initialization` 正好证明数据在 bind mount 里）→ **`down` exit 0**（容器与 `milvus` 网络都移除、`docker ps -a` 无残留）→ 再 `up` 回来，**表数仍是 10、alembic head 仍是 `add_paper_knowledge_graph`**（`volumes/postgres` 21 MB 与 `PG_VERSION` 全程未动）。建库这一步走的是**宿主** `alembic upgrade head` 而不是 `dev.py migrate`——后者是容器内 alembic，需要构建 16.5 GB 的 backend 镜像，只为建库不值得；`migrate` 子命令的实跑证据仍是 2026-10-10 那次 7 容器全栈记录。⚠️ 两条本轮新踩到的环境事实，比「命令能跑」更值得记：①**compose 没有顶层 `name:` 时项目名会退回目录名**，本机目录仍叫 PaperRAG，于是容器标签是 `paperrag`、自动创建的网络/具名卷会带 `paperrag_` 前缀，且换目录 clone 就换一个项目名——已在两份 compose 里钉成 `researchpilot`（台账 C26）；②**改完 `CustomWslDistroDir` 之后 Docker Desktop 自己退出过一次**（`docker desktop status` 报 Is Docker Desktop running?、进程数 0），所以搬盘之后第一次 `logs`/`down` 其实失败了（报的是 `dockerDesktopLinuxEngine` 管道不存在），必须 `docker desktop start` 重来一遍才算数——**命令返回非零时先分清是脚本缺陷还是引擎没在跑**（`AGENTS.md` §5 那条老规矩这轮又应验一次）。 |
| P0-1 | Go 服务骨架（cmd/api + cmd/worker + Chi 路由 + slog + trace_id + detail 错误信封 + health/ready） | 完成 | 真实链路（要求 real） | 8h | P0-0 | `cd server && gofmt -l . && go vet ./... && go test ./...` | 16 项 Go 用例绿：/ready 失败用 {"detail":{...}} 信封、成功平铺；探测键名 database 与超时文案 "timeout after Ns" 逐字对齐 backend/api/health.py；404/405/500 都走 FastAPI 同款信封；trace_id 生成与透传；panic 兜底；生产缺 DATABASE_URL 拒绝启动。real 部分本机条件已具备（Docker 自 2026-10-12 起可用，此句原写「本机无 Docker」已过期）；**2026-10-14（第十轮）**实测宿主源码起 go-api 后 `/api/v1/health` 与 `/ready` 各 200（真实 PG 探活），但 X1 还要求 `ai-core` 由 `dev.py serve` 真起（本轮上游是仓库外 stub），故仍不标 done **2026-10-14 第十五轮转 done（real）**：real 缺口原本是「未进 compose、未与 Python 联调」，前者被 2026-10-13 的定案取消（容器只跑中间件，进 compose 不再是验收条件），后者已经发生——chain 层 15 项用例让 go-api 与源码跑的 ai-core、真 PG/Redis 双向互验（X4 的 Go 签发→Python 校验就是这一向），X1 的两条探针也在真进程上拿到 200 且 database/redis 两个键都是 ok。⚠️ 一条边界别说过头：**go-worker 今天只验到「进程能起 + 暴露探针」**（`cmd/worker/main.go:52` 自陈 worker_idle，调度器与 Frontier 属 P3），所以本卡的 done 覆盖的是骨架与门面，不是编排能力。 |
| P0-2 | Schema 基线与非破坏性收编（audit_schema.py + probe_timestamps.py + migrations/000001_baseline） | 完成 | 真实链路（要求 real） | 8h | P0-0 | `uv run python scripts/audit_schema.py --check-baseline` | 含 create_all 建出的无 alembic_version 存量库的人工补版本步骤。2026-10-09：scripts/audit_schema.py 落地（离线 --check-baseline + 只读 --live 两模式，判定逻辑 19 项单测），本机 --check-baseline 现在如实返回 1（migrations/ 还空着）。剩下的都必须有真库：基线 DDL 由实际结构抄录而非 ORM 声明（05 §1 末、§2.2），故 X6 仍 not_run。**2026-10-11 真库审计已跑通**：--live 需显式导出 DATABASE_URL（脚本不读 config 默认值，已写进 .env.example），导出 docs/reference/schema-baseline.json —— PG 15.18、10 张表、alembic head=add_paper_knowledge_graph、ORM 与真库漂移 23 处。剩余交付：server/migrations/000001_baseline.{up,down}.sql 按真实结构抄录并让 --check-baseline 返回 0，X6 才能转 pass。**2026-10-11 已完成并转 pass**（X6），同时暴露三处必须记下的事实：①`audit_schema.py` 的 `--live` payload **不含列清单**（只有 tables/alembic/tz/server_version/indexes/constraints/column_diff），所以基线的列名/类型/NOT NULL/DEFAULT 是抄自真正建库的 alembic 链（head 与 baseline 的 `alembic: head:add_paper_knowledge_graph` 一致），再用 column_diff 机器交叉验证（DDL 里「无 DEFAULT」的列集合 = 漂移 23 条，完全一致；无 type/only_in_orm 漂移）——**要让基线可直接抄录，应给 payload 补 `columns`**，否则 varchar 长度与 NOT NULL 无机检覆盖；②`--check-baseline` 只判文件形态，且 down 规则不剥注释、up 规则剥注释（注释里写 DROP TABLE IF EXISTS 会被误判成违规），这是校验器自身的不一致；③真库是 **10 表**（含 `alembic_version`），`05 §2.2` 写的「现存 9 表」应更新；`alembic_version` 是否算 Go 基线对象、down 能否作用于存量库，两项待拍。**2026-10-12 收尾与新增机检**：①上面那条「sqlc.yaml 指到 migrations/」的收尾已完成（临时参照 `server/sql/schema.sql` 删除，见 P0-3 note），顺带推翻两条旧记录——本机其实**已装** sqlc v1.30.0（`$HOME/go/bin/sqlc.exe`，`dev.py` 早就优先用本机二进制），且 diff 门禁抓不到 DEFAULT 类失真；②列级 fidelity 终于有机检：`--live` 的 payload 补 `columns`，新增离线模式 `--verify-columns` 逐列比类型/varchar 长度/NOT NULL/DEFAULT（SERIAL 的 nextval 按库侧口径算，快照缺 `columns` 时如实 exit 2 而不是假绿），up/down 的注释规则也统一（台账 C1/C2），`test_audit_schema.py` 由 19 项增至 37 项（15 项列级机检随本条落，另 3 项随 000002 落地），含「解析真基线得 10 表/59 列」这条防解析器脱节的用例。**仍未 done 的两条，都要 Docker**：仓库现存那份 `schema-baseline.json` 是补 `columns` 之前导的，`--verify-columns` 现在返回 2，得重跑 `--live` 才真比得上；`probe_timestamps.py` 与 `timestamp-audit.md` 未产——探针法/分布法/交叉法三种判定全都要往库里写或读，而「每表时间列判定」是 X6 验收明文列出的第三问。**2026-10-12 二次核查更正（台账 C20）**：上面「都要 Docker」这个说法**不够准**——daemon 现在可达，但**数据面被清空了**（0 镜像 / 0 卷），导出 `schema-baseline.json` 的那个原真库随之消失且不可复原。所以这两件事的前置不是「等 Docker 起来」而是「**先重建环境**」：补 `.env`（已丢失）→ `dev.py infra` 拉 6 个中间件镜像（约 4 GB，docker.io 有 DNS 污染）→ `alembic upgrade head` 建库 → 再 `--live` 重导。⚠️ 重导出的是**全新库的快照**：它能给 `--verify-columns` 提供列级机检对象（varchar 长度 / NOT NULL / DEFAULT），但**不能**再当作「历史存量库的形状」使用，X6 的存量库那一问已按历史证据收口。**2026-10-12 本轮（环境重建后）转 done，两条尾巴都解了**：①`--live` 重导成功，快照现在带 `columns` 段（10 表 / 59 列，alembic head `add_paper_knowledge_graph`，`column_diff` 仍是 **23 条**——与原库审计的漂移画像一致，说明重建库结构对得上），`--verify-columns` 从「拒跑 exit 2」变成真正的逐列比对 **exit 0**（类型/varchar 长度/NOT NULL/DEFAULT 四项）；②`scripts/probe_timestamps.py` 落地并产出 `docs/reference/timestamp-audit.md`（11 个 naive 时间列逐个判定），配 `tests/unit/test_probe_timestamps.py` 25 项。幂等在真 PG **15.19** 上重测：空库跑 000001 两遍 = 0→10 表→10 表、两遍 exit 0；**存量形态**（把重建库的结构 `pg_dump --schema-only` 复制进临时库，即已存在 10 表）跑 000001 两遍各 30 条 `already exists, skipping`、表数恒 10、exit 0；`000002` 连跑两遍 10→11→11、`ai_executions` 恰 **17 列**、exit 0；down 跑一遍有效、第二遍报 `does not exist` 退出 3（这是 `migrations/README.md` 里「禁止 `DROP TABLE IF EXISTS`」那条规则的**预期后果**，不是缺陷）。探针法还**实测证实了 `05 §4` 的断言**：会话时区 `Asia/Shanghai` 下 aware `datetime.now(UTC)` 写进 naive 列会落成 +8 小时偏移的挂钟值（07:08:09→15:08:09），而 `sql_now_at_tz_utc` 与字面量两条路径恒为 UTC——以前这是推断，现在是量出来的。补齐的交付件：`server/migrations/README.md`（此前卡片列了它但文件不存在，现在写了：编号表、up/down 规则、「必须同批登记 sqlc.yaml」、两条门禁的口径差别，以及**这里目前没有执行器**这件事）。⚠️ 三条诚实边界照旧：分布法/交叉法**没有存量数据可判**（重建库是空的，而带历史数据的那个库已永久消失，所以这不是「等以后有数据」）；今天的「存量库」是 alembic 建出来的形态，**不是**原来那个 `create_all`+alembic 混合库；PG 从 15.18 变成 15.19 是因为 `image: postgres:15` 是浮动 tag（台账 C25） |
| P0-3 | Go 数据访问层（sqlc + pgx pool，生成物入库并以 diff 校验一致性） | 完成 | mock（要求 mock） | 4h | — | `uv run python scripts/dev.py gen --check` | 决策 K2 已落地：生成物入库，dev.py gen --check 作为漂移门禁（sqlc 版本钉 v1.30.0，不匹配就拒绝生成）。2026-10-09 已完成 users 认证切片的 queries + 生成物 + pgx 池 + 7 项 Go 用例（`internal/db` 实数，原文记 8 项已核正）；未 done 的原因只有一个——schema 源是 server/sql/schema.sql 这份**临时参照**（形状取自 ORM 声明，本机无 PG 无法核查），P0-2 出真基线后要把 sqlc.yaml 指到 migrations/ 并重跑 gen，字段有变就是那次 diff 的内容。**2026-10-11 真基线落地后的反查结论**：`server/sql/schema.sql` 这份临时参照在 `users.created_at` 与 `users.role` 两列上**失真**——真库有 `DEFAULT now()` 与 `DEFAULT 'user'`（否则这两列会出现在 column_diff 里），而该文件与 `05 §4` 写成「库里无 DEFAULT」。切 `sqlc.yaml` 时必须以这份已知差异核对 diff；真库还有两处「如实登记不修正」的漂移：**没有** `ix_paper_nodes_id`（ORM 声明了但真库没落库）、`paper_nodes.filename` 与 `users.username` 的唯一性由 unique index 承载而非 UNIQUE 约束。**2026-10-12 done（mock）**：`sqlc.yaml` 的 schema 源已切到 `migrations/000001_baseline.up.sql`，临时参照 `server/sql/schema.sql` 删除，与本卡的 `gen --check` 是同一原子改动。切换那次 diff 的实际内容推翻了一条原定的核对方法，必须记下：`User` struct 与 `users.sql.go` 三条查询**逐字未变**——**sqlc 不把列默认值编码进 Go 类型**，所以「在 diff 里专门核对 `role`/`created_at` 的 DEFAULT」做不到，diff 门禁的能力边界是类型/可空性/列与表的存在性；DEFAULT 的机检归 `audit_schema.py --verify-columns`。真正一次性补回来的是此前完全缺席的 9 张表 / 54 个字段（parent_chunks、chat_sessions、chat_messages、workspaces、workspace_members、paper_nodes、citation_edges、glossary_entries、alembic_version）——临时参照的代价不是「字段写错」而是「Go 只看得见一张表」。同批给 `dev.py gen` 加了三条生成前置检查并各配负向用例（共 9 条新单测，`test_dev_cli.py` 18 项）：schema 源若是含 `.down.sql` 的目录则拒绝（sqlc 按文件名顺序执行，down 排在 up 前 → 先 DROP 再 CREATE，生成物按回退后的库产出）；`migrations/*.up.sql` 未登记进 schema 列表则拒绝（新迁移建了表而 Go 看不见，重生成不报错只静默少一张表）；`internal/db/X.sql.go` 无对应查询则拒绝（sqlc 只写不删输出）。这三条都是本机实跑踩出来的，其中第二条当场抓住我一次 `sqlc.yaml` 编辑没生效。验收实跑：`dev.py gen --check` 生成物无漂移 + `cd server && gofmt/go vet/go test ./...` 全绿。**deps 摘除理由**（沿用 P0-4 的同款判断）：本卡只取 P0-2 的基线 DDL 产物，该产物已于 2026-10-11 落地并拿到 X6 的 real 证据；P0-2 未 done 的剩余项（时间列探针、含 columns 的快照重导）与本卡的生成一致性无关，把它算成阻塞会让一张已验完的卡永远不能 done。**本卡残留的诚实边界**：model 的 NOT NULL/类型正确性目前只有离线证据（DDL 解析 + column_diff 交叉验证），与真库快照的逐列机检要等 Docker 重导 `--live`；`requires` 本就是 mock，故按 mock 判 done。仍未接真库、未进 compose（属 P0-1/P0-8 的 real 缺口） |
| P0-4 | 契约目录（openapi.yaml + ai-execution.schema.json + error-codes.md + table-acl.md + check_contracts.py）含 429 信封定案 | 完成 | mock（要求 mock） | 8h | — | `uv run python scripts/check_contracts.py` | 五件产物齐且 X3 本机 pass；K1/K4 已于 2026-10-09 落地（backend/core/exceptions.py 两个 handler + tests/integration/{test_error_envelope,test_rate_limit_enforcement}.py），契约里不再有 As-Is 例外，故 done。原先挂的 deps:[P0-1] 已摘除：本卡只取 P0-1 的 detail 错误信封形状，该形状已在 server/internal/httpapi/envelope.go 落地并有 Go 单测，不要求 P0-1 整体（real 级 compose 证据）先完成——P0-1 的 real 缺口由 Docker Desktop 决定，与契约内容无关 |
| P0-5 | 跨语言契约测试骨架 + chain 级真实容器 fixture | 完成 | 真实链路（要求 real） | 6h | P0-4 | `uv run pytest -m chain -k contract` | 未实现端点走显式白名单跳过，不伪装通过<br>**2026-10-14 第十三轮 done（real）**。产出 `tests/chain/`：`_runtime.py`（地址解析 + preflight 策略，纯函数）、`conftest.py`（真库种子与两侧令牌）、`test_go_auth_cross_validation.py`（X4 的 `-k go_auth`，4 项）、`test_contract_chain.py`（本卡判据 `-k contract`，5 项）。实跑形态与判据读数：6 中间件容器 healthy + `dev.py serve`（127.0.0.1:8000）+ `dev.py go-serve`（:8080），`pytest -m chain` **9 passed**，`-k contract` 收 5 项、`-k go_auth` 收 4 项（**都不是收 0 项 rc=5**），全量 593 passed 零回归。<br>**「不伪装通过」落成了可证伪的三档**：①`preflight_action(markexpr)`——显式 `-m chain` 时起不来就**红**，被全量收集路过才 skip；这条分档由 `tests/unit/test_chain_runtime.py` 的正反用例钉住（写反成恒 skip 就会红，而那正是 X4 从 not_run 起一直没被发现的失效模式）。②种子**直接写 PG**，不用被测面铺数据，否则接口坏了会以「铺数据失败」的形态报错。③`checked >= 5` 兜住静态门禁自己失效（`test_rate_limit_signatures.py` 那条）。卡片原句里的「未实现端点白名单跳过」本轮**没用到**——只对两侧都已实现的端点做对拍；等 P1 逐条接管时若需要，再按那句补。<br>**deps 摘除 `P0-1` 的理由**（沿用 P0-3/P0-4 的同款判断）：本卡要的是「有一个能跑的 go-api 进程」，那个进程已由 P0-6 + 第十轮交付并被这 9 项用例真打过；P0-1 整体未 done 缺的是**服务侧探测键集合补齐**（X1 的 Redis 那一格）与编排能力，与本卡的测试骨架无关。<br>**副产品**：这条 chain 层第一次真跑就抓到台账 **C32**（五条 Python 面任何合法请求都 500，slowapi 的按名形参缺失，而 572 项 mock/integration 全绿抓不到）——这正是「端到端优先」这条原则要买的东西：局部全绿不等于链路通。同时新记 **C33**（Go 无限流层，接管即丢） |
| P0-6 | 认证垂直切片（Go register/login/me + PBKDF2 golden vectors + JWT claims 兼容） | 完成 | 真实链路（要求 real） | 16h | P0-3、P0-4、A0-3 | `uv run python scripts/export_pbkdf2_golden.py --check && uv run python scripts/export_jwt_golden.py --check && cd server && go test ./internal/auth/...` | 认证垂直切片：Go 的 register/login/me + 改密码 + 偏好，PBKDF2 与 JWT 两套 golden vectors。判据 `X4`/`X5`；real 档由 chain 层的真容器互验取证（Go 签发↔Python 校验、login/me 逐字对拍）。欠账不在本卡：X5 的 `--from-db` 真库形状统计仍不可执行（C20），P1 接管 users 前必须先跑一次。 |
| P0-7 | ai-core 内部执行面（/internal/v1/ai/execute + executions 异步 + task_type 注册表 + 内部令牌 + ai_executions 表） | 完成 | 真实链路（要求 real） | 14h | P0-4 | `uv run pytest -m chain -k ai_executions` | ai-core 内部执行面：`/internal/v1/ai/*` 七条 + `ai_executions` 迁移 + `AICORE_INTERNAL_TOKEN` 校验（未配置即拒绝，比较走 `hmac.compare_digest`）。P0 只注册 `PARSE_PAPER`/`INDEX_PAPER`。real 档由 `pytest -m chain -k ai_executions`（12 项）取证，成功路径走**真解析器读真 PDF**。⚠️ 两条如实的边界：①注册的两个类型都**不调 LLM**（`usage.calls=0`），所以本卡没有"真 LLM 成功执行"这回事，LLM 调用随 P1 的 LLM 任务类型落地；②表已落库但 `ExecutionStore` 仍是进程内 dict、**零写入方**（台账 C37）。 （需密钥） |
| P0-8 | Go 服务接线与跨环境实跑（源码形态：Go 侧启动接线 + nginx upstream 切 Go；不再新增应用容器） | 完成 | 真实链路（要求 real） | 8h | P0-1、P0-6、P0-7 | `uv run python scripts/dev.py infra 起中间件，宿主源码起 go-api 与 ai-core 后 curl http://localhost:8080/api/v1/health（原判据是 dev.py up 全栈容器，2026-10-13 定案后作废）` | Go 服务接线与跨环境实跑（源码形态）：`dev.py go-serve` + `nginx/nginx.conf` 的 `/api/`、`/api/v1/ws/`、`= /health`、`= /ready` 全部切 `go-api`（保留一行可回退 Python 的配置，04 §5）；prod compose 新增 `go-api` 服务（`server/Dockerfile` 构建、不发布宿主端口）；`check_nginx_routes.py` 按 dev/prod 形态分判 R4 并新增 R5（dev 不得出现应用服务）；台账 C29 四处遗留物全部处置。⚠️ X2 的证据是**静态配置级**：没在这台机器上起过 prod 全栈容器（16.5 GB 镜像）。 |
| P0-9 | P0 端到端演示与退出复核（Playwright p0-auth.spec + p0-demo.md + 状态收口） | 完成 | 端到端（要求 e2e） | 8h | P0-8 | `cd frontend && npm run test:e2e` | P0 端到端演示与退出复核：`frontend/e2e/p0-auth.spec.ts`（Playwright，9 项）+ `frontend/playwright.config.ts`+ `npm run test:e2e` + `docs/plans/p0-demo.md`。**结构级**：断言路由/DOM/属性/文案，不判像素。⚠️ 三条口径：①用例落在 `frontend/e2e/` 而不是卡片原写的 `tests/e2e/`（Node 从仓库根找不到 `node_modules`），`pytest -m e2e` 因此仍收 0 项、rc=5；②每条用例自己注册新账号——Playwright 每条一个新 context，登录态不跨用例；③本机 Playwright 的 chromium 包两次都只落 `chrome.dll`，实跑用 `E2E_BROWSER_CHANNEL=chrome`，不设该变量仍回默认 chromium。 |

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

**本阶段不做**：不做 Frontier 与多轮规划（P3）· 不做 chunk 可信化（P2）· 不宣称引用为证据链（P1 引用为非证据级）· 不为兼容提前实现 P2 的存储方案，也不建临时表/兼容层/双写（2026-10-15 定案 D4，见 08 §10 与 04 §4.4）

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
| Z6 | 论文自动抓取与主题书架可用（数据入口不再只有人工上传） | `uv run python -m pytest -q -m integration -k "acquisition or topic_cluster"` | 真实链路 | ⬜ 未跑 |

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
| P2-9 | 论文自动抓取与元数据识别（arXiv API / DOI→CrossRef / 按研究方向检索导入，去重 + 任务态复用 ai_executions） | 待办 | 未验证（要求 real） | 12h | P1-3、P0-7 | `uv run python -m pytest -q -m integration -k acquisition` | 2026-10-13 立项（用户拍板：把产品轴缺口登记进分母，接受完成度下降）。现状是**代码零存在**：backend/ 全仓 grep arxiv / doi / crossref / httpx / requests 无命中（唯一 doi 是 academic_cleaner.py:47 的正文正则），入库只有人工上传一条路。抓取属网络型长任务，必须走 P1-3 的持久化任务态，不能用 upload_jobs 的进程内存态（台账 C9） |
| P2-10 | 主题分类与语义书架（知识库自动成主题群 + 主题检索入口） | 待办 | 未验证（要求 real） | 10h | P2-1、P2-9 | `uv run python -m pytest -q -m integration -k topic_cluster` | 2026-10-13 立项（11 §4.1 的语义书架 / 主题分类，原挂在 §8 缺口清单第 2 项）。现状：全仓无聚类或主题分组代码。**必须排在 P2-1 之后**——在 Milvus 的 VARCHAR(2000) 截断副本上算主题，等于给不可信数据打标签，与 11 §7 的 P1 引用非证据级口径冲突 |

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
| T0前 | 待 P1 设计批准与环境就绪 | G01：核对全局模块与五维设计，形成可认领任务；模块确认不自动批准设计 | 设计准备；M17 | planned |
| W1–W7 | 相对 T0 第 1–7 周预留窗口 | G02→G03→G04：Go 接管、上传任务、问答/引用窄链路与真实 E2E；验收后进入下一阶段 | P1；M1/M6/M8/M17/M19 | planned |
| W8–W17 | P1 收口后；相对窗口随实际完成顺延 | G05/G07→G06、G08、G09：PG 正文、学术结构/定位、事件/用量、导入/书架与科研回归 | P2；M1–M9/M17/M18/M23 | planned |
| W18–W24 | P2 收口后；相对窗口随实际完成顺延 | G10→G11：Run/Frontier/worker、固定研究闭环、恢复与 PARTIAL 报告；不提前做双图 | P3；M8/M13/M15/M17 | planned |
| W25+基础扩展 | P3 收口并完成各包设计后滚动重估 | G12/G13/G14/G18/G20：项目精读、比较/书目版本、双图证据、首个受控工具与模型治理 | 后续规划；M2/M5/M7/M8/M10/M16/M18/M19/M20/M23 | planned |
| 后续研究增强 | 相关工作区、比较和证据前置验收后再排具体周次 | G15/G16/G17：候选问题/假设、Critic/动态路线、接地写作与 Radar/Knowledge Diff | 后续规划；M11/M13/M14/M15/M21/M22 | planned |
| 后续Lab | G18/G12/G14 验收与 Lab 方案确认后滚动排期 | G19：先完成一个实际形式化或复现实验纵向链，再扩展其他学科 | 后续规划；M12/M19/M20 | planned |
| 后续协作部署 | 单用户研究能力稳定且权限/部署设计确认后排期 | G21：团队共享/审核、机构隔离、安装升级和备份恢复；不提前做计费 | 后续规划；M8/M17/M24 | planned |

## 待你拍板

- **D1** 总纲要求 ai-core/ 独立目录，路线建议保留 backend/ 物理目录、ai-core 只作角色名，是否接受？ → 建议：接受（决策 Q2 + 原则④），改名留到 P2 后作为可单独回滚的提交（P0 目录结构）
- **D2** 13 条在用接口在 P1 迁完、其余 12 条在 P1 末统一 Deprecation，是否符合总纲 P0 完成标准里「旧接口必须迁移或标记 deprecated」？ → 建议：符合原则①；若要求 P0 内完成则 P0 估时翻倍（P0 退出标准 X2）
- **D3** chunk 可信化移到 P2 且改在 Go 侧 schema，接受 P1 引用为非证据级？ → 建议：接受；证据级引用属 P2 的 Z1/Z3（P1 演示口径与 README 表述）
- **D7** 是否按 ARTEX 的分层习惯，把 evidence / report / llmpool（含用量记账）/ guard / tools（MCP）/ notify 在 Go 侧升为一等模块？（02 目前把它们散在 P3/P4 展望里） → 建议：接受其中三个：evidence（L4 的直接承载）、report（V2 报告 + V4 Research Writing）、llmpool + 用量记账（P2-6 预算持久化的前置）；guard / tools(MCP) / notify 等 V3/V4 再定（02 的模块划分与 P3/P4 的边界）

## 风险登记（前 8）

- **开发机没有容器运行时，P0 的 real 级验收整体阻塞（2026-10-11 已解除）** ｜触发：2026-10-09 判为「本机未安装 Docker Desktop / WSL 组件装完待重启」；2026-10-10 现场核查**推翻**：Docker Desktop（本机实测）（系统级安装，Client（本机实测） / Compose Compose（本机实测））一直都在，只是没在运行——启动后 5 秒引擎即就绪。真实阻塞是缺 .env（且 LLM_API_KEY / LLM_MODEL 是硬要求，只验骨架也必须有值）与 docker.io 的 DNS 污染 ｜缓解：已解除并留下证据：p0-environment.md §3 的 up/ps、/health 200、migrate 均已实跑记录；中间件 6 容器 healthy；镜像源与本地代理（本机代理 本机代理端口）已配好。剩余风险转移到数据面：chunk 正文仍只在 Milvus 且 VARCHAR(2000) 截断，见 G10/G11/G12
- **本机 Docker 数据面易失：一次清空就连真库带 real 级证据一起抹掉（2026-10-12 已实际发生一次，台账 C20）** ｜触发：容器卷不是持久的成果存储——`docker system prune --volumes`、Docker Desktop 重置、数据盘迁移都会连库一起清掉。本轮实测 `docker system df` 四项全 0，导出 `schema-baseline.json` 的原真库随之**不可复原**（本机也无原生 PG）；`.env` 同样丢失（`.gitignore` 忽略、从未入库）。清空原因未查明，所以不能假定它不会再来一次 ｜缓解：①real 级证据一律落成**仓库内文件**（快照 / 实跑记录 / golden vectors）——只存在于卷里的证据视为没有证据；②X6 的「存量库幂等」按 2026-10-11 的历史实跑记录收口，**不拿 `alembic upgrade head` 重建出的全新库自证充数**；③环境重建序列写进台账 C20 与 `AGENTS.md` §3（补 `.env` → `dev.py infra` → 建库 → 重导 `--live`），可复制执行；④`.env` 的三个必填项在 README §3 与 `.env.example` 里都有，丢了能重建，但**原值不可恢复**（`JWT_SECRET_KEY` 换值等于让既有 token 全失效——本机开发库无妨，生产环境必须先备份）
- **Go 依赖拉不动，P0-1 之后每张 Go 卡都开不了工** ｜触发：proxy.golang.org 在中国大陆不可达（本机 dial tcp 实测超时）；go mod tidy 连依赖的测试依赖一起解析 ｜缓解：机器级 `go env -w GOPROXY=https://goproxy.cn,direct`，容器构建用 --build-arg GOPROXY；已写进 p0-environment.md §4 第 7 条。go.sum 入库保证离线也能 build
- **Go 验不了旧密码，接管后用户登录全挂** ｜触发：PBKDF2 base64 编码差异（标准 vs urlsafe）、盐长度、迭代数 ｜缓解：先导出 golden vectors，X5 全绿前 Go 不接管 users
- **SSE 形状漂移导致前端流式显示异常** ｜触发：Go 侧缓冲/flush 策略、nginx X-Accel-Buffering ｜缓解：P1 契约测试比对 Python 与 Go 的字节级帧序列
- **同一份业务状态被双写** ｜触发：切换窗口内 Python 仍在写 chat_messages ｜缓解：单写者原则 + feature flag + 写路径断言，接口逐个切换
- **P1 的引用被当成证据链宣传** ｜触发：chunk 真相层尚未建立，引用来自 Milvus 截断副本 ｜缓解：前端与 README 显式标注非证据级；证据级属 P2 验收（Z1/Z3）
- **6 周日程与 solo 投入不匹配** ｜触发：总纲按全职强度估 6 周；solo 15–20h/周下 P0+P1≈5–6.5 周，P2 落在 W7 后 ｜缓解：不可压缩项固定（P0 骨架/契约/认证、P1 E2E），日程在 progress.json 里显式标 overtime 而非偷改日期

## 图例

- 状态：待办 / 进行中 / 完成 / 延期 / 取消。**只有达到要求证据等级才能标完成**（`--check` 强制）。
- 证据等级：`mock` 单元级（外部依赖全 mock）< `real` 真实容器链路 < `e2e` 真实浏览器。
- 完成度按工时加权，`deferred`/`cancelled` 不计入分母。
