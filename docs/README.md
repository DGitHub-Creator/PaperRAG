# docs 目录宪法（读文档先读这一份）

> 这是整个 `docs/` 的**结构规则**：目录分层、优先级、命名、归档、新文档往哪放、怎么查。
> **内容的**最高约束不是本文，而是 [`rules/08-principles-and-conventions.md`](rules/08-principles-and-conventions.md)——
> 内容冲突时以它为准；**目录怎么放**以本文为准。

面向 **ResearchPilot**（Go 主后端 + Python AI Core）。基线：`main @ 106f17dd`，2026-10-09；
目录分层（rules / plans / reference / archive）于 **2026-10-14** 重构。

---

## 0. 一条铁律：不要再往后编号

**新文档一律不取新号**——不要 `15-`、`16-`、`17-` 这样往后写。

- 既有的两位数前缀（`08` / `09` / `13` …）是**永久 ID，不是顺序**：`08 §2`、`13 §6.1` 这类简写引用，
  以及代码注释里的 `docs/rules/10`，全都指它。**不要重命名、不要重排、不要复用**。
- 新文档用**语义文件名**放进对应层：`docs/rules/<slug>.md`、`docs/plans/<slug>.md`，
  例如 `docs/rules/retrieval-quality.md`。层内**不排号**。
- 只有"必须被简写引用"且已成体系时，才由用户拍板是否给一个号；**默认不给**。

> 为什么：按号往后写会让"规则"和"随时会变的计划"混在一串数字里，谁都不知道该先读谁、哪份还作数。
> 分层的目的是让**不确定该听谁**这件事消失。

## 1. 四层结构（优先级从高到低）

| 层 | 目录 | 放什么 | 变动频率 | 权威性 |
| --- | --- | --- | --- | --- |
| **规则** | [`docs/rules/`](rules/) | 架构（To-Be / As-Is）、功能模块、产品愿景、问题台账、四条原则、前端结构规定 | 低（**改它 = 改契约**） | **最高**，冲突以它为准 |
| **计划** | [`docs/plans/`](plans/) | 迁移路线、P0 任务卡、差距分析、E2E 方案、环境复现 | 高 | 低，实施细节以它为准 |
| **事实** | [`docs/reference/`](reference/) | 审计基线（`00`/`01`）、`schema-baseline.json`、`timestamp-audit.md` | 冻结 / 只读 | 历史证据，**不是现状** |
| **归档** | [`docs/archive/`](archive/README.md) | 被取代的旧计划 | 只增不改 | **不作为实施依据** |

**进度真相不进任何层**：`docs/progress.json`（唯一真相）与其生成物 `PROGRESS.md` / `progress.html`
固定放在 `docs/` 根目录；契约不放 `docs/` 而在 [`contracts/`](../contracts/)。

## 2. 规则层 `rules/` —— 常青，必须一直遵守

| 文件 | 管什么 |
| --- | --- |
| [`08-principles-and-conventions.md`](rules/08-principles-and-conventions.md) | **最高约束**：四条第一性原则、阶段顺序律、任务卡规范、开发规范、跨环境律、进度同步律 |
| [`02-target-architecture.md`](rules/02-target-architecture.md) | **To-Be 架构**：五条架构律 L1–L5、目录、Go↔Python 契约、状态机、模块所有权与写入边界（大部分**未实现**） |
| [`13-frontend-backend-architecture.md`](rules/13-frontend-backend-architecture.md) | **As-Is 实测架构**：运行形态、逐条端点（带 `file:line`）、数据面差集、前端结构、死代码清单（**可复核**） |
| [`14-feature-modules.md`](rules/14-feature-modules.md) | **功能模块规划**：M1…M17 逐模块的现状 / 目标行为 / 判据 / 卡片 / 顺序 / 风险 |
| [`11-product-vision.md`](rules/11-product-vision.md) | **产品愿景（产品价值轴）**：五个入口、十项能力、V1–V4 路线、缺口清单 |
| [`12-known-code-issues.md`](rules/12-known-code-issues.md) | **代码问题台账**：证据 / 影响 / 建议 / 归属卡片；2026-10-12 起按 P0 顺序逐条处置 |
| [`10-frontend-structure.md`](rules/10-frontend-structure.md) | **前端结构规定**：F1–F11 缺陷、R1–R11 规定、`check_frontend.py` 机检口径 |

