-- 000001_baseline.down.sql —— 与 000001_baseline.up.sql 配对（golang-migrate 形态）
--
-- 语义：up 建出的 10 张表按依赖逆序真实回退（先删引用方，再删被引用方，不需要 CASCADE）。
--
-- 为什么**刻意不写 IF EXISTS**：05 §2 的幂等纪律禁止拿它把 "库里本来就没这张表" 当成回退成功
-- ——那会把真实错误（表名写错、基线没打过）掩盖成绿灯。表不存在时本文件会明确报错，
-- 这正是想要的行为。（校验器 audit_schema.py 从 2026-10-12 起对 up 与 down **都先剥注释再判**，
-- 所以注释里讲这条纪律不再会被误判成违规；语句里真写了那四个词仍然会红。）
--
-- ⚠️ 执行前必读：本 down 会连表内数据一起删除。存量库上已用 `migrate version 1` 打过基线戳，
-- 对存量库执行 down 等价于弃库，必须先做 `pg_dump -Fc` 全量备份（05 §4.2 的备份要求）。
-- 只读核查纪律同样适用：不要在没备份的真库上跑它。
--
-- 待人工确认的语义歧义（见交付结论）：alembic_version 是 alembic 遗留表、不是本基线"拥有"的对象。
-- 当前按"up 建了什么 down 就删什么"处理；若团队认为冻结的 alembic 元数据不该由 Go 迁移回退，
-- 把最后一句注释掉即可（不影响 migrate 的成对性）。

-- 5/10 引用 chat_sessions
DROP TABLE chat_messages;
-- 4/10 引用 users / workspaces
DROP TABLE chat_sessions;
-- 3/10 引用 workspaces / users
DROP TABLE workspace_members;
-- 6/10 无外键
DROP TABLE parent_chunks;
-- 8/10 引用 paper_nodes
DROP TABLE citation_edges;
-- 9/10 引用 paper_nodes
DROP TABLE glossary_entries;
-- 7/10 被 citation_edges / glossary_entries 引用
DROP TABLE paper_nodes;
-- 2/10 被 workspace_members / chat_sessions 引用
DROP TABLE workspaces;
-- 1/10 被 workspaces / workspace_members / chat_sessions 引用
DROP TABLE users;
-- 10/10 alembic 遗留版本表（无外键依赖，放最后）
DROP TABLE alembic_version;
