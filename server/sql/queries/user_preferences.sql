-- 用户偏好的读写（设置页的「偏好设置」「外观·主题」两个板块）。
-- 只碰 user_preferences 一张表：table-acl.md 里它的 Go 侧是独占写（W），Python 是 X。

-- name: GetUserPreferences :one
-- 无行是**正常路径**（用户从没改过偏好），由 Go 侧把 pgx.ErrNoRows 翻成默认值，
-- 不要在这里用 COALESCE 造假行——那会让"未设置"与"设成了默认值"在库里分不开。
SELECT user_id, theme, start_view, created_at, updated_at
FROM user_preferences
WHERE user_id = $1;

-- name: UpsertUserPreferences :one
-- 偏好是"整行覆盖"语义：两个字段都是闭集枚举，不存在只改一个、另一个保持原值的歧义
-- （前端每次提交整份偏好），所以 upsert 整行而不是分列 UPDATE。
-- created_at 在冲突分支**不更新**（首次落库的时间是它唯一的含义）；
-- updated_at 由写入方给 UTC 值，理由见 000003 头注释（库里没有 DEFAULT）。
INSERT INTO user_preferences (user_id, theme, start_view, created_at, updated_at)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (user_id) DO UPDATE
    SET theme = EXCLUDED.theme,
        start_view = EXCLUDED.start_view,
        updated_at = EXCLUDED.updated_at
RETURNING user_id, theme, start_view, created_at, updated_at;
