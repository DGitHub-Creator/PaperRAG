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
