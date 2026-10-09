# 表级写入权限矩阵（可机检形式）

> 出处：`02-target-architecture.md` §6.2。本文件是那张表的**机器可读版本**，
> 由 `scripts/check_contracts.py` 校验；`02` §6.2 保留叙述，两者冲突时以本文件为准并回改 `02`。
> 落实方式：PG 侧按角色 GRANT（Go 对 Python 只授 `SELECT`，除 `ai_executions` 外不给 DML）。

标记：`W` = 独占写，`R` = 只读，`X` = 禁止访问。`transition` 非 `-` 表示允许双写的过渡期。

| table | go | python | transition | note |
| --- | --- | --- | --- | --- |
| `users` | W | R | - | Python 只校验服务身份，不改业务主体 |
| `workspaces` | W | R | - | 同上 |
| `workspace_members` | W | R | - | 同上 |
| `chat_sessions` | W | X | - | 迁移后 Python 不再持久化对话 |
| `chat_messages` | W | X | - | 需把覆盖式写改 append-only（00-audit §4） |
| `papers` | W | X | - | Go 是文献实体权威 |
| `paper_versions` | W | X | - | 同上 |
| `paper_files` | W | X | - | 同上 |
| `paper_chunks` | W | W | until-P2 | 过渡期由 Python 写以重建可信 chunk 层；Go 接管后改 Python 只读 |
| `research_projects` | W | X | - | L1 全局调度 |
| `research_runs` | W | X | - | 同上 |
| `research_plans` | W | X | - | 同上 |
| `research_tasks` | W | X | - | 写必须带 `WHERE lease_token = $t`（02 §3.4 fencing） |
| `research_task_dependencies` | W | X | - | 同上 |
| `research_events` | W | X | - | 事件日志/SSE 游标归 Go，Redis 不得作为唯一事件源 |
| `outbox_events` | W | X | - | 同上 |
| `research_budget_usage` | W | X | - | Python 上报 usage，Go 记账 |
| `model_usage_records` | W | X | - | 同上 |
| `knowledge_items` | W | X | - | Python 只交候选（02 §3.2 约定） |
| `exploration_gaps` | W | X | - | 同上 |
| `evidence_links` | W | X | - | 同上 |
| `research_claims` | W | X | - | 同上 |
| `report_sections` | W | X | - | 同上 |
| `ai_executions` | R | W | - | Python 独占；Go 只读状态推进自己的 ResearchTask |

## 校验规则（`check_contracts.py` 实际执行的内容）

1. 每行的 `go`/`python` 取值必须在 `{W, R, X}` 内；表名必须是 `snake_case`。
2. 一行里最多一个 `W`；出现双 `W` 必须 `transition != "-"`，否则判为写入归属冲突。
3. `ai_executions` 必须是 `go=R, python=W`；`research_*` 与 `*_events` 的 `python` 必须是 `X`
   ——这两条是「Go 是唯一全局调度中心」这条架构律在数据层的落点，写错就等于破律。
4. Python 侧标 `W` 的表数量 ≤ 2（`ai_executions` + 过渡期的 `paper_chunks`）：
   防止 P1/P2 期间不知不觉给 Python 开出第三张可写表。
