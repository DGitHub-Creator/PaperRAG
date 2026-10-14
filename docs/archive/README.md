# 归档区：本目录所有文件都不作为实施依据

这里放的是**被取代的旧计划与旧规划**。留着的唯一目的是追溯"当时为什么这么定"，
以及给现行文档提供出处（`00-audit` / `02-target` 的输入来自 `refactor-plan-v2.0-researchpilot.md`）。

**现行权威入口**（结构规则见 [`../README.md`](../README.md)）；归档件与它们冲突时，一律以现行件为准：

| 权威文件 | 管什么 |
| --- | --- |
| [`../rules/08-principles-and-conventions.md`](../rules/08-principles-and-conventions.md) | 最高约束：四条第一性原则、阶段顺序律、任务卡规范、开发规范、进度同步律 |
| [`../plans/09-milestone-p0.md`](../plans/09-milestone-p0.md)（+ [`../rules/10-frontend-structure.md`](../rules/10-frontend-structure.md)） | 当前阶段的任务卡：输入/输出/依赖/验收/证据等级，以及 X1–X8 退出标准 |
| [`../progress.json`](../progress.json) | 进度真相源（`PROGRESS.md` / `progress.html` 是它的生成物）；契约在 [`../../contracts/`](../../contracts/) |

## 归档清单

> 「原位置」列记的是**归档当时**的路径（早于 2026-10-14 目录重构的行指向已不存在的 `docs/refactor/`）——这是历史事实，不追改；
> 旧路径与新位置的对照表见文末。

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

## 2026-10-14 目录重构：旧路径 → 新位置

`docs/refactor/` 已拆进分层目录（`rules/` / `plans/` / `reference/`）；归档件抬头里残留的 `../refactor/…` 链接按
"逐字保留"纪律**不追改**。对照表：

| 旧路径（2026-10-14 前） | 新位置 |
| --- | --- |
| `docs/refactor/00-audit.md`、`01-current-architecture.md` | `docs/reference/`（dated 事实，只读） |
| `docs/refactor/` 的 `02` `08` `10` `11` `12` `13` `14` | `docs/rules/`（常青规则，最高优先级） |
| `docs/refactor/` 的 `03` `04` `05` `07` `09`、`p0-environment.md` | `docs/plans/`（会变的计划，低优先级） |
| `docs/refactor/schema-baseline.json`、`timestamp-audit.md` | `docs/reference/`（生成物，不手改） |
| `docs/refactor/README.md` | `docs/README.md`（文档宪法） |

**新文档不再取号**（不再有 `15-`、`16-`…）：分层与命名规则见 [`../README.md`](../README.md) §0/§9。
