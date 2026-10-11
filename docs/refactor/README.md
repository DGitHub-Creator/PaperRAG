# 重构 Spec 索引

面向 **ResearchPilot**（Go 主后端 + Python AI Core）的渐进式重构文档集。
基线：`main @ 6221147`，2026-10-09。**最高约束是 [08](08-principles-and-conventions.md)**，其余文件与它冲突时以它为准。

> 被取代的旧计划已移到 [`../archive/`](../archive/README.md)（含 `plan-v2.0-researchpilot.md` 与 `06-milestone-a0.md`）。
> **归档件不作为实施依据**；引用它们时必须同时指出接管它的现行文件。

## 现行文件

| 文件 | 内容 | 性质 |
| --- | --- | --- |
| [08-principles-and-conventions.md](08-principles-and-conventions.md) | **四条第一性原则、阶段顺序律、任务卡规范、开发规范、跨环境律、进度同步律** | 最高约束 |
| [09-milestone-p0.md](09-milestone-p0.md) | **P0 文件级任务卡 P0-0…P0-9 + FE-1、依赖顺序、X1–X8 退出标准、决策 K1–K4** | 实施（当前阶段） |
| [10-frontend-structure.md](10-frontend-structure.md) | 前端结构专项：F1–F11 缺陷、R1–R11 规定、`check_frontend.py` 机检口径 | 实施（FE-1 已 done） |
| [00-audit.md](00-audit.md) | Phase 0 代码审计：调用链、断链、数据归属、基线测试结果 | 事实 |
| [01-current-architecture.md](01-current-architecture.md) | As-Is：拓扑、25 条对外契约、配置清单、中间件语义、数据归属 | 事实 |
| [02-target-architecture.md](02-target-architecture.md) | To-Be：五条架构律、目录、Go↔Python 契约、状态机、**模块所有权与写入边界** | 决策 |
| [03-gap-analysis.md](03-gap-analysis.md) | 差距清单与断链处置、未调用接口审计纪律、测试缺口 | 决策依据 |
| [04-migration.md](04-migration.md) | 路线 **P0→P1→P2→P3**（架构先行）、旧 A0 卡片去向、切换策略、回滚、风险、日程 | 决策 |
| [05-database-migration.md](05-database-migration.md) | Schema 收编七步、`paper_chunks` DDL、TIMESTAMPTZ 验证与转换、存量文献重建 | 实施 |
| [07-e2e-test-plan.md](07-e2e-test-plan.md) | 最小真实 E2E 方案：分层、断言纪律、T1–T8 用例、契约测试、CI 分工 | 实施（由 P0-9 落地） |
| [p0-environment.md](p0-environment.md) | P0-0 产物：从零到 `/health` 200 的可复制启动序列 + §3 实跑记录表 + 已知坑 | 实施 |
| [11-product-vision.md](11-product-vision.md) | **产品愿景（产品价值轴）**：五个产品入口、十项核心能力、三个惊艳功能、V1–V4 路线、差异化与目标用户、ARTEX 架构借鉴、**尚未登记的缺口清单** | 愿景 |
| [12-known-code-issues.md](12-known-code-issues.md) | **代码问题台账**：按愿景检查仓库时发现的代码层问题（证据 / 影响 / 建议改法 / 归属卡片），本轮只记录未动手 | 问题清单 |

> **两条轴别混用编号**：工程阶段是上表的 **P0–P3**（`04` 定义）；产品价值是 **V1–V4**（`11` 定义）。
> 两者的映射关系与三处顺序冲突见 [11](11-product-vision.md) §7。

进度与日程：[../progress.json](../progress.json)（唯一真相）→ [../PROGRESS.md](../PROGRESS.md) / [../progress.html](../progress.html)（生成物，双击可开）。

契约目录：[../../contracts/](../../contracts/)（`openapi.yaml` 对浏览器 · `ai-execution.schema.json` Go↔Python · `error-codes.md` · `table-acl.md`），
由 `uv run python scripts/check_contracts.py` 机检并进 CI；改契约不改文档，改这里。

## 阅读顺序

- **评审决策**：`08 → 00 → 03 → 02 → 04`
- **要动手**：`08 → 09 → 07 → 05`（09 是 P0 的文件级计划；前端专项看 10）
- **看进度**：`../progress.html`（可视化）或 `../PROGRESS.md`（文本）

## 文档口径纪律（原则②③的落地方式）

- 每篇文档开头写清**性质**（事实 / 决策 / 实施 / 历史）与**取代关系**；被取代的进 `../archive/`。
- 未实现的能力一律显式标注「未实现」并指向 `progress.json` 的卡片号，不写成既成事实。
- 里程碑命名只用 **P0–P3**；`Milestone A0/A/B/C` 属旧口径，只在归档件里出现。

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
9. **K1–K4（2026-10-09 定案，落点见 `09` §3）**：429 统一到 `{"detail": ...}`；sqlc 生成物入库并用 `git diff` 门禁；nginx upstream 切换放在 P0-8 末、P0-9 前且先过 X5；422 降级为 400 + 字符串 `detail`。

**目标不是让代码变成 Go**，而是让 ResearchPilot 在功能正确、数据可信、可验证的基础上，成为 Go + Python 的自主科研平台。
