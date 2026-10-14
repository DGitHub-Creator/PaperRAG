# 时间列语义审计（`05` §4.1 / X6 第三问）

> 生成：2026-10-12T08:41:18+00:00 · 取数命令：`uv run python scripts/probe_timestamps.py`
> 引擎：PostgreSQL 15.19 (Debian 15.19-1.pgdg13+2) · 会话 `timezone` = `Etc/UTC` · `log_timezone` = `Etc/UTC`
> 时间列总数：naive `11` 个 / aware `0` 个

## 1. 探针法：写入路径 × 会话时区 → 落库语义

已知时刻 `2026-01-01 07:08:09+00:00`。`偏移(小时)` 是`extract(epoch from 落库值) − 真值 epoch` 再除以 3600；0 表示落库值就是 UTC 挂钟。

| 会话时区 | 写入路径 | 落库挂钟 | 偏移(小时) | 判定 |
| --- | --- | --- | --- | --- |
| `UTC` | `sql_literal_utc_wallclock` | `2026-01-01 07:08:09` | 0.0 | utc |
| `UTC` | `sql_now_at_tz_utc` | `2026-10-12 08:41:17` | 0.0 | utc |
| `UTC` | `python_aware_datetime_utc` | `2026-01-01 07:08:09` | 0.0 | utc |
| `Asia/Shanghai` | `sql_literal_utc_wallclock` | `2026-01-01 07:08:09` | 0.0 | utc |
| `Asia/Shanghai` | `sql_now_at_tz_utc` | `2026-10-12 08:41:17` | 0.0 | utc |
| `Asia/Shanghai` | `python_aware_datetime_utc` | `2026-01-01 15:08:09` | 8.0 | local |
| `Etc/UTC` | `sql_literal_utc_wallclock` | `2026-01-01 07:08:09` | 0.0 | utc |
| `Etc/UTC` | `sql_now_at_tz_utc` | `2026-10-12 08:41:17` | 0.0 | utc |
| `Etc/UTC` | `python_aware_datetime_utc` | `2026-01-01 07:08:09` | 0.0 | utc |

**读法**：`sql_literal_utc_wallclock` 是「把 UTC 挂钟原样塞进 naive 列」，偏移必为 0，它是另外两条的参照。真正说明问题的是另外两条：

- `sql_now_at_tz_utc`（`05 §4.1` 点名的写法）：值来自 **PG 自己的时钟**，`AT TIME ZONE 'UTC'` 把 timestamptz 转成 UTC 挂钟的 naive 值，所以这条路径**与会话时区无关**，落库语义恒为 UTC。
- `python_aware_datetime_utc`：经驱动传一个 **aware** datetime。PG 会先按会话 `TimeZone` 把绝对时刻换算成挂钟、再丢弃偏移，所以落库值随会话时区偏移 —— **这就是 `05 §4` 说的「不能假定为 UTC」**。

## 2. 分布法：小时直方图

| 表.列 | 行数 | 峰值小时 | 峰值占比 | 判定 |
| --- | --- | --- | --- | --- |
| `chat_messages.timestamp` | 0 | — | — | **no_data** |
| `chat_sessions.created_at` | 0 | — | — | **no_data** |
| `chat_sessions.updated_at` | 0 | — | — | **no_data** |
| `citation_edges.created_at` | 0 | — | — | **no_data** |
| `glossary_entries.created_at` | 0 | — | — | **no_data** |
| `paper_nodes.created_at` | 0 | — | — | **no_data** |
| `parent_chunks.updated_at` | 0 | — | — | **no_data** |
| `users.created_at` | 0 | — | — | **no_data** |
| `workspace_members.created_at` | 0 | — | — | **no_data** |
| `workspaces.created_at` | 0 | — | — | **no_data** |
| `workspaces.updated_at` | 0 | — | — | **no_data** |

## 3. 交叉法：`chat_messages` 的 timestamp 与 serial id 单调性

- 方法：chat_messages id vs timestamp
- 判定：**no_data**（检查 0 个多消息会话，违例 0 处）

## 4. 每表每列判定（`05 §4.1` 要的交付形状）

| 表 | 列 | 类型 | 存量行数 | 判定 |
| --- | --- | --- | --- | --- |
| `chat_messages` | `timestamp` | `timestamp` naive | 0 | **no_data** |
| `chat_sessions` | `created_at` | `timestamp` naive | 0 | **no_data** |
| `chat_sessions` | `updated_at` | `timestamp` naive | 0 | **no_data** |
| `citation_edges` | `created_at` | `timestamp` naive | 0 | **no_data** |
| `glossary_entries` | `created_at` | `timestamp` naive | 0 | **no_data** |
| `paper_nodes` | `created_at` | `timestamp` naive | 0 | **no_data** |
| `parent_chunks` | `updated_at` | `timestamp` naive | 0 | **no_data** |
| `users` | `created_at` | `timestamp` naive | 0 | **no_data** |
| `workspace_members` | `created_at` | `timestamp` naive | 0 | **no_data** |
| `workspaces` | `created_at` | `timestamp` naive | 0 | **no_data** |
| `workspaces` | `updated_at` | `timestamp` naive | 0 | **no_data** |

## 5. 本报告的边界（不写清就等于夸大结论）

- ②分布法与③交叉法判的是**存量数据**的语义。2026-10-11 导出快照的那个原真库已随 Docker 数据卷清空而永久消失（台账 C20），本机也无原生 PG，所以这两法在重建库上**永远没有对象**——报 no_data 不是'等以后有数据'，而是那一问在这台机器上不再可判。
- ①探针法测的是引擎与驱动的行为，与存量无关，因此在新库上的结论依然成立：naive 列里 aware 值会被按会话时区偏移后丢弃偏移。
- 本脚本不执行任何 DDL，也不改任何业务表；探针表是 TEMP + ON COMMIT DROP + ROLLBACK。

## 6. 对 `05 §4.2` 转换迁移的后果

- 探针法给出的结论是**面向今后**的：只要列还是 naive，aware 写入就会被会话时区偏移。这一条与有没有存量数据无关，所以它仍然成立。
- 分布法/交叉法原本用来判**存量**该按哪个偏移转回来；存量对象已不可复原（C20），因此 `05 §4.2` 那条 `USING col AT TIME ZONE 'UTC'` 的**猜测风险**在当前这台机器上没有可判的输入。**不要把它当成「已验证可以转换」**——应记为「无存量数据，转换风险未评估」，并在真有带数据的库上做（或按 `05 §4.2` 的前置表先在克隆库演练）。
- `05 §2.6` 已拍板新表一律 `TIMESTAMPTZ`，所以增量部分（如 `ai_executions`）不继承这个问题。