> 规则层"改它等于改契约"：动 `rules/` 里的架构或模块规划，必须**先回文档层对齐、再写代码**（`08` 原则③）。

## 3. 计划层 `plans/` —— 会变，优先级低

| 文件 | 管什么 |
| --- | --- |
| [`04-migration.md`](plans/04-migration.md) | 路线 **P0→P1→P2→P3**（架构先行）、旧卡片去向、切换策略、回滚、风险、日程 |
| [`09-milestone-p0.md`](plans/09-milestone-p0.md) | **当前阶段**：P0 文件级任务卡 + X1–X8 退出标准 + 决策 K1–K4 |
| [`05-database-migration.md`](plans/05-database-migration.md) | Schema 收编七步、`paper_chunks` DDL、TIMESTAMPTZ 验证、存量重建 |
| [`03-gap-analysis.md`](plans/03-gap-analysis.md) | 差距清单与断链处置、未调用接口审计纪律、测试缺口 |
| [`07-e2e-test-plan.md`](plans/07-e2e-test-plan.md) | 最小真实 E2E 方案：分层、断言纪律、T1–T8 用例、契约测试、CI 分工 |
| [`p0-environment.md`](plans/p0-environment.md) | P0-0 产物：从零到 `/health` 200 的可复制启动序列 + 实跑记录 + 已知坑 |

> 计划层变动大。**改计划不用改契约层**，但每份计划开头要写清**性质**与**它被谁取代 / 取代了谁**。
> 一份计划做完或作废，就把**旧版**移进 [`archive/`](archive/README.md)，只留现行版在 `plans/`。

## 4. 事实层 `reference/` —— 只读

| 文件 | 性质 |
| --- | --- |
| [`00-audit.md`](reference/00-audit.md) | 2026-10-09 Phase 0 审计基线（dated 事实，**逐字保留、不追改**） |
| [`01-current-architecture.md`](reference/01-current-architecture.md) | 2026-10-09 As-Is 快照（dated 事实） |
| [`schema-baseline.json`](reference/schema-baseline.json) | 真库结构快照，由 `scripts/audit_schema.py --live` 只读导出（**生成物，不手改**） |
| [`timestamp-audit.md`](reference/timestamp-audit.md) | 时间列语义判定，由 `scripts/probe_timestamps.py` 产出（**生成物，不手改**） |

> **`01` 与 `13` 的分工**：`01` 是 dated 审计基线（冻结）；`13` 是**今天可复核的形状**（代码变了就更新它）。
> 两者冲突以 `13` 为准。**`02` 与 `13` 的分工**：`02` 写应该怎样（To-Be），`13` 写现在怎样（As-Is），差异是待办不是错误。

## 5. 归档层 `archive/` —— 不作为实施依据

- 归档 = **被取代**（不是"旧的"）。放进来的东西**正文逐字保留**，只在文件头加归档抬头。
- 引用归档件时**必须同时给出取代它的现行文件**，例如"见 `archive/plan-5-academic.md`（已归档，现由 `plans/04` §0.2 与 D3 接管）"。
- 不得据归档件排期、验收或宣称完成（原则②）。归档清单在 [`archive/README.md`](archive/README.md)。
- ⚠️ 2026-10-14 目录重构前的 `docs/refactor/*` 路径 → 新位置的映射表见 `archive/README.md` 末尾；
  归档件抬头里残留的 `../refactor/…` 链接按"逐字保留"纪律**不追改**。

## 6. 内容权威层级（冲突时按此优先级）

详见 [`AGENTS.md` §2](../AGENTS.md)：`rules/08` 最高 → `progress.json` → 当前阶段任务卡 → 产品轴 / 台账 → 架构实测 → `contracts/` → `reference/`（dated） → `archive/`。
**一句话**：内容听 `08`，结构听本文，进度听 `progress.json`。

## 7. 阅读顺序

- **评审决策**：`08 → 00 → 03 → 02 → 04`
- **要动手**：`08 → 09 → 07 → 05`（09 是 P0 的文件级计划；前端专项看 `10`）
- **想知道"现在真是什么样"**：`13`（带 `file:line` 与取数命令）→ 与 `02` 的 To-Be 对照看差距
- **想按功能排期**：`14`（M1…M17 的现状与判据）→ `11 §7` 两轴映射 → `04` 路线
- **看进度**：`../progress.html`（可视化）或 `../PROGRESS.md`（文本）

