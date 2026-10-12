-- 000002_ai_executions.down.sql —— 与 000002_ai_executions.up.sql 配对（golang-migrate 形态）
--
-- 语义：删掉 up 建出的唯一一张表。索引、唯一约束与 CHECK 随表一起消失，不单独 DROP。
--
-- 为什么不需要顺序、也不需要 CASCADE：这张表**不引用别的表，也没有别的表引用它**
-- （run_id / task_id 是 Go 侧 research_tasks 的标识，跨表外键会在 P0-8 之前造出一个
--  删不动的依赖；02 §6.2 把 Python 的写权限限定在这张表与过渡期的 paper_chunks，也不含引用）。
--
-- 为什么刻意不写 IF EXISTS：与 000001_baseline.down.sql 同一条纪律——05 §2 禁止拿
-- `DROP TABLE IF EXISTS` 把"库里本来就没这张表"当成回退成功，那会把表名写错、迁移没打过
-- 这类真实故障掩盖成绿灯。表不存在时本文件明确报错，这正是要的行为。
--
-- ⚠️ 执行前必读：本 down 连表内数据一起删除。`ai_executions` 是执行历史的唯一真相
-- （Go 读状态、审计与重放都靠它，PG 是唯一业务真相），存量环境执行前先 `pg_dump -Fc`
-- 备份（05 §4.2 的备份要求）。另外它是 Python 独占写（contracts/table-acl.md:34），
-- 回退窗口内 Python 侧必须停写——否则 internal_api 的 PG 后端会在删除后立即 INSERT 失败。

-- 1/1 ai_executions（无外键依赖，单条即可）
DROP TABLE ai_executions;
