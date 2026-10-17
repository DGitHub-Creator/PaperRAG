# Go 数据库迁移

本目录是 Go 管理的 schema 来源。编号与设计见 [数据库计划](../../docs/plans/05-database-migration.md)，实际运行证据见 [WORKLOG](../../docs/WORKLOG.md)。

## 执行与恢复

迁移通过 `server/cmd/migrate` 显式执行，不放入应用启动流程，不向公开入口自动增加 DDL 职责。
在仓库根目录运行：

```bash
uv run python scripts/dev.py migrate-go
```

使用当前环境的 DATABASE_URL；开发未配置地址时使用本机 compose 数据库，生产必须显式配置。
生产镜像含 `/app/migrate` 与 `/app/migrations`，部署命令见 [README](../../README.md#36-部署形态)。
存量库先保存可恢复备份。迁移失败先检查 SQL、数据与 dirty 状态，不直接 force、更不清库。
仅在明确已回滚/修复实际结构之后才使用 force 校正版本；版本号不能代替结构核对。

## 已实现的迁移

| 编号 | 内容 | 验证范围 |
| --- | --- | --- |
| 000001 | 历史基线结构 | 新库与存量结构兼容，保留历史版本表 |
| 000002 | ai_executions | 实际 PG 幂等、租约、结果与终态 |
| 000003 | user_preferences | 实际 HTTP 用户偏好与认证链路 |
| 000004 | index_constraints | 删除 7 个主键重复的非唯一索引；成员唯一性；重复数据失败整笔回滚 |
| 000005 | execution_replay | 首次接受输入 JSONB；真实进程退出后恢复；非终态输入禁止回滚丢弃 |

未来 paper_chunks、时间语义变更等尚未实现，不提前占用编号。
当前 Python 启动要求 clean 版本至少 5；启动检查不会自行修复 dirty 或重放旧 Alembic 建表链。

## 编写与验收

- 已发布迁移不原地修改；按实际实施顺序新增成对 up/down，写明数据影响与恢复办法。
- 创建使用明确幂等语义；业务唯一性靠约束。重复数据导致失败，不能擅自删行制造成功。
- 删除索引必须有查询/约束证据；当前审计器只允许基线中与主键严格重复的非唯一 id 索引，并要求 down 重建。
- 新时间列使用 TIMESTAMPTZ。既有 naive UTC 列保留语义，转换必须先调查、备份和验证。
- down 必须真实回退，不能靠 IF EXISTS 掩盖原对象不存在。可能丢数据的回滚先备份；000005 对未结束任务额外拒绝回滚。
- 运行角色由 scripts/configure_database_roles.py 在迁移后显式创建/更新，与业务 DDL 分开；只授当前调用所需权限，目标 table-acl 的写入接管另属阶段迁移。
- 新增 up 同步列入 server/sqlc.yaml，运行 dev.py gen，并核对生成物；不手改生成文件。

```bash
uv run python scripts/dev.py gen --check
uv run python scripts/audit_schema.py --check-baseline
uv run python scripts/audit_schema.py --verify-columns --out docs/reference/schema-audit-2026-10-17.json
uv run python scripts/verify_storage.py --http
```

最后一条创建隔离库，实际跑两遍迁移和存储/HTTP 回归，结束删除本轮隔离对象。
空库成功不能代替带数据兼容性；离线快照比对也不代表当前线上数据库。
