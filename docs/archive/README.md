# 归档区：本目录所有文件都不作为实施依据

这里放的是**被取代的旧计划与旧规划**。留着的唯一目的是追溯"当时为什么这么定"，
以及给现行文档提供出处（`00-audit` / `02-target` 的输入来自 `refactor-plan-v2.0-researchpilot.md`）。

**现行权威入口只有三处**，与它们冲突时一律以它们为准：

| 权威文件 | 管什么 |
| --- | --- |
| [`../refactor/08-principles-and-conventions.md`](../refactor/08-principles-and-conventions.md) | 最高约束：四条第一性原则、阶段顺序律、任务卡规范、开发规范、进度同步律 |
| [`../refactor/09-milestone-p0.md`](../refactor/09-milestone-p0.md)（+ [`10-frontend-structure.md`](../refactor/10-frontend-structure.md)） | 当前阶段的任务卡：输入/输出/依赖/验收/证据等级，以及 X1–X8 退出标准 |
| [`../progress.json`](../progress.json) | 进度真相源（`PROGRESS.md` / `progress.html` 是它的生成物）；契约在 [`../../contracts/`](../../contracts/) |

## 归档清单

| 文件 | 原位置 | 归档日期 | 被什么取代 |
| --- | --- | --- | --- |
| `refactor-plan-v2.0-researchpilot.md` | `docs/refactor/` | 2026-10-09 | 决策 Q1 被《重构执行总纲》推翻（原则①端到端优先）→ `08` §2 + `04` 的 P0→P3 阶段模型 |
| `refactor-06-milestone-a0.md` | `docs/refactor/` | 2026-10-09 | Milestone A0 取消，卡片重映射进 P0/P1/P2 → `04` §0 + `09` |
| `improvement_plan.md` | `docs/` | 2026-10-09 | 分阶段路线图 → `04` + `09`；已完成项见 `completed-items.md` |
| `architecture-review-and-improvement-plan.md` | `docs/` | 2026-10-09 | 架构判断 → `01-current-architecture.md`（As-Is）+ `02-target-architecture.md`（To-Be） |
| `code-review-action-items.md` | `docs/` | 2026-10-09 | 7 项缺点的处置 → `03-gap-analysis.md` + `04` §0 |
| `plan-5-academic.md` | `docs/` | 2026-10-09 | 四个学术功能重映射进 P2 → `04` §0.2、决策 D3；断链实测见 `00-audit` §3 |
| `plan-1-architecture.md`…`plan-4-testing.md` | `docs/` | 早于 2026-10-09 | 旧四份分领域计划，标题里的「✅ 已完成」是当时的自评，未经端到端验证 |
| `completed-items.md` | `docs/` | 早于 2026-10-09 | 从上面几份计划里摘出的"已完成"清单，同上口径 |

## 引用归档件的纪律

1. **不得据归档件排期、验收或宣称完成**（原则②：完成 = 端到端可验证行为）。
2. 引用时必须同时给出取代它的现行文件，例如"见 `archive/plan-5-academic.md`（已归档，现由 `04` §0.2 与 D3 接管）"。
3. 归档件的正文**逐字保留**，只在文件头加归档抬头——改正文会让"当时的判断"失真，也就失去归档的意义。
4. 归档不等于删除：`plan-5-academic.md` 里的公式索引、多模态等功能仍在路线上（P2），
   只是不再按旧文档的口径推进；`06` 的 E1–E10 仍是文件级细节的来源。
