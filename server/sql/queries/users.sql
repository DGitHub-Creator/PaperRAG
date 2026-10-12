-- 认证垂直切片（P0-6：register / login / me）需要的 users 访问。
-- 只写这一张表：02 §6.2 里 users 的 Go 侧是独占写（●），Python 只读。

-- name: InsertUser :one
-- role 与 created_at 由调用方显式给值。理由和以前不同，得说清：
-- 真库这两列**有** DEFAULT（`DEFAULT 'user'` / `DEFAULT now()`，见 000001_baseline.up.sql），
-- 但 sqlc 不把 DEFAULT 编码进生成的类型，`git diff` 门禁也抓不到这类失真，
-- 所以靠这里写死：created_at 要的是 UTC 值，而 `now()` 取的是会话时区（05 §4 的语义审计未完成）。
-- 用户名重复走 ix_users_username 的 unique violation，由 Go 翻译成 409，不在 SQL 里预查
-- （预查与插入之间的窗口就是并发下的假成功）。
INSERT INTO users (username, password_hash, role, created_at)
VALUES ($1, $2, $3, $4)
RETURNING id, username, role, created_at;

-- name: GetUserByUsername :one
-- 登录路径专用：需要 password_hash 才能验签。调用方不得把整行放进响应。
SELECT id, username, password_hash, role, created_at
FROM users
WHERE username = $1;

-- name: GetUserByID :one
-- /me 路径专用：**故意不选 password_hash**。少一处可选字段，就少一处把它写进响应的机会。
SELECT id, username, role, created_at
FROM users
WHERE id = $1;
