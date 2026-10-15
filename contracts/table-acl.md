# 表级写入权限矩阵（可机检形式）

> 出处：`02-target-architecture.md` §6.2。本文件是那张表的**机器可读版本**，
> 由 `scripts/check_contracts.py` 校验；`02` §6.2 保留叙述，两者冲突时以本文件为准并回改 `02`。
> 落实方式：PG 侧按角色 GRANT（Go 对 Python 只授 `SELECT`，除 `ai_executions` 外不给 DML）。

标记：`W` = 独占写，`R` = 只读，`X` = 禁止访问。`transition` 非 `-` 表示允许双写的过渡期。

| table | go | python | transition | note |
| --- | --- | --- | --- | --- |
| `users` | W | R | - | Python 只校验服务身份，不改业务主体 |
| `user_preferences` | W | X | - | 设置页的用户自助面（theme / start_view），只读自己的行；与 `users` 同属 Go 的账号域 |
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

## 本表**没有**回答的两件事（2026-10-15 现场核对，读数别抄）

本矩阵是**归属意图**，不是库里的现状。两者的差集现在被显式登记在这里，
过去它只存在于台账 C30 的一句话里，于是「ACL 写着 `go: W`」被反复读成「Go 在写这张表」：

| 类别 | 表 | 事实 |
| --- | --- | --- |
| 本表声明了归属、但**库里根本没有** | `papers` `paper_versions` `paper_files` `paper_chunks` `research_projects` `research_runs` `research_plans` `research_tasks` `research_task_dependencies` `research_events` `outbox_events` `research_budget_usage` `model_usage_records` `knowledge_items` `exploration_gaps` `evidence_links` `research_claims` `report_sections`（18 张） | 它们的 `go: W` 是 P2/P3 建表时的**预定归属**（台账 **C30**）。落表时点：`papers`/`paper_versions`/`paper_files`/`paper_chunks` 属 P2-1，`research_*`/`outbox_events` 属 P3-1，`knowledge_*`/`exploration_*`/`evidence_links`/`research_claims`/`report_sections` 属 P3 之后 |
| 库里存在、但**本表故意不登记** | `parent_chunks` `paper_nodes` `citation_edges` `glossary_entries` `alembic_version`（5 张） | 归属是**决策 D6**，还没拍。写进矩阵等于替 D6 做决定，所以留空并在这里点名。前四张里 `paper_nodes`/`citation_edges`/`glossary_entries` 实测是**死表**（`13 §6`），`alembic_version` 属 alembic 那条线，不是 Go 的表 |

**取数命令**（两边各一次，别信任何文档里的表数）：

```bash
# 库里真有的表
docker exec researchpilot-postgres psql -U postgres -d langchain_app \
  -tAc "SELECT table_name FROM information_schema.tables
        WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY 1;"
# 本表声明的表
grep -c '^| `' contracts/table-acl.md
# Go 今天真的读写哪几张 = sqlc 的查询文件覆盖的表
ls server/sql/queries/
```

**写入边界的执行**目前只有第 1–4 条校验规则（值域、单 `W`、`ai_executions` 与 `research_*` 的律、
Python 可写 ≤ 2）。"谁真的在写这张表"今天**无机检**——那需要 PG 侧的角色与 `GRANT`，
属 P1-3/P2-1 建表时一并做（迁移里 `GRANT` 在角色定义之前不写，见 `05 §2.6`）。
