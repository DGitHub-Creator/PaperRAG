# WORKLOG —— 逐轮实录（append-only，倒序）

> **性质：日志，不是权威。** 这里记「哪一轮做了什么、拿到什么等级的证据、留下什么坑」。
> 内容冲突时：规约听 [`rules/08`](rules/08-principles-and-conventions.md)，进度听
> [`progress.json`](progress.json)，现状听 [`reference/13`](reference/13-frontend-backend-architecture.md)，
> 待办听 [`plans/12`](plans/12-known-code-issues.md) 台账。
>
> **为什么单独一份**（2026-10-15 用户明确要求）：`AGENTS.md` 只放愿景 / 规约 / 硬约束，
> `progress.json` 的 `current` 只放当前读数与下一步，任务卡的 `note` 只放卡片定义。
> 这三处从前都长成了日志——一个字段几万字、一张卡片 note 塞满实跑读数——结果是"规约"要翻很久才找得到，
> 而"日志"散在四个地方互相重复。日志一律进本文件。
>
> **轮转规则**：一个阶段（P0 / P1 / …）收口后，把该阶段的轮次移进 [`archive/`](archive/README.md)，
> 本文件只留当前阶段（与 `08 §6`「文件体积」同一条纪律：日志也会长，长了就轮转，不要无限追加）。
>
> **每条格式**：日期 + 一句话结论 → 做了什么 → 证据等级与读数 → 留下的坑 / 指针。
> 写的时候遵守 `08 §6`：只写**为什么**与**当时量到了什么**，不复述代码在做什么。

---

## 依赖安全审计 · 前端闭环、Python 分组待办

