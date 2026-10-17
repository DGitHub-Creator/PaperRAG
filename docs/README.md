# 文档导航与维护规范

先看本文选择资料，再按任务阅读。文档中的“目标”“计划”“历史通过”都不能代替当前实现证据。

## 权威入口

| 要解决的问题 | 阅读入口 | 使用边界 |
| --- | --- | --- |
| 接手仓库、修改代码 | [AGENTS.md](../AGENTS.md) | 稳定开发规则与操作禁区 |
| 原则、阶段顺序、证据等级 | [08 原则](rules/08-principles-and-conventions.md) | 最高项目约束，用户指令优先 |
| 全局模块、排期与 agent 任务交接 | [全局开发计划](plans/14-feature-modules.md) | 后续 agent 开工必读；范围确认不等于能力已实现 |
| 已完成多少、当前阶段 | [progress.json](progress.json) | 唯一进度源；[PROGRESS](PROGRESS.md) 与 [页面](progress.html) 是生成物 |
| 代码现在怎么运行 | [13 架构现状](reference/13-frontend-backend-architecture.md) | 可维护现状，对照列出的实现和测试复核 |
| 还有什么故障 | [12 问题台账](plans/12-known-code-issues.md)、[规范化清单](plans/repository-standardization.md) | 分清已修、待验证和未解决 |
| 安装与启动 | [根 README](../README.md) | 参数以 dev.py --help 为准，不照抄历史命令 |
| 跨服务接口与归属 | [contracts](../contracts/) | 改接口同时改契约、调用方与门禁 |
| 当时为何这样做 | [WORKLOG](WORKLOG.md)、[archive](archive/README.md) | 历史证据，不作为当前操作指令 |

规则决定应怎样，代码和现场验证说明已怎样；发生冲突要修文档或登记缺口，不能按文档推定功能存在。

## 分类与文件清单

| 目录 | 内容 | 维护方式 |
| --- | --- | --- |
| rules/ | 稳定原则、目标架构、职责边界与产品愿景 | 设计变化时更新；不混入测试计数和本机状态 |
| plans/ | 阶段任务、实施方案、功能规划与动态问题台账 | 变更时同步相关任务；计划不代表已完成 |
| reference/ | 当前实现说明和有日期的结构/审计快照 | 当前说明持续维护；冻结快照保留来源与日期 |
| archive/ | 已被取代的资料 | 原文保留，仅加历史标识和取代入口 |

`rules/`：

- [02 目标架构](rules/02-target-architecture.md)：目标服务边界与数据所有权，大部分尚待实现。
- [08 原则](rules/08-principles-and-conventions.md)：阶段、任务卡、证据与工程治理。
- [10 前端结构](rules/10-frontend-structure.md)：前端分层与检查规则。
- [11 产品愿景](rules/11-product-vision.md)：产品价值轴，不能用页面存在推定能力实现。
- [前后端分工](rules/frontend-backend-division-of-labor.md)：稳定职责约定，不存进度副本。

`plans/`：

- [03 差距分析](plans/03-gap-analysis.md)、[04 迁移路线](plans/04-migration.md)：规划依据；其中早期现状描述需对照 13。
- [05 数据库迁移](plans/05-database-migration.md)、[07 E2E 方案](plans/07-e2e-test-plan.md)：实施与验收方案。
- [09 P0 任务卡](plans/09-milestone-p0.md)：卡片定义与退出标准；状态从 progress.json 读取。
- [12 问题台账](plans/12-known-code-issues.md)、[14 全局开发计划](plans/14-feature-modules.md)：质量缺口，以及已确认的模块、依赖、任务包与交接计划。
- [环境复现](plans/p0-environment.md)、[P0 演示](plans/p0-demo.md)：运行参考，历史实跑只证明当时结果。
- [规范化 TODO](plans/repository-standardization.md)：本轮全仓质量整改范围与未决项。

`reference/`：

- [13 架构现状](reference/13-frontend-backend-architecture.md)：现行说明，修改相关代码后同步。
- [00 审计](reference/00-audit.md)、[01 架构](reference/01-current-architecture.md)：冻结的早期基线，不追改。
- [schema-baseline.json](reference/schema-baseline.json)：历史真库快照，仅作对应版本的基线比较。
- [schema-audit-2026-10-17.json](reference/schema-audit-2026-10-17.json)：当前整改批次真库结构与权限快照；only_in_db 表示未由 ORM 声明，不等同于业务列漂移。
- [schema-audit-2026-10-16.json](reference/schema-audit-2026-10-16.json)：此前版本快照，保留当时事实，不作为当前结构。
- [timestamp-audit.md](reference/timestamp-audit.md)：当时的时间语义调查，不直接授权转换历史数据。

## 写作与重构规则

1. 开头注明性质、适用范围；事实写核验日期及代码符号或可运行命令。不要维护易失效的行号和数量副本。
2. 规则、现状、计划、证据分开；“未实现”“未验证”“历史通过”“本轮通过”明确区分。
3. 进度只写 progress.json；运行证据记 WORKLOG。生成物由脚本重建，不手改数字。
4. 新文件使用语义 slug，不继续排号；已有编号保留作稳定引用。分类错放可以移动，同批修复引用。
5. 移动文件时更新全仓现行链接、脚本常量和根 README；不篡改档案里的历史路径。
6. 旧计划被取代时归档并给现行入口；历史故障只说明曾发生，不推定当前仍发生或必然发生。
7. 不记录机器用户名、绝对路径、代理端口、真实凭据；环境特例必须标注适用条件。
8. 一处定义、多处链接。需要重复的摘要注明来源，不复制整张进度表、问题台账或决策记录。

## 验证

```bash
uv run python scripts/check_repository.py
uv run python scripts/sync_progress.py --check
uv run python scripts/check_contracts.py
uv run python scripts/check_design_review.py
```

链接检查通过只说明引用存在；语义、历史边界与实现一致性仍须人工核对。
