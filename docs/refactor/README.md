# 重构 Spec 索引

面向 ResearchPilot（Go 主后端 + Python AI Core）的渐进式重构文档集。
基线：`main @ 6221147`，2026-10-09。**最高约束是 [08](08-principles-and-conventions.md)**，其余文件与它冲突时以它为准。

| 文件 | 内容 | 性质 |
| --- | --- | --- |
| [08-principles-and-conventions.md](08-principles-and-conventions.md) | **四条第一性原则、阶段顺序律、任务卡规范、开发规范、跨环境律、进度同步律** | 最高约束 |
| [plan-v2.0-researchpilot.md](plan-v2.0-researchpilot.md) | 重构计划 V2.0 原文（逐字存档，未修改） | 输入 |
| [00-audit.md](00-audit.md) | Phase 0 代码审计：调用链、断链、数据归属、基线测试结果 | 事实 |
| [01-current-architecture.md](01-current-architecture.md) | As-Is：拓扑、25 条对外契约、配置清单、中间件语义、数据归属 | 事实 |
| [02-target-architecture.md](02-target-architecture.md) | To-Be：五条架构律、目录、Go↔Python 契约、状态机、**模块所有权与写入边界** | 决策 |
| [03-gap-analysis.md](03-gap-analysis.md) | 差距清单与断链处置、未调用接口审计纪律、测试缺口 | 决策依据 |
| [04-migration.md](04-migration.md) | 路线 **P0→P1→P2→P3**（架构先行）、A0 卡片去向、切换策略、回滚、风险、日程 | 决策 |
| [05-database-migration.md](05-database-migration.md) | Schema 收编七步、`paper_chunks` DDL、TIMESTAMPTZ 验证与转换、存量文献重建 | 实施 |
| [09-milestone-p0.md](09-milestone-p0.md) | **P0 文件级任务卡 P0-0…P0-9、依赖顺序、X1–X8 退出标准、待拍板决策 K1–K3** | 实施（待确认） |
| [07-e2e-test-plan.md](07-e2e-test-plan.md) | 最小真实 E2E 方案：分层、断言纪律、T1–T8 用例、契约测试、CI 分工 | 实施 |
| [p0-environment.md](p0-environment.md) | P0-0 产物：从零到 `/health` 200 的可复制启动序列 + §3 实跑记录表 + 已知坑 | 实施 |
| [06-milestone-a0.md](06-milestone-a0.md) | 【历史】旧 Milestone A0 任务清单与 E1–E10；§4 给出卡片到新阶段的重映射 | 历史 |

进度与日程：[../progress.json](../progress.json)（唯一真相）→ [../PROGRESS.md](../PROGRESS.md) / [../progress.html](../progress.html)（生成物，双击可开）。

## 阅读顺序

- **评审决策**：`08 → 00 → 03 → 02 → 04`
- **要动手**：`08 → 09 → 07 → 05`（09 是 P0 的文件级计划；06 只作历史与细节来源）
- **看进度**：`../progress.html`（可视化）或 `../PROGRESS.md`（文本）

## 已锁定决策

1. ~~先修复既有故障与安全缺陷，建立 Milestone **A0**，之后才动 Go。~~
   **已被 `08` §2 的阶段顺序律取代**（2026-10-09）：P0 架构与契约先行，旧系统必要修复按"是否阻塞本阶段端到端演示"穿插进 P0/P1/P2。上传任务内存态仍由 Go Frontier（P3）取代。
2. Go 落 `server/`，Python 保留 `backend/`，不做大规模目录迁移。
3. Go 优先接管前端实际调用的 13 条接口 + SSE/WS；其余接口先完成调用方审计再弃用。
4. `golang-migrate` 统一管理后续 schema；先核查实际结构再建非破坏性基线；禁止对存量库重复初始化建表；TIMESTAMPTZ 统一须先验证历史 naive 语义；删除静默 `create_all` 兜底。
5. PG 为正文唯一真相，Milvus 只存可重建索引；旧文献从原始 PDF 重解析。
   ~~Chunk 可信化是 Milestone A 的前置阻塞~~ → **改在 P2，且在 Go 侧新 schema 上做**（`04` §0.2 D3）。代价：P1 的引用为非证据级，不得宣传为证据链。
6. 修通公式索引与检索并要求真实链路测试；多模态与布局分析 DEFER 但不删除、不宣传为已实现。
7. 保留统一 `/internal/v1/ai/execute` + `task_type` 分发，MVP 即实现异步 `execution_id`；大体积数据走 `object_id`/`result_ref`；Go 拥有 ResearchTask 与全局调度，Python 拥有局部 AIExecution。
8. 按 solo、每周 15–20 小时规划；真实 E2E/集成/契约/10–15 题固定回归必做；A/B/C 实验、20+ 题 benchmark、消融 DEFER 到最后阶段之后；≥95%/≥90% 保留为质量目标，不作当前门禁。

**目标不是让代码变成 Go**，而是让 PaperRAG 在功能正确、数据可信、可验证的基础上升级为 Go + Python 的自主科研平台。
