# 表级写入权限矩阵（可机检形式）

> 出处：`02-target-architecture.md` §6.2。本文件是那张表的**机器可读版本**，
> 由 `scripts/check_contracts.py` 校验；`02` §6.2 保留叙述，两者冲突时以本文件为准并回改 `02`。
> 本矩阵定义目标权限，不代表当前数据库已实施 GRANT。`present` 只说明迁移建了表，不说明目标写入边界已接管。

存在性：note 的 `[present]` / `[planned]` 由迁移文件校验，新增建表必须同批更新。

标记：`W` = 独占写，`R` = 只读，`X` = 禁止访问。`transition` 非 `-` 表示允许双写的过渡期。

| table | go | python | transition | note |
| --- | --- | --- | --- | --- |
| `users` | W | R | - | [present] Python 只校验服务身份，不改业务主体 |
| `user_preferences` | W | X | - | [present] 设置页的用户自助面（theme / start_view），只读自己的行；与 `users` 同属 Go 的账号域 |
| `workspaces` | W | R | - | [present] 同上 |
| `workspace_members` | W | R | - | [present] 同上 |
| `chat_sessions` | W | X | - | [present] 迁移后 Python 不再持久化对话 |
| `chat_messages` | W | X | - | [present] 需把覆盖式写改 append-only（00-audit §4） |
| `papers` | W | X | - | [planned] Go 是文献实体权威 |
| `paper_versions` | W | X | - | [planned] 同上 |
| `paper_files` | W | X | - | [planned] 同上 |
| `paper_chunks` | W | W | until-P2 | [planned] 过渡期由 Python 写以重建可信 chunk 层；Go 接管后改 Python 只读 |
| `research_projects` | W | X | - | [planned] L1 全局调度 |
| `research_runs` | W | X | - | [planned] 同上 |
| `research_plans` | W | X | - | [planned] 同上 |
| `research_tasks` | W | X | - | [planned] 写必须带 `WHERE lease_token = $t`（02 §3.4 fencing） |
| `research_task_dependencies` | W | X | - | [planned] 同上 |
| `research_events` | W | X | - | [planned] 事件日志/SSE 游标归 Go，Redis 不得作为唯一事件源 |
| `outbox_events` | W | X | - | [planned] 同上 |
| `research_budget_usage` | W | X | - | [planned] Python 上报 usage，Go 记账 |
| `model_usage_records` | W | X | - | [planned] 同上 |
| `knowledge_items` | W | X | - | [planned] Python 只交候选（02 §3.2 约定） |
| `exploration_gaps` | W | X | - | [planned] 同上 |
| `evidence_links` | W | X | - | [planned] 同上 |
| `research_claims` | W | X | - | [planned] 同上 |
| `report_sections` | W | X | - | [planned] 同上 |
| `ai_executions` | R | W | - | [present] Python 独占；Go 只读状态推进自己的 ResearchTask |

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
| 库里存在、但**本表故意不登记** | `parent_chunks` `paper_nodes` `citation_edges` `glossary_entries` `alembic_version`（5 张） | D6 已确定“先审计，再明确归属与生命周期”，不是已逐表定案；因此本矩阵暂不替它决定目标权限。前四张里 `paper_nodes`/`citation_edges`/`glossary_entries` 当前未发现业务写入调用方（schema 存在不证明功能已实现），`alembic_version` 属 alembic 那条线，不是 Go 的表 |

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
Python 目标可写 ≤ 2）与 note 的存在性标识。当前过渡运行权限另由 [角色配置工具](../scripts/configure_database_roles.py) 实际落实，并以真实受限连接验证；
工具只授予当前真实调用所需权限，尚不等于上表的目标 Go 写入接管。未来业务表/角色变更仍随对应阶段设计实施。

## 当前写入偏差（迁移期事实，不是额外授权）

| 表 | 当前实际行为 | 实现依据 |
| --- | --- | --- |
| users | Go 与旧 Python 注册接口都能写；目标仅 Go，旧接口尚未删除 | server/internal/auth、backend/api/auth.py |
| chat_sessions | Go 读与删除，Python 按轮 UPSERT；目标仅 Go，现有双写是待收编事实。**读路径已于 P1-1 收口**（`GET /sessions` 与 `GET /sessions/{id}` 均由 Go 原生，Python 那条按 `route-ownership` 登记为对拍保留待删）；**写路径的退出时点尚未拍板**，它随问答链接管（P1-4/G04）一起定，不提前撤权 | server/internal/session、backend/services/conversation_storage.py |
| chat_messages | Python 在追加问答事务中写入；Go 读（P1-1）并删除会话时触发级联；写权限同样待 P1-4 收编 | backend/services/conversation_storage.py、000001 外键 |
| parent_chunks | Python 负责当前索引路径的写入与清理 | backend/rag/parent_chunk_store.py |
| ai_executions | Python 已实际写入，不再是空表意图；Go 调度尚未完成 | backend/internal_api/postgres_executions.py |
| user_preferences | Go SQL 查询负责更新 | server/sql/queries/user_preferences.sql |
| schema_migrations / alembic_version | 分别为 Go 工具与旧 Alembic 版本表；不是业务写入 API | server/cmd/migrate、backend/core/database.py |

此表校准已识别调用，不声称数据库角色已隔离或所有读写路径已穷尽。
## 当前实现审计（2026-10-17）

- Go 查询写 users、user_preferences，删除 chat_sessions（外键级联 chat_messages），并读取认证与会话数据。
- Python 旧注册仍写 users，会话写 chat_sessions/chat_messages，索引写 parent_chunks，执行写 ai_executions；WorkspaceMember 只有访问校验读路径。
- workspaces/workspace_members、paper_nodes/citation_edges/glossary_entries 未发现业务 CRUD 写入口；不为“覆盖”新增空业务接口。
- 000004 去除 7 个非唯一 id 重复索引，保留主键、外键查询索引与业务唯一索引，新增 workspace_members(workspace_id,user_id) 唯一性。重复业务行导致迁移失败回滚，不擅自清洗。
- [实际权限快照](../docs/reference/schema-audit-2026-10-17.json) 显示当前开发连接为 postgres，拥有超级用户/建库/建角色/绕过 RLS 权限；没有把目标矩阵实现为运行角色 GRANT。
- 生产 compose 已提供独立受限 Go/Python 角色，显式角色工具按当前实际调用授予权限；不授予 SUPERUSER、CREATEDB、CREATEROLE、BYPASSRLS、public CREATE 或对象所有权。公开应用不再取得数据库管理员密码。
- Go 当前可读写 users/user_preferences、读取会话消息并删除会话；Python 当前可写旧认证/会话、parent_chunks、ai_executions，读取工作区成员与迁移版本；具体列举只维护在角色工具 PERMISSIONS/SEQUENCES。
- 真实权限测试验证允许现有读写、拒绝 public DDL 和跨域写；真实 Go/Python HTTP 也使用受限角色。测试角色随隔离库清理，未擅自改本机 .env。
- 这完成当前过渡权限隔离；目标唯一写入归属仍依赖 P1 接管，不能立即撤销 Python 现有能力，也不提前建立未来业务表。