- 代码检查点 **355e504d 已 push 到 main**；R11 本批代码发布已核实，未推送历史备份分支。
- npm 审计原有 10 项（8 high）；先用非 force 的兼容修复减少到 3，再升级 Vite 7.3.7 / 插件 6.0.10 / KaTeX 0.18.10，Vue 3.5.44 与 Playwright 1.64.1 下限同步，最终 0 项已知风险。选择 7 而非审计默认建议的 8，避免无必要跨越更多版本。
- 升级后 typecheck/build + Chrome 12 项专项通过。随后类型与元数据对齐（Node 类型 24、engines、声明下限、移除旧 @types/katex 改包自带类型），typecheck 与 npm 审计仍通过。
- CI 与 Docker 前端构建默认 Node 24，Node 20 已结束支持，依据 [Node 官方支持周期](https://github.com/nodejs/Release#release-schedule)。本轮未构建完整 Docker 镜像，不据配置校验宣称容器验收通过。
- Python pip-audit 只读扫描当前 .venv 的 **178 个安装包**，**32 包 / 235 条已知漏洞记录**，无依赖收集跳过项。范围不包括未安装的跨平台/可选依赖。没有自动 --fix 或大范围 uv 升级。
- 需优先审查上传解析/Web、网络/加密、LLM 工具栈及 Torch 的适用条件与兼容修复；python-jose 的一项无修复候选，不能用忽略规则制造安全绿灯。明细、候选与分组验收已写入 TODO R12。
- 边界：公告命中不等于每项均可从本项目路径利用；当前仍存在待处置依赖风险，不宣称全仓合规。未保留审计后台进程或测试服务。

## 全仓整改续批 · 真实入口验收与第二轮故障修复

- 发布：上一批基线 2a44ad65 已 push 至 origin/main；本批按 TODO R02–R11 跟踪，质量整改不增加产品完成度。
- R02：历史追踪不合法时只将可选追踪置 null、保留正文并告警，不记录原始追踪；新写入严格校验。检索来源和引用结果随答案持久化，历史回显区分 supported 真/假。REST/SSE 按已声明 RagTrace 投影，契约不再承诺任意字段透传。
- R03：注册 role 的契约、Python DTO 与 TS 输入类型对齐；漂移门禁从真实 DTO 提取类型/可空性/默认值。真 HTTP 对拍缺省/null/空串/root 与 admin 关闭分支；有效邀请码和其他注册错误仍未穷尽。
- R04：移除解析/分块/多模态测试的全局 sys.modules 伪模块与自制假 splitter；实际已安装库下关联 36 passed。替换空 refresh 测试为真实 401 断言，移除链路 fixture 的旧会话缓存清理旁路。
- R05：首次真实登录验证发现 Python 信任已关闭仍可被 X-Forwarded-For 绕过，根因是 Uvicorn 提前改写 client 地址。已在 dev.py、main.py、app.py、Docker 与验证入口关闭底层代理头改写，应用按可信 CIDR 判定；HTTP/WS 限流均增加项目 Redis 命名空间。复验两侧第 21 次均 429，伪造头无效，Go 删除后两侧消息立即不可见。
- R10：Go 迁移空库后 Python init_db 曾 exit 1、DuplicateTable；隔离库已实证。已接管库改为只读检查 schema_migrations（版本至少 3、clean），未接管旧库保留 Alembic；没有 stamp、重建或 create_all 兜底。真实空库启动和旧库失败/dirty 单测通过。
- R06（部分）：ACL 的 present/planned 与迁移机检；登记目标权限和当前实际写入偏差，修正 D6 状态描述。尚未完成实际角色/GRANT 与索引必要性审计。
- 本批真实证据：verify_storage.py --http 的存储组 **18 passed**、Go/Python HTTP 组 **17 passed**；仅临时库与随机测试账户，两个进程自动退出、隔离库已删除。前端 typecheck/build 与 Chrome 专项 **12 passed**，Go vet/test 通过。
- 回归过程中曾在运行测试时更新进度生成物，导致一项生成物一致性测试读到不同版本（其余 665 passed / 48 skipped）。已停止并发修改生成物，最终回归结果另行补记，不将该次失败报成全绿。
- 最终复验：Python **666 passed / 48 skipped**；进度生成物停止变动后全绿。Ruff 与全部仓库/契约/路由/前端/设计/拓扑/基线/golden 门禁通过。Docker 查询隔离库剩余 **0**；本轮 PG/Redis 已停止，无常用应用端口监听，数据卷保留。
- 新增 --http 已接入存储 CI job；未据本机通过推定远端 Actions 已通过。未解决项继续见台账与 TODO。

## 2026-10-17 · 第二十一轮 —— G01 批准后开工：P1-0 收口，并把它的空判据补实

**一句话**：环境核验后按依赖顺序先收 P1-0（它是 P1-1 的前置），结果发现它的判据
`pytest -m chain -k proxy` **一条代理行为都没测到**——补了 6 条才算数。

- **环境核验**：Docker 引擎 29.8.2（`docker desktop start` 起，GUI exe 仍归用户手动路径）；
  `up postgres redis` → 两容器 healthy；`dev.py migrate-go version` → **5 clean**
  （`000004/000005` 是远端新增，`init_db` 现在要求 version ≥ 5 才肯启动 Python，
  所以"拉完代码先 migrate-go"是硬前置，不是可选步骤）。
- **P1-0 的判据是空的**：`-k proxy` 当时只命中 `test_rate_limit_login_twenty_first_request_and_spoofed_proxy`
  两条——它们名字里有 proxy 是因为**伪造 X-Forwarded-For**，测的是限流，不是转发。
  命令能跑、用例能绿、结论却什么也没证明，这正是本仓库反复登记的那类错（C22 的 `rc 恒为 1`、
  C31 的"契约声明了但服务侧无机检"同一族）。
- **补的 6 条**（`tests/chain/test_go_proxy.py`，真栈）：路径与 query 原样到达上游、Bearer 透传后
  经 Go 与直连 Python 拿到逐字相同 JSON、未鉴权信封两侧一致、**追踪号单值且入站值被沿用**
  （C38 的修复在这里第一次有了运行证据）、通配转发不遮蔽 Go 原生探针、未接管面不被提前 404。
- **读数**：`-m chain -k proxy` = 6 passed / 2 skipped（那 2 条要 `verify_storage.py --http` 的隔离栈，
  按设计不抢共享环境）；全链层 **34 passed / 16 skipped**。完成度 31%，8/25 退出标准通过。
- **状态变化**：P1-0 `done(real)`；P1-1 `in_progress`（依赖规则"已开工不得有 pending 前置"由此成立）；
  schedule 的 T0前 → 已完成、W1–W7 → 进行中。`check_design_review.py` 在 approved 状态下仍绿，
  而 `--check` 会拦任何"没批准就开工"的卡——这条门禁今天第一次真的在放行而不是在拦。
## 2026-10-17 · 第二十轮 —— CI 两条红分别修掉；顺带把 C37 的口径同步进审查文档

**一句话**：拉进远端的模块全景与依赖整改后，CI 仍红两条，**两条都不是"发现漏洞/发现缺陷"，而是判据自己站不住**。

- **红一条：后端 `Run tests`**（#53/#54 红，根因同 #44 一族）。
  `tests/unit/test_websocket.py` 直接调 `create_access_token`，它读模块级 `JWT_SECRET_KEY`——
  也就是**读开发机的 `.env`**。CI 没有 `.env` → 空密钥 → pyjwt 抛 `InvalidKeyError`。
  本机永远有 `.env`，所以本地 696 全绿而 CI 红。
  修法照仓库既有做法（`test_auth.py` 已经用 `patch.multiple(..., JWT_SECRET_KEY=TEST_SECRET)`），不另立约定；
  **patch 必须同时罩住签发与验证**，只罩签那半，失败会伪装成"令牌无效"，看不出根因。
  取证：**把 `.env` 改名再跑全量**（与 CI 同条件）= 696 passed / 68 skipped，跑完复验 `.env` 在位。
- **红二条：`Audit reachable Go vulnerabilities`。** 它不是报漏洞，是**工具在 CI 的目标平台上崩**：
  `7b8e705` 把 `server/go.mod` 的 `go` 指令提到 **1.27.2**，而钉死的 `govulncheck@v1.1.4` 里的
  `x/tools v0.29.0` 在建 SSA 时 `panic: unexpected expr: *ast.KeyValueExpr`。
  关键教训是**复现方式**：本机默认目标（windows/amd64）扫同一棵树报 "No vulnerabilities found"，
  看起来"我这儿是绿的"——**换成 `GOOS=linux GOARCH=amd64` 扫才复现 panic**。
  处置：CI 与 `AGENTS §9` 的钉版一起升到 `v1.9.0`（同一条 linux 目标扫描 → `No vulnerabilities found.`），
  并把"钉版要跟着 go 指令走、判据要跨平台跑一遍"写进 AGENTS。
- **C37 口径同步**：远端 `0eafe02` 已补 `PostgresExecutionStore`（`internal_api/router.py:36` 装配，
  带 advisory lock 与两个幂等轴，落库证据在 `tests/integration/test_execution_postgres.py`，
  需 `REFACTOR_TEST_DATABASE_URL`，本机 skip、CI 真跑）。台账由远端更新，我把
  `contracts/p1-design-review.md` 数据所有权一节里"零写入方"那句改成已闭——**审查文档留着一条已作废的缺陷当依据，比没写更糟**。
- **读了新全局计划**（`docs/plans/14-feature-modules.md`，24 模块 / G01–G21 任务包 / T0 = 五维设计审查批准 + 环境就绪）。
  它明写"不能自动把 proposed 改成 approved"与"命令绿本身不算批准"，与我上轮建的门禁语义一致；
  所以 **T0 现在唯一挡着的就是 §6 那五个 `☐`**。
- **续：C38 的第二条复验成立并修掉了，另外登记 C39。**
  真栈（`up postgres redis` + `migrate-go` 补应用 `000004/000005` → `version: 5 clean` + `serve --no-reload` + `go-serve`）
  实测 `curl -D - :8080/metrics` 给出**两行相同的 `X-Trace-Id`**。
  修法在 `upstream.go` 的 `ModifyResponse` **丢弃上游那份**（边缘才是权威），单测
  `TestUpstreamEmitsExactlyOneTraceHeader` 钉"只有一个值"而不是"值相等"。
  **过程里我自己错了一次**：第一版把 `ModifyResponse` 写成 `Set`，以为覆盖即可——实际只把上游的
  2 个值收成 1 个，中间件先前 Set 的那份仍在，总数还是 2；是新加的单元测试把它抓住的（不是真栈）。
  修后四条路径（直连、经 Go、入站自带 id、经 Go 打未接管业务面）各只有一个值，入站 id 照常沿用。
  **仍未决的两条**（都写进 C38，不塞进本轮）：①`X-Trace-Id` 还没进 `openapi.yaml`；
  ②两端生成的 id **长度不同**（Go 16 hex / Python 直连 32 hex），经 Go 时被覆盖所以看不出来——
  统一成哪种属契约级，随 G01 批准一起定。
- **C39（新登记，未修）**：`go-api` 在 dev 监听 `0.0.0.0:8080`（`config.Load` 默认 `:8080`），
  局域网可直连公开入口，而它带 `/internal/*` 反代前缀。不能简单改成回环——prod 里 nginx 要连得上去。
  正确做法是监听地址由环境给（dev 由 `dev.py go-serve` 注入回环，prod compose 显式给 `0.0.0.0`），
  属部署形态决定，**要拍**，所以登记而不是顺手改。
- **chain 层在真栈上的读数是 28 passed / 16 skipped**（skip 的那批要 Milvus 与显式隔离 URI），
  我的代理改动没破跨语言对拍；中途一次 11 条红是**我重启 serve 时漏了 `AICORE_INTERNAL_TOKEN`**，
  服务端按设计拒绝一切内部请求所致——不是回归，但值得记：这条红在 CI 上永远看不见（那边 chain 全 skip）。
- **远端把 `dev.py serve` 的启动加了库侧门禁**：`init_db` 现在要求 `schema_migrations.version >= 5` 且不 dirty，
  否则拒绝启动（不再回退 `create_all`）。这条与我本轮"迁移必须先显式跑"的定案一致，
  但它意味着**拉完代码要先 `dev.py migrate-go`**，否则 Python 起不来——写进 C38 之外的操作事实。

- **副作用记一笔**：拉取改了依赖锁，`uv run` 自动重装环境（含 torch 118 MB）；C 盘已 90% 满、剩约 11 GB。
## 2026-10-16 · 实质重构与文档治理（持续进行）

- 根因整改：会话按轮事务追加，不再覆盖历史；移除跨服务会话缓存。AIExecution 改用既有 PG 表，修复幂等、租约、终态与过期；持久记录不代表崩溃后执行恢复。
- 修复真实 LangGraph 执行、工具 artifact、消息累积与共享预算；LLM 配置导出、超时、流式提交顺序与取消收尾。后续工具轮次保留既有来源。
- 文档同步/异步共用索引执行路径；实际上传大小限制、staging、成功指纹原子更新及 Redis WATCH/MULTI 状态保护。解析失败保留旧索引，但跨存储写入仍非原子事务。
- Go 原生路由增加 Redis 固定窗口限流、可信代理 CIDR 与故障关闭；Python WS 复用限流并校验消息。FastAPI 改用 lifespan，同步数据库操作移出事件循环。
- 前端修复截断 SSE、迟到响应串会话、WS 中断 loading 与上传取消/非法 JSON；净化 Markdown。
- 文档：精简 AGENTS，重写 README 与 docs 导航；台账/模块规划移 plans、现状移 reference，三方分工只保留职责；P0 日志及旧混合文档正文归档。契约引用同步修复。历史失败与早期测试数不再写作当前状态。
- 数据：修改开发库前备份至本地忽略目录 .tmp/backups/development-before-storage-refactor.sql，SHA256 58864c3a1a62c756a63da5fef1f04c7aa8f7f47656ac7e17a319fa0560929384；应用既有 Go 迁移至 version 3 clean，原有 10 表行数不变。新增真库快照 13 表/83 列；83 列的类型/长度/可空性/DEFAULT 有无与迁移逐项匹配。ORM 对照中 only_in_db 的 25 项属于非 ORM 管理表，不是已声明业务列的类型/长度/空值/默认值漂移。
- 工程：uv.lock 下载来源规范到官方 PyPI；对比锁文件包名/版本集合无升级，新增直接声明已使用的 limits。新增真实存储 CI job；GitHub CI 本身尚未远端运行。
- 验证：完整 Python **652 passed / 39 skipped**，无弃用警告；未启动完整链路的 chain 及需独立环境的测试跳过，不算 real。末次工具来源保留改动后专项 **6 passed**。隔离 PG/Redis **17 passed**；Go 全包 vet/test 与真实 Redis 并发限流通过；前端 typecheck/build 及系统 Chrome **11 项专项通过**。静态门禁和生成物核对结果在本批收尾复验。
- 收尾：Ruff、仓库/契约/路由/前端/设计/拓扑门禁、进度生成物及 sqlc 无漂移通过；末次审计/仓库专项 42 passed。新增 CI job 仅作本地 YAML 结构检查，未远端执行。历史私钥头/GitHub token 两类差异扫描未命中，不代表完整泄露审计。PG/Redis 已停止，无本轮应用端口监听；数据与备份保留。
- 未决：见当前问题台账，包括索引跨存储恢复、可靠执行调度、rag_trace 历史投影、注册对拍、ACL 与长时 Milvus 负载；不把这些标成已完成，不调整 P1/P2 阶段进度。

## 2026-10-16 · 全仓规范化首批整改（尚未完成）

用户授权检查仓库全部自有文件、数据库、文档及 Git 治理；TODO 见
[repository-standardization.md](plans/repository-standardization.md)，规则见根 AGENTS.md §9。

- 已修：Markdown 最终净化与失效高亮配置；Go 响应包装的 flush/hijack 与追踪号透传；
  Python 请求追踪、日志轮转、布局分析临时文件与 PDF 释放；异常链；文档失败状态与会话异常传播；
  等长向量配对；文件名和 Milvus 字符串转义。文档任务执行与认证 DTO 按已有职责拆分。
- 工程：清除 requirements.txt 的外机路径和无关 freeze，移除重复依赖；新增 EditorConfig、
  Ruff 异常/安全规则与 check_repository.py，并将仓库检查接入 CI。
- 验证：Python **645 passed / 27 skipped**（未起完整应用链路，chain 跳过）；Go 全包 vet/test 通过；
  前端 typecheck/build 通过，Markdown 安全与正常显示 **6 项 Playwright/系统 Chrome 通过**。
  Ruff、契约、前端结构、路由归属、设计门禁、nginx 拓扑、基线形态与 59 列快照比对通过。
- 数据库：仅启动 PostgreSQL/Redis。原开发库现有 **10 表**；分别创建空白隔离库与原库的
  **仅结构副本**，通过真实 Go 迁移执行器连跑两遍 up，均为 **version 3 clean / 13 表**；
  最后一份迁移 down 1 → up 也通过。两份隔离库均已删除，原库保持只读。
  这证明本轮结构重跑和最后一步回滚，不证明所有含数据迁移及故障恢复语义。
- 边界：仍有待审模块、鉴权/限流/缓存、真库漂移治理、Git 历史和现行文档语义审查；
  不宣称全仓已合规，不改变产品轴 30% 或将 P1 卡片标为完成。


P0 阶段此前日志已轮转至 [历史实录](archive/2026-10-15-p0-worklog.md)，正文保留，不作为本轮运行依据。

## 2026-10-17 · Python 依赖安全首组

- R12 首组按官方索引解析兼容约束，锁定上传/PDF/图片/请求相关 8 包安全更新；提高 3 个直接依赖下限，未升级模型栈，也未修改第三方源码。
- 增加真实 PDF 经 LangChain/PyPDF 提取正文回归；完整 Python 667 passed / 48 skipped，uv pip check 通过。跳过不算真实链路。
- pip-audit 对当前安装的 176 包报告 24 包/118 条，首轮 178 包为 32 包/235 条；117 条减少来自本批 8 包，frozen sync 清除未声明 neo4j/pytz，模型/Web/加密剩余风险仍在 TODO。审计的缓存跨盘写入警告未阻止报告生成。
- Ruff、契约、前端结构、路由归属、设计、nginx 与数据库基线/列快照门禁通过；本轮不启动服务，不变更数据库，不以离线回归充当真实业务验收。

## 2026-10-17 · 用户要求暂停，全仓整改交接

- 用户因额度不足要求就近停止。本批工作区改动全部保留，尚未提交或推送；最后已推送提交为 `b0f13edd`。全仓整改未完成，不调整产品完成度。
- 本批涉及依赖与 JWT、父块事务存储、Office/PDF 解析、BM25 文件并发、索引崩溃恢复、上传任务与 AIExecution 重放、数据库约束及审计。均须以最终复验确定完成状态。
- 最新真实 PostgreSQL/Redis/Milvus 专项结果为 **27 passed / 1 failed**；其中 4 项索引崩溃恢复通过。失败项为执行重放测试的 PDF 样本清洗后无有效块；样本已修正，尚未重跑。后续 HTTP 阶段未执行。
- 最近相关单元批次 133 项通过；最近全量 Python 为 672 passed / 60 skipped / 2 failed。两项路由枚举失败已通过恢复兼容 FastAPI 版本处理，相关 30 项通过，但此后仍有改动，尚无最终全量通过证据。最后 Ruff 通过。
- 完整锁文件安全审计曾覆盖 207 个 PyPI 版本且无发现；之后增加 Office 解析依赖，必须重新审计。Go 全量检查也早于本批最后修改，需复验。不宣称真实模型问答端到端已通过。
- 开发库已迁移到 **version 4 clean**，13 表行数未变；**当前 Python 启动代码要求 version 5**，新迁移 000005 仅在隔离库验证。恢复时先核对迁移及备份，再迁移开发库，不能直接认为当前代码可以启动。
- 迁移前备份：`.tmp/backups/before-index-constraints-4e3204d7bbba49b0ae643212825ea6a8.sql`，SHA256 `231695ad6aaad511bf79af2dcf6e502df8846ef6723749d148e26f719f6c9476`。
- 已删除本轮隔离 Milvus 测试容器及网络，停止本轮启动的 PostgreSQL/Redis；清理后无运行中容器。保留数据卷、镜像、备份和测试文件。
- 续接顺序：核对工作区及 version 5 迁移 → 重跑失败专项及真实 HTTP → 最终依赖审计和全仓门禁 → 对齐 AGENTS/README/架构现状与整改清单 → 分关注点提交。数据库最小权限、剩余现行文档语义和远端 CI 等仍待处理；详细任务见 [整改清单](plans/repository-standardization.md)。

## 2026-10-17 · 恢复整改并完成本批验收

本节取代上节暂停交接中的未完成判断；保留原暂停记录，不追改当时结果。

### 根因修复

- 依赖：完整锁审计覆盖所有 PyPI 平台/可选组，移除无调用方且公告未修的 ChromaDB；python-jose 替换为 PyJWT，Go 使用严格签名编码校验，保留既有令牌契约。FastAPI 取兼容路由检查的 0.135.x，保留安全 Starlette；真实微型 BERT/SentenceTransformer/嵌入前向验证兼容，不下载或冒充真实 BGE 质量。
- 存储：父块改 PG 事务 UPSERT、去缓存，默认 PDF 补章节父块；BM25 使用跨进程文件锁、唯一临时文件与原子发布，按实际存留叶子重建统计，保留维度。索引写前持久化 pending，PG 共享/排他锁隔离检索与写入，缺原文或指纹不符拒绝恢复；核心检索失败不再返回空成功。
- 恢复：Redis 文档任务私有上下文不对外返回，启动重放并通过操作锁排除活跃进程；AIExecution 首次输入写入 JSONB，重放换租约、终态与取消保护，拒绝旧租约结果。不新增 Go 全局调度替代品。
- 数据库：000004 删除 7 个主键重复索引、增加成员唯一性，重复行使整笔失败，不删业务数据；000005 补执行重放输入，down 拒绝丢弃未结束输入。锁等待前限制并发、预留嵌套连接；只读认证查询后立即释放连接。
- 运行权限：新增显式角色配置工具，创建/更新当前 Go/Python 受限角色；拒绝外部同名角色、额外成员/对象所有权及 PUBLIC 额外权限。生产应用不再得到数据库管理员或另一运行账号密码；实际权限保留旧 Python 认证/会话必要写入，不提前实现 P1 唯一写入接管。开发 .env 未改。
- 配置：开发中间件仅回环绑定，生产模板拒绝占位凭据、显式内部令牌/代理网段、Milvus 正确传入 S3 凭据。Redis 可丢弃缓存使用有界 SCAN，不记录带凭据 URL。生产镜像提供显式迁移/角色配置工具，不将 DDL 放入启动路径。
- Go 补充安全：govulncheck 首轮发现 11 条可达公告；升级 Go 1.27.2、x/text 0.41.0（同时对齐 x/sync），Go 镜像升级到对应工具链及 Alpine 3.24.2。依据：[Go 修复发布](https://go.dev/doc/devel/release#go1.27.2)、[Alpine 受支持分支](https://alpinelinux.org/releases/)。

### 本轮证据与边界

- Python 全量此前 696 passed / 67 skipped；新增权限专项后的最终全量读数在下方收尾记录，不把跳过计入真实通过。
- 最终真实 PG/Redis/Milvus/权限专项 **29 passed**，受限角色运行的 Go/Python HTTP **26 passed**；旧 PDF 样本失败已修正并重跑。涵盖真实 PDF 解析、PG/Redis/Milvus/文件/BM25、强制退出后的索引/执行恢复；嵌入权重使用固定向量隔离，不能证明真实模型检索质量。
- Go 1.27.2 下全包 vet/test 通过，govulncheck 返回 No vulnerabilities found；uv pip check 对 178 个已安装包通过，完整锁文件审计 205+5=210 个版本无发现。npm audit 为 0，前端 typecheck/build、12 项 Playwright 系统 Chrome 专项通过。
- 全量回归后的开发工具/配置/缓存/结构审计单元批次 **99 passed**；Ruff 与仓库/契约/前端结构/归属/设计/nginx/数据库基线门禁通过。sqlc 已用 v1.30.0 实际重生成；提交前 gen --check 因合法未提交生成物报差异；存储提交后重跑已通过，生成物无漂移。
- Go API/worker/migrate 镜像已实际构建，临时无网络容器核验二进制、000005 文件与 UID 10001。生产 compose 使用隔离 env_file 覆盖和临时随机值做 config --quiet 通过；未创建生产密钥文件，未部署。Python/nginx 完整部署镜像与远端 CI 不冒充已验证。
- 开发库备份 `.tmp/backups/before-execution-replay-9dbd833da6bf4f28ae24b6ec7a241c07.sql`，SHA256 `da923f3a5adf00062b0ab8b179d5ffbfeb28b2e707b6c1982a872b72dd95fd82`；迁移后实际 **version 5 clean**，13 表/84 列与全部 up 逐列一致。快照 26 个 only_in_db 均为 Go/工具/反射表的未映射列，不是业务 ORM 类型漂移。审计连接为开发管理员，不代表生产受限账号。
- 已核实本轮隔离数据库/角色均为 **0**；删除隔离 Milvus 容器及网络、停止本轮 PG/Redis，结束后无运行容器或 5173/8000/8080 监听；保留卷、镜像、原文、备份及本地测试材料。
- AGENTS、根 README、docs 导航、迁移手册、数据库计划、架构现状、台账、整改 TODO 与进度生成页同步。历史资料保留当时事实；当前规则不存测试计数/机器读数。产品仍未完成的 Go 接管、PG 全文证据链、逐 token 输出与真实模型端到端保持未完成，不将质量修复计入产品进度。

### 最终交付收尾

- 最终停容器全量首跑暴露 8 项检索单测依赖本机 PG（688 passed / 8 failed / 68 skipped）；为两个检索单测模块增加显式 SQL 会话与临时状态文件 fixture，未替换检索/合并/读保护核心或放宽断言。对应 22 项通过，随后在所有容器停止条件下完整 **696 passed / 68 skipped**。
- 依赖安全提交 `7b8e705c`，存储恢复与权限提交 `0eafe02b`；部署配置、规范与现行文档独立收尾。每次提交更新 progress.json 并同步生成物，产品任务状态不变。超过 400 行的锁文件/跨存储恢复提交在提交信息说明不可拆的兼容与一致性边界。
- 本批暂存区分别经 Gitleaks 扫描无发现；发布前继续扫描 main 可达历史，不推送含历史个人信息的本地备份分支，不改写无实际问题的旧历史。
- 本批质量整改已完成有证据的代码/数据库/依赖/文档治理；未来产品实现与未做的完整模型、长时负载、Python/nginx 部署镜像及远端 CI 验收仍按 TODO 保留，不用本地门禁替代。

## 2026-10-17 · 已确认的全局模块计划与 agent 交接

- 用户确认 24 个模块并要求纳入 AGENTS 开工入口及提交 GitHub。复用现有 docs/plans/14-feature-modules.md，整理为全局模块、边界、依赖、相对日程及 G01–G21 交接任务包；没有新增服务或目录，也没有启动后续功能开发。
- AGENTS、根 README、docs 导航、愿景和迁移路线同步指向全局计划，避免未来 agent 将旧缺口描述或六周讨论当当前排期。
- progress.json 的 schedule 改用设计批准/环境就绪为 T0 的相对窗口；按现有 80/114/82 小时卡片及每周 15–20 小时假设预留集成缓冲，后续能力按依赖滚动重估。只改计划元数据与日程，不变更正式任务状态、deps、工时、证据和阶段退出条件。
- 计划中的新增链路测试路径属于未来验收设计，未伪报已有测试；明确零收集/跳过不能验收。模块范围批准不替代 proposed P1 五维设计的人工签署。
- 验证：模块 M1–M24 各出现一次、G01–G21 全覆盖所有模块且依赖无环；与 HEAD 比对确认正式任务/依赖/工时/证据/退出标准及未决设计未改。仓库链接、进度生成一致性、契约、设计审查与 diff 检查通过；本轮仅文档/排期变更，不启动服务或冒充产品验收。

## 2026-10-17 · 计划准入与已完成修复分离

- 核对当前源码与现行台账：C33 限流、C34 追踪投影、C35 移除会话缓存均已修复；修复不是取消能力，也不等于 P1 接管卡完成。日程仍仅取 progress.json.schedule，全部计划窗口与正式任务状态不变。
- 修正 route-ownership 的会话详情/删除/缓存说明，详情仍为 proxy。G01 批准且环境就绪后，详情读取可作 G02 首个候选切片；已有 go_read 对拍只证明既有行为，不证明 Go 原生实现。
- 重整 proposed 五维审查，删除旧的内存执行存储、会话吞异常、盲目混跑迁移及“无流式契约”等过期前提；区分 D6 已有审计与待定目标归属。补充 trace 两种生成长度及头契约缺口、占位名对齐和流式兼容建议，五项人工确认保持未勾选，不修改 OpenAPI 或批准任何方案。
- 本轮为文档校准，未启动服务、未重跑真实 HTTP 栈，限流/投影历史证据仅引用原有记录。检查结果：仓库链接、契约、路由归属、设计审查结构、进度生成一致性及 Git diff 检查通过；正式 phases、schedule 与变更前逐项相同。结构通过不代表设计批准。

## 2026-10-17 · 用户授权五维设计批准与执行交接

- 用户明确要求按推荐方案确认并上传 GitHub，具体实现交给另一个 agent。P1 审查状态改 approved，五维签署注明本轮授权来源；保留双通道/现有生成长度/业务键与迁移分流，明确 trace 输入边界及 D6 过渡处置。
- 审查 §8 明确第一切片、环境核验、真实读取与退出旧路径的验收要求。现有 OpenAPI 和运行实现尚未按新建议修改，不以设计批准代替完成证据。
- progress.json 同步“设计已批准、环境待核验”；正式任务状态、工时、阶段依赖不变。schedule 不擅自启动 W1，产品进度不增加。包含上一轮尚未提交的过期依据修正文档，一并交付。

- 发布整合：远端新增 CI、JWT 测试隔离、C38 登记与反代追踪头去重提交，已保留；设计审查冲突合并保留已持久化、advisory lock 与双幂等轴事实。文档门禁复验通过，不宣称复验远端代码的运行行为。

## 2026-10-18 · G02 首切片：会话详情 GET 的 Go 原生接管（代码完成，判据待跑）

- 环境核验：T0 前置确认 `migrate-go` 全部落地、postgres/redis 容器 healthy、`:8000`/`:8080` 两侧健康检查 200；判据在同一条指令下统一跑完（见下文"已跑的部分"）。
- 契约补齐：`contracts/openapi.yaml` 的 `RagTrace` 从 2 个 property 补到 39 字段并新增 `RetrievedChunk`/`SourceReference`/`CitationInfo`/`UnsupportedClaim`，required 仍只有 `tool_used`/`tool_name`；把"读取投影"四条口径（必需键不符→整条 null、未声明键丢弃、缺失可选键补 null、嵌套元素不合法连带整条）写进 description。同时删掉 `GET /api/v1/sessions/{session_id}` 的 **404 声明**——两侧真实行为都是 200 + `{"messages": []}`，契约在承诺一个没人实现的状态码。
- 新增机检：`scripts/check_contracts.py` 的 `check_trace_projection` 做契约↔pydantic 模型↔Go 字段表的逐字段核对（名字、顺序、种类、必需性、嵌套指向）；`check_trace_header` 核对追踪头的头名与接受集合在三处字面量一致。配套负向单测：字段改名/删字段/种类错/嵌套指错/表写法变了/整块 schema 被删/常量被改名，每条都必须红。
- Go 实现：`server/internal/session/trace.go` 按契约做 JSON 列的读取投影（按文档顺序解码、重复键取首位置末值、`isoFormat` 复用列表接口那一份）；`DetailHandler`+`Service.Detail`+sqlc 查询 `ListMessagesForUserSession`（`ORDER BY cm.id`，按 `cs.user_id`+`session_id` 过滤）；`server/cmd/api/main.go` 注册显式路由。`httpapi.WriteJSON` 关闭 HTML 转义并去掉结尾换行，对齐 Starlette 的 `ensure_ascii=False` + 紧凑分隔符——否则正文里一个 `&` 就两侧字节不同。
- 实测纠正的三处取值集合分歧：pydantic 宽松模式下 `int` 字段收 `"10.0"`→10、收 `true`→1 而拒 `"1e2"`，`float` 字段收 `true`→1.0，`str | int` union 把 `"10.0"` 留在字符串分支。原 Go 投影在这三种形状上会把整条追踪变 null，而 Python 给出对象——已按实测集合改 `projectInt`/`projectFloat`/`projectBool`，并把这些形状钉进 Go 单测与 chain 用例。
- C38 闭合：追踪头进契约（`components.parameters.TraceId`，`^[A-Za-z0-9._-]{1,128}$`），Go `SanitizeTraceID` 与 Python `sanitize_trace_id` 同一接受集合；非法或缺失即新生成且**不回显**，生成长度按 §6 保留 Go 16/Python 32 的差异。Python 侧用 `fullmatch` 而非 `match`（`$` 在 Python 里允许结尾换行前的位置，会多接受 `"abc\n"`）。
- 判据自我纠错与补强：`tests/chain/test_go_proxy.py` 有两条用例原本以 `/api/v1/sessions*` 做"转发"探针，而这两条面本卡已搬 Go 原生——继续留着就是"测了一个不经过上游的转发用例"，且照样绿。已重锚到仍在 Python 的 `/api/v1/stats/usage`，用 403（认出用户、拒绝角色）与 401（头没送到）之差证明 Bearer 透传，并新增"就地提权后响应体原样透传"一条（403/401 证明不了 body 没被改写）。另证：全仓 Python 路由不读 query（`grep -rn 'Query(' backend/api/` 零命中），故 query 原样转发只在 Go 单测层用桩上游断言 `URL.Path`/`URL.RawQuery`，这点写进了文件 docstring 以免后人再拿真栈去证观测不到的东西。
- 越权用例的补法：会话详情原先只有"不存在的会话回空数组"，那不是越权——`chat_sessions` 的唯一约束是 `(user_id, session_id)`，所以新增一条**同一个 session_id 挂在另一个用户名下**的用例（`twin_foreign_session`），断言响应里不含对方正文；过滤器一旦漏掉 `user_id` 就会红。追踪头的接受集合也补了 chain 层两侧用例（非法值不回显、128 边界值必须沿用；非 ASCII 值不在真栈测，HTTP 头值只能 latin-1，客户端先报错）。
- 新登记 C40：卡标题里的 `/documents` 两条面不能在 P1 原生接管——`GET /api/v1/documents` 的清单真相是 Milvus 全集合扫描（`backend/api/documents.py:102-114` 的 `query_all` 再按文件名数块），PG 无对应表；删除面还叠加进程内 job 管理器与 `UPLOAD_DIR`。Go 接管只能新造 Milvus 客户端复刻聚合（违反 14 §19 铁律 2「门面先于重写」）或等 G05 真相层。旧文档那句"读文件系统 `UPLOAD_DIR` + `ingested_state.json` + Milvus 的 chunk 数"其实把 `/documents/ingest`（那个才读 ingested_state）和列表面混成了一件事，归属表现已按代码改正。⚠️ 收口口径需用户拍板，本轮不改卡片标题、依赖与工时。
- 已跑的部分与其真实边界：本轮按"代码与用例全部写完 → 统一跑一轮"的顺序执行。环境=postgres/redis 容器 healthy、`migrate-go` 全部落地、`:8000` 与 `:8080` 两侧健康检查 200。结果：Go `gofmt`/`go vet`/`go test ./...` 九个包全绿；Python **unit 671 passed**、**integration 64 passed / 24 skipped**、**chain（相关面）46 passed / 18 skipped / 0 failed**；`check_contracts`、`check_route_ownership`、`check_design_review`、`check_nginx_routes`、`check_frontend`、`sync_progress --check`、`check_repository`、`audit_schema --check-baseline` 八条门禁全过；ruff 干净。
- 三条 chain 红是**用例自身的前提错**，都不是被测实现的缺陷，已逐条改正后复跑：①JSON 字符串标量那组根本铺不进库（`CAST('不是对象' AS json)` 被 PG 拒），要存标量必须传带引号的 JSON 文档 `'"不是对象"'`；②`/api/v1/stats/usage` **自己就是请求计数面**，两次调用必然把 `count` 与 `last_accessed` 改掉，拿它比字节是在比测试数据；现改为该面比条目集合、字节级对拍换用 `/documents/upload/jobs`（两侧打同一进程，任务表不因读而变）；③删除响应对拍拿两个**不同的 session_id** 比整串字节，`session_id` 字段按定义就不同，现归一化后比字节、单独断言键序与文案。另修一处夹具接口不一致（契约篡改器一个按元组、两个按 callable，导致 TypeError 而非规则红）。
- 契约新增的追踪头说明里点了源码路径 `server/internal/...`，被既有守卫 `test_internal_surface_stays_out_of_the_public_contract`（要求 `/internal/` 字面量不得出现在公开契约里）如实判红。**守卫是对的，改我的措辞**，已改成不含该字面量的表述并复跑通过。
- 内部执行面（`tests/chain/test_ai_executions.py`，10 error + 1 fail）本机**跑不了且与本次改动无关**：`.env` 里没有 `AICORE_INTERNAL_TOKEN` 这个键（实测读出的长度为 0），服务端按设计对所有内部面一律拒绝。10 个 error 是夹具 `pytest.fail` 要求注入令牌；那 1 个 fail 同因——它断言 `detail == "内部令牌无效"`，而未配置时服务端给的是另一句"AICORE_INTERNAL_TOKEN 未配置，内部执行面拒绝服务"，两个 401 原因本来就不同。该组的实现另有 `tests/unit/test_ai_executions_store.py` 与 `tests/unit/test_internal_error_codes.py` 在本轮 671 项里覆盖。要跑这组需要给本机 `.env` 补一个令牌并让服务端与测试进程取到同一个值，属环境配置，不在本轮改动面内。
- **两条收口动作等用户拍板，未擅自执行**：①退出 Python 旧路径（`nginx/nginx.conf` 里 `upstream backend` 是**文档化的回退路径**，删掉 Python 的会话读面会让那条回退失效）；②C40 的 `/documents` 接管口径。详见 `contracts/route-ownership.md` 与台账 C40。
- 归属与现状：`contracts/route-ownership.md` 里 `GET /api/v1/sessions/{session_id}` 由 `proxy` 改 `go` 并登记对拍用例名（该行现在是"Go 已原生 + Python 对拍保留待删"），`GET /api/v1/documents` 的说明按代码改正并指向 C40；`contracts/p1-design-review.md` §0 的会话详情现状行同步为已接管。契约的 `RagTrace` 声明、追踪头参数与路径占位名（`{sessionId}`/`{jobId}`→snake_case，只改契约符号不新增 URL）一并落进 `openapi.yaml`。
- 状态口径（本条已被下方"同日追记"更新）：P1-1 仍 `in_progress`，P1-0 保持 done 但其 chain 用例本轮被重锚；完成度、工时、阶段依赖与退出标准一律未改。
- **同日追记：CI 抓出我一个真回归，红得对。** push 后远端 `Backend (pytest + ruff)` 判 failure，而我上一轮报的"unit 671 passed"是**改卡片状态之前**的读数——把 P1-2 转成 in_progress 之后我只重跑了门禁，没重跑单测。复现方式是把 `.env` 临时改名跑全量（CI 的 backend job 既没有 `.env` 也没有 PG service）：`tests/unit/test_check_design_review.py::TestTakeoverCoupling::test_draft_phase_is_not_blocked` 红，734 passed / 1 failed。
- 根因不在门禁而在夹具：`progress_with()` 直接拿真实 `docs/progress.json` 当基线，只把**点名的那一张**改成给定状态，其余保持真实值。于是"P1-1 pending 且审查 proposed 必须绿"这条负向用例会因为**另一张卡**在别的时间转 in_progress 而失败——G5 报"没批就开工"是正确判定，夹具却默认整个 P1 都是 pending。已改成先把 P1 全部卡归到 pending、再只动点名那张，并把理由写进夹具 docstring：夹具依赖易变的真实状态，等于把单测变成进度表。有无 `.env` 两种条件下该文件均 20 passed。
- **教训**：改 `docs/progress.json` 的任务状态后必须重跑读它的单测（`test_check_design_review.py` 与 `sync_progress --check` 都读它）。上一轮"八条门禁全过 + unit 671"因此是过期读数，在此更正，不以局部绿冒充整体绿。
- 范围收口（用户批准）：P1-1 与 P1-2 转 `done(real)`，两卡**标题**摘掉 `/documents` 条目使标题与 D9 范围一致；工时、依赖与阶段退出标准一字未动，完成度上升只反映卡片计数。旧路由退场时点统一到 **P1-4**（会话读两面、会话删除面、auth 三条写面），理由与逐行去向写进 `contracts/route-ownership.md` 表头与决策 D9；`/documents` 系列按 D9 归 G05 真相层。本轮 done 的确切含义：Go 原生接管完成且真栈验收通过，**不含**旧路径删除。
- 同批把 G02 的**判据承载物补齐**（都属"命令能跑而被测的东西没被测"这一类，与 C31/C22 同型）：
  ① P1-2 的 `verify` 是 `pytest -m chain -k go_write`，而该选择器**收集 0 项**——这张卡从来没有证据。新增
  `tests/chain/test_go_write_sessions.py` 七条：删除 200 响应体逐字对拍、Go 删除后 Python 读路径立刻空、
  越权删除两侧同一份 404 且他人行不动、**同号不同用户**只删请求者那一行、并发删除恰好一个赢家
  （钉"按受影响行数判成败"而不是先查再删）、并发注册撞 `users.username` 约束恒为一行、注册与登录跨边缘同形。
  ② `scripts/verify_storage.py --http`（G02 的验收命令）原先只跑两个 chain 文件，会话详情与写面都不在集合里，
  已把 `test_go_read_session_detail.py`、`test_go_write_sessions.py`、`test_go_proxy.py` 一并纳入隔离栈。
  ③ `contracts/route-ownership.md` 里 `/auth/register` 那行原登记为"**未**对拍保留（C36）"，现在有跨边缘用例了
  才升级成"对拍保留"并指向它——顺序反了就是用一个不存在的证据占住一条遗留。
  ④ `contracts/table-acl.md` 的会话两行按代码改正：读路径已随 P1-1 收口，**写路径退出时点仍未拍板**
  （随 P1-4/G04 问答链接管一起定），所以运行角色一条权限都不撤——按目标提前撤权是设计审查 §5 明令禁止的。
- 这七条与前面的对拍用例**都已执行**：dev 栈 `-k go_read` 24 passed、`-k go_write` 5 passed / 2 skipped（skip 的两条要隔离 Redis 前缀）、`-k proxy` 8 passed / 2 skipped；`verify_storage.py --http` 隔离栈两阶段 25 passed / 4 skipped 与 **58 passed / 0 skipped**，即全部写面用例在隔离栈真跑过。P1-1 与 P1-2 的 `evidence` 转 `real`，但**都不标 done**：两张卡标题里的 `/documents` 系列已被 D9 移到 G05，标题不动就标 done 等于用标题失真换绿灯；旧写路由（auth 三条 + 会话删除）的退出也还没做，且未被 D9 覆盖，需要同样的时点决定。
- 顺手修了一处记录自相矛盾：**D3 同时挂在 `decisions_pending` 与 `decisions_resolved`**。它 2026-10-15 已决议并写了 consequence，pending 那份是从没删的残留。危害不是难看——下一个 agent 读到 pending 会重新问一遍已经问过的问题，或把已定的事当成未决口子。删掉 pending 那条（与 `contracts/p1-design-review.md` 里"D3 已关闭"一致），并在 `scripts/sync_progress.py` 的 `validate()` 加机检：同一决策号不得双边登记。配套三条单测：能红、不冲突时绿、以及**真实 progress.json 必须自洽**这条收口判据。此前没有任何检查会发现它。
- 本批最终读数（都在改完状态之后重跑，不再拿局部绿冒充整体绿）：CI 等价条件（无 `.env`、无栈）全量 **738 passed / 100 skipped / 0 failed**；带栈 chain 46 passed / 18 skipped；`verify_storage.py --http` 隔离栈 25 passed / 4 skipped + **58 passed / 0 skipped**；八条门禁与 `sync_progress --check` 全过；远端 CI 在 `3916282` 上 **success**（run 39127244532）。
