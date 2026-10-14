-- 000003_user_preferences.up.sql —— 用户偏好表（产品雏形的设置页用；Go 独占写）
--
-- 为什么是这张表、为什么是现在：设置页要落「偏好设置」与「外观·主题」两个板块，
-- 而"PostgreSQL 是唯一业务真相"要求偏好跨设备一致，不能只躺在前端的 localStorage 里
-- （localStorage 只是缓存，见 docs/rules/10-frontend-structure.md R2）。
--
--   * 号为什么是 000003：05 §2.6 拍的规则是「号按依赖顺序给，谁先被运行链路需要谁靠前」。
--     此前 000003/000004 分别预留给 `fix_drift`（P0-2 尾）与 `paper_chunks`（P2-1），
--     两者都还没开工，而本表今天就被设置页需要——按同一条规则让位，那两个号顺延到
--     000004/000005（05 §2.5/§2.6/§3 同批改指）。预留不占号、真正的实现才占号。
--   * 读写归属 = contracts/table-acl.md（go=W / python=X）：偏好是 Go 门的服务端状态，
--     Python 执行单次 AIExecution 时不需要它（语言/主题由前端在请求里携带）。
--   * 时间列一律 TIMESTAMPTZ，且不给库侧 DEFAULT。这两条都是 05 §2.6 对新表的明文口径：
--     基线的 `timestamp without time zone` + `DEFAULT now()` 是对存量库的**如实登记**，
--     不是新表的模板；`now()` 取的是会话时区，会把"记录时间"变成"落库时间"并掩盖漏写。
--     `created_at`/`updated_at` 由 Go 显式给 UTC 值。
--   * `theme` 加 CHECK：三态（light/dark/system）是**闭集**，写进第四个值就等于外观层多出
--     一个没有 token 的分支。`start_view` **不加** CHECK：它取自前端路由名，路由集会随
--     产品增长，DDL 与前端双写必然漂（这条与 000002 对 `task_type` 不加 CHECK 同理）——
--     合法性由 Go 侧校验，但**只校验形状**（小写 slug），不抄一份前端路由表进 Go；
--     不认识的名字由前端在跳转时回退到 chat（分工见 14 §19）。DB 这里只保证它是短文本。
--   * 为什么不建 `locale`：语言在**未登录**的登录页也要生效，而那时还没有用户行可查，
--     所以它的真相必须留在前端（i18n 已有 localStorage，R2 的唯一所有者）。在服务端再存
--     一份会造成"两个真相"，与原则冲突——不做。
--   * 非破坏 + 幂等：CREATE 带 IF NOT EXISTS，全文不含 DROP/TRUNCATE/DELETE/ALTER，
--     可在存量库上重复执行（`audit_schema.py --check-baseline` 判这条）。
--   * 不写 GRANT：PG 角色名至今没有定义（与 000002 同一条理由），给不存在的角色授权
--     等于把纪律写成一条必失败的语句。

-- ══════════════════════════════════════════════════════════════════════
-- 1/1 user_preferences —— 用户级偏好（当前：外观主题、登录后默认进入的页面）
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id    INTEGER     NOT NULL,
    -- light|dark|system；system 表示跟随操作系统（前端读 prefers-color-scheme 落地）
    theme      VARCHAR(16) NOT NULL DEFAULT 'system',
    -- 前端的路由名（chat/library/…）；Go 只校验"是小写 slug"这一形状，不在这里 CHECK
    start_view VARCHAR(32) NOT NULL DEFAULT 'chat',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT user_preferences_pkey PRIMARY KEY (user_id),
    -- 用户删除时偏好随行消失：偏好没有独立生命周期，留着就是孤儿行
    CONSTRAINT user_preferences_user_id_fkey FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT ck_user_preferences_theme CHECK (theme IN ('light', 'dark', 'system'))
);
