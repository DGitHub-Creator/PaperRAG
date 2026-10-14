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
-- 按 id 取身份，**故意不选 password_hash**。少一处可选字段，就少一处把它写进响应的机会。
-- 注：本查询原先注明"/me 路径专用"，但那个声明落不了地——JWT 的 `sub` 是**用户名**不是 id，
-- /me 要先按用户名查才能拿到 id，而按用户名查的只有下面那条带 hash 的登录查询。
-- 所以 /me 走 GetProfileByUsername，本条留给将来按 id 取身份的路径（P1 的会话/文档归属校验）。
SELECT id, username, role, created_at
FROM users
WHERE id = $1;

-- name: GetProfileByUsername :one
-- /me 路径专用：**故意不选 password_hash**。令牌里只有用户名，而"哈希不进 /me 的响应"
-- 这件事要靠查询本身保证，不能靠调用方自觉（GetUserByUsername 的整行一旦传下去，
-- 就只剩"别忘了别序列化那个字段"这一层纪律在挡）。
SELECT id, username, role, created_at
FROM users
WHERE username = $1;

-- name: UpdateUserPasswordByUsername :one
-- 改密码路径（Go 侧）：写入方给的是**已经哈希过**的串，明文不进这一层。
-- 路由是 /api/v1/auth/password，先 GetUserByUsername 验旧口令再落到这里。
UPDATE users
SET password_hash = $2
WHERE username = $1
RETURNING id, username, role;

-- name: UpdateUserRoleByUsername :one
-- 种子/运维路径专用：把既有用户提升为 admin（或改回）。注册路径只在创建那一刻解析 role，
-- 之后没有任何"改角色"的业务入口——这条查询的存在是为了让 `cmd/seed` 幂等：
-- 账号已存在时不必删库重来，改一行 role 即可。
UPDATE users
SET role = $2
WHERE username = $1
RETURNING id, username, role, created_at;
