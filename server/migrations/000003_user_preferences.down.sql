-- 000003_user_preferences.down.sql —— 与 000003_user_preferences.up.sql 配对（golang-migrate 形态）
--
-- 语义：删掉 up 建出的唯一一张表。索引、外键与 CHECK 随表一起消失，不单独 DROP。
--
-- 为什么不需要顺序、也不需要 CASCADE：本表**引用 users，但没有别的表引用它**，
-- 所以它必须是"最后一个被删"的依赖端——回退时先删它再谈 users，不会连带删任何东西。
--
-- 为什么刻意不写 IF EXISTS：与 000001/000002 的 down 同一条纪律（05 §2）——不许拿
-- `DROP TABLE IF EXISTS` 把"库里本来就没这张表"当成回退成功，那会把表名写错、迁移没打过
-- 这类真实故障掩盖成绿灯。表不存在时本文件明确报错，这正是要的行为。
--
-- ⚠️ 执行前必读：本 down 连数据一起删除。偏好是可重建的轻量状态（用户在设置页再选一次即可），
-- 但反正删除前先 `pg_dump -Fc` 是 05 §4.2 的统一要求。回退窗口内 Go 侧必须停写，
-- 否则 PUT /me/preferences 会在删除后立即报错（该表是 Go 独占写）。

-- 1/1 user_preferences（外键指向 users，单向依赖，单条即可）
DROP TABLE user_preferences;
