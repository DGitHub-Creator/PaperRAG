-- sqlc 代码生成用的参照结构（不是迁移，不执行）。
--
-- 为什么单独存在：P0-2 的正式基线必须由真实库核查生成（05 §1 末：「Go 的迁移基线
-- 由此生成，不由 ORM 直接生成」），而本机此刻没有 PG。为了让 P0-3 的生成层先跑起来，
-- 这里只登记**认证垂直切片要动的表**，形状取自 backend/core/models.py 的 ORM 声明
-- （PG dialect 编译结果），并逐列注明与 PG 默认值有关的行为差异。
--
-- 收编纪律：P0-2 产出 server/migrations/000001_baseline.up.sql 之后，把
-- server/sqlc.yaml 的 schema 从本文件切到 migrations 目录并重跑 `dev.py gen`。
-- 届时 sqlc 生成的结构体若有任何字段变化，`git diff --exit-code` 门禁就会红，
-- 也就是说这份临时参照被换掉时不会悄悄漏掉差异。

CREATE TABLE IF NOT EXISTS users (
    -- ORM: Integer primary_key → PG 侧是 integer + nextval 默认值（不是 SQL 标准 identity）
    id            SERIAL       NOT NULL PRIMARY KEY,
    -- ORM: String(100) unique index → 唯一性由 ix_users_username 这条 UNIQUE INDEX 保证，
    --      不是 table constraint（05 §1 记录过这类漂移，`contype='u'` 查不到它）
    username      VARCHAR(100) NOT NULL UNIQUE,
    -- 格式 pbkdf2_sha256$<rounds>$<salt>$<digest>，由 backend/core/auth.py 产生，
    -- Go 侧 P0-6 要逐字节复刻（含 rounds 与 hex 大小写）
    password_hash VARCHAR(255) NOT NULL,
    -- 'user' | 'admin'。默认值 "user" 在 ORM 的 Python 侧，DDL 里没有 DEFAULT，
    -- 所以 Go 必须显式写这一列，否则 NOT NULL violation。
    role          VARCHAR(20)  NOT NULL,
    -- created_at 同理：`default=datetime.utcnow` 是 Python 侧默认，库里无 DEFAULT，
    -- 且列型是 timestamp without time zone（05 §4）。Go 必须自己写入 UTC 值，
    -- 并且不能假设驱动会补这个字段。
    created_at    TIMESTAMP    NOT NULL
);
