# `server/migrations/` —— Go 侧 schema 的唯一来源

> 编号分配与新表口径见 [`docs/plans/05-database-migration.md`](../../docs/plans/05-database-migration.md) §2.6，
> 本文件只写"在这里加一个迁移要遵守什么、以及哪条机检会拦住你"。

## 现状：有文件，**没有执行器**

`migrate` CLI 从未接线（PATH 上没有它，`server/go.mod` 里也没有 golang-migrate 依赖），
`dev.py migrate` 跑的是容器内 `alembic upgrade head`。今天读这两份 `.sql` 的只有两个**离线**工具：
`scripts/audit_schema.py --check-baseline` 与 sqlc。

所以在本目录放一个文件 ≠ 它被应用过。要手工应用到某个库（本轮实测用的就是这条路）：

```bash
# 应用一遍（ON_ERROR_STOP 让任何语句失败都变成非零退出码，别用 || true 吞掉）
docker exec -i researchpilot-postgres psql -U postgres -d <库名> \
  -v ON_ERROR_STOP=1 -q < server/migrations/000002_ai_executions.up.sql
echo $?   # 0 才算过
```

接执行器属 P0-8/P1，且要先拍"谁执行、什么时候执行、失败怎么办"（决策 D8 / 台账 C18）——
关键是**别因此长出第二个全局调度器**（`AGENTS.md` §7）。

## 已登记的编号

| 编号 | 内容 | 状态 |
| --- | --- | --- |
| `000001` | `baseline`：从真库结构抄录的 10 张表 / 59 列 | 已落，已在真 PG 上验过幂等 |
| `000002` | `ai_executions`：17 列，逐列回指 `backend/internal_api/executions.py` 的 dataclass | 已落，已在真 PG 上验过幂等 |
| `000003` | `fix_drift` | 预留 |
| `000004` | `paper_chunks` | 预留 |

**条件性的预留不占号**（例如 `auth_compat`：只在真要补列时才存在）。拿着没用的号比空着更糟。

## 写 `*.up.sql` 的规则

1. **只做登记，不动存量**：`CREATE TABLE IF NOT EXISTS`。出现 `DROP` / `TRUNCATE` / `DELETE` /
   `ALTER` 就是在动已有数据，`--check-baseline` 直接判失败。
2. 新表的时间列一律 **`TIMESTAMPTZ`**（旧表的 `timestamp without time zone` 语义不确定，见
   [`timestamp-audit.md`](../../docs/reference/timestamp-audit.md)）。
3. **可空列做唯一键成员时必须 `NOT NULL DEFAULT ''`**：PG 里 `NULL ≠ NULL`，
   否则 `UNIQUE(a, b)` 在 `b IS NULL` 的行之间静默失效（`000002` 的 `run_id` 就是这个原因）。
4. 实现没写到的列**不预先建**（`000002` 只建 `lease_token`，不建 `lease_owner`/`lease_expires_at`）。
5. **不写 `GRANT`**：角色尚未定义，写了就是死语句。

## 写 `*.down.sql` 的规则

用**无 `IF EXISTS`** 的真实回退：`DROP TABLE ai_executions;`

这不是疏漏。`audit_schema.py` 明确禁止 down 里出现 `DROP TABLE IF EXISTS`，理由是"库里本来就没这张表"
不能被当成回退成功。后果是 **down 不可重入**——第二次跑会报
`table "ai_executions" does not exist` 并以非零码退出，这是**刻意的**（2026-10-12 在真 PG 上实测确认）。

`down` 只允许作用于空库或已备份的库；是否强制 `pg_dump` 前置属未拍板的 D6。

## 加一个新迁移要同做的事

`sqlc.yaml` 的 `schema:` 是**逐个列 `*.up.sql`** 的，不能整目录交出去：
按文件名排序 `000001_baseline.down.sql` 排在 `.up.sql` 之前，sqlc 会**先执行 down 再执行 up**，
生成物看着正常、实际是按"回退后的库"生成的。

所以新加 `0000NN_xxx.up.sql` 必须同批：

1. 在 `server/sqlc.yaml` 的 `schema:` 列表里加上这个文件（漏了 `dev.py gen` 会拒绝生成）；
2. 跑 `uv run python scripts/dev.py gen`，并把生成物一起提交（`gen --check` 是漂移门禁）；
3. 跑 `uv run python scripts/audit_schema.py --check-baseline`。

`dev.py gen` 的三条前置机检：schema 源是含 `.down.sql` 的目录 → 拒绝；
`migrations/*.up.sql` 未登记 → 拒绝；`internal/db/X.sql.go` 有孤儿 → 拒绝。

## 两条门禁的口径差别（别混）

| 命令 | 判什么 | 不判什么 |
| --- | --- | --- |
| `audit_schema.py --check-baseline` | **文件形态**：up 非破坏、幂等写法、down 配对 | 内容与真库是否一致 |
| `audit_schema.py --verify-columns` | **内容**：逐列比类型 / varchar 长度 / NOT NULL / DEFAULT，比对对象是 `docs/reference/schema-baseline.json` 的 `columns` 段 | 快照本身过期了没有——快照需带 `columns`，缺时如实 exit 2 |