## 8. 写作纪律（原则②③的落地方式）

- 每篇文档开头写清**性质**（事实 / 决策 / 实施 / 愿景 / 历史）与**取代关系**；被取代的进 `archive/`。
- 未实现的能力一律显式标注「未实现」并指向 `progress.json` 的卡片号，不写成既成事实。
- 里程碑命名只用 **P0–P3**；`Milestone A0/A/B/C` 属旧口径，只在归档件里出现。
- **两条轴别混用编号**：工程阶段 **P0–P3**（`plans/04` 定义）、产品价值 **V1.0–V4.0**（`rules/11` 定义），映射见 `11 §7`。

## 9. 新增 / 移动文档怎么办

1. **先判断层**：常青规则 → `rules/`；会变的计划 → `plans/`；只读事实/快照 → `reference/`；被取代 → `archive/`。
2. **命名**：语义 slug（`retrieval-quality.md`），**不取号**。
3. **改引用**：用 `git grep` 找出全仓引用（含代码注释、`scripts/*.py`、`contracts/`），一并更新；
   跨层相对链接要重算（`rules/x.md` ↔ `plans/y.md` 需 `../plans/`、`../rules/`）。
4. **同批**：改目录结构要在**同一提交**里更新 `AGENTS.md §2`、根 `README.md` 的目录树、本文件，并跑门禁。
5. **契约**：改 Go↔Python 契约不改这里，改 [`contracts/`](../contracts/)（`check_contracts.py` 机检）。

---

## 已锁定决策（摘要，权威在 `plans/04` 与 `plans/09`）

1. ~~先修复既有故障与安全缺陷，建立 Milestone **A0**，之后才动 Go。~~
   **已被 `rules/08` §2 的阶段顺序律取代**（2026-10-09）：P0 架构与契约先行，旧系统必要修复按"是否阻塞本阶段端到端演示"穿插进 P0/P1/P2。上传任务内存态仍由 Go Frontier（P3）取代。
2. Go 落 `server/`，Python 保留 `backend/`，不做大规模目录迁移。
3. Go 优先接管前端实际调用的 13 条接口 + SSE/WS；其余接口先完成调用方审计再弃用。
4. `golang-migrate` 统一管理后续 schema；先核查实际结构再建非破坏性基线；禁止对存量库重复初始化建表；TIMESTAMPTZ 统一须先验证历史 naive 语义；删除静默 `create_all` 兜底。
5. PG 为正文唯一真相，Milvus 只存可重建索引；旧文献从原始 PDF 重解析。
   ~~Chunk 可信化是 Milestone A 的前置阻塞~~ → **改在 P2，且在 Go 侧新 schema 上做**（`04` §0.2 D3）。代价：P1 的引用为非证据级，不得宣传为证据链。
6. 修通公式索引与检索并要求真实链路测试；多模态与布局分析 DEFER 但不删除、不宣传为已实现。
7. 保留统一 `/internal/v1/ai/execute` + `task_type` 分发，MVP 即实现异步 `execution_id`；大体积数据走 `object_id`/`result_ref`；Go 拥有 ResearchTask 与全局调度，Python 拥有局部 AIExecution。
8. 按 solo、每周 15–20 小时规划；真实 E2E/集成/契约/10–15 题固定回归必做；A/B/C 实验、20+ 题 benchmark、消融 DEFER 到最后阶段之后；≥95%/≥90% 保留为质量目标，不作当前门禁。
9. **K1–K4（2026-10-09 定案，落点见 `plans/09` §3）**：429 统一到 `{"detail": ...}`；sqlc 生成物入库并用 `git diff` 门禁；nginx upstream 切换放在 P0-8 末、P0-9 前且先过 X5；422 降级为 400 + 字符串 `detail`。
10. **容器只跑中间件（2026-10-13 定案）**：Go / Python / 前端一律**源码运行**，应用层不容器化（见 `AGENTS.md` §6、台账 `C29`）。

**目标不是让代码变成 Go**，而是让 ResearchPilot 在功能正确、数据可信、可验证的基础上，成为 Go + Python 的自主科研平台。
