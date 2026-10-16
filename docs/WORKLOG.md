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
