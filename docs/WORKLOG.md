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
