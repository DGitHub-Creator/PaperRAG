# 重构 Spec 索引

面向 ResearchPilot（Go 主后端 + Python AI Core）的渐进式重构文档集。基线：`main @ c55129e`，2026-10-09。

| 文件 | 内容 | 性质 |
| --- | --- | --- |
| [plan-v2.0-researchpilot.md](plan-v2.0-researchpilot.md) | 重构计划 V2.0 原文（逐字存档，未修改） | 输入 |
| [00-audit.md](00-audit.md) | Phase 0 代码审计：调用链、断链、数据归属、基线测试结果 | 事实 |
| [01-current-architecture.md](01-current-architecture.md) | As-Is：拓扑、25 条对外契约、配置清单、中间件语义、数据归属 | 事实 |
| [02-target-architecture.md](02-target-architecture.md) | To-Be：五条架构律、目录、Go↔Python 契约、状态机、**模块所有权与写入边界** | 决策 |
| [03-gap-analysis.md](03-gap-analysis.md) | 差距清单 G1–G? 与断链处置、未调用接口审计纪律、测试缺口 | 决策依据 |
| [04-migration.md](04-migration.md) | 路线 A0→A→B→C、切换策略、回滚设计、风险登记、排期压缩选项 | 决策 |
| [05-database-migration.md](05-database-migration.md) | Schema 收编七步、`paper_chunks` DDL、TIMESTAMPTZ 验证与转换、存量文献重建 | 实施 |
| [06-milestone-a0.md](06-milestone-a0.md) | **Milestone A0 文件级任务清单、依赖顺序、E1–E10 退出标准** | 实施 |
| [07-e2e-test-plan.md](07-e2e-test-plan.md) | 最小真实 E2E 方案：分层、断言纪律、T1–T8 用例、契约测试、CI 分工 | 实施 |

## 阅读顺序

评审决策：`00 → 03 → 02 → 04`。要动手：`06 → 07 → 05`。

## 已锁定决策（Q1–Q8，全部 A 方案）

1. 先修复既有故障与安全缺陷，建立 Milestone **A0**（基线修复与数据可信化），上传任务内存态不单独重构，由 Go Frontier 取代。
2. Go 落 `server/`，Python 保留 `backend/`，不做大规模目录迁移。
3. Go 优先接管前端实际调用的 13 条接口 + SSE/WS；其余接口先完成调用方审计再弃用。
4. `golang-migrate` 统一管理后续 schema；先核查实际结构再建非破坏性基线；禁止对存量库重复初始化建表；TIMESTAMPTZ 统一须先验证历史 naive 语义；删除静默 `create_all` 兜底。
5. Chunk 可信化是 Milestone A 的**前置阻塞**：PG 为正文唯一真相，Milvus 只存可重建索引；旧文献从原始 PDF 重解析。
6. 修通公式索引与检索并要求真实链路测试；多模态与布局分析 DEFER 但不删除、不宣传为已实现。
7. 保留统一 `/internal/v1/ai/execute` + `task_type` 分发，MVP 即实现异步 `execution_id`；大体积数据走 `object_id`/`result_ref`；Go 拥有 ResearchTask 与全局调度，Python 拥有局部 AIExecution。
8. 按 solo、每周 15–20 小时规划；真实 E2E/集成/契约/10–15 题固定回归必做；A/B/C 实验、20+ 题 benchmark、消融 DEFER 到 C 之后；≥95%/≥90% 保留为质量目标，不作当前门禁。

**目标不是让代码变成 Go**，而是让 PaperRAG 在功能正确、数据可信、可验证的基础上升级为 Go + Python 的自主科研平台。
