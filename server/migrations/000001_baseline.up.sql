-- 000001_baseline.up.sql —— ResearchPilot PostgreSQL 结构基线（P0-2，golang-migrate 形态）
--
-- 结构与来源（务必按此复核，勿凭 ORM 猜测）：
--   * 对象集合权威 = docs/refactor/schema-baseline.json（audit_schema.py --live 从真库只读导出：
--     source=live-postgres、PG 15.18、10 张表、alembic head=add_paper_knowledge_graph）。
--     本文件的每一条索引与约束都逐字对应它的 indexes / constraints 两段。
--   * 该 JSON **不含列清单**（脚本的 payload 只有 tables/indexes/constraints/column_diff），
--     因此列名、类型、NOT NULL、DEFAULT 抄自真正建出这个库的 alembic 链
--     （21f6caf0b15b_init → add_workspaces → add_paper_knowledge_graph，head 与 baseline 的
--     alembic 字段一致），并用 column_diff 逐项交叉验证通过：
--       - 22 条 no_server_default 与本文件"无 DEFAULT"的列一一对应；
--       - 1 条 only_in_db（alembic_version.version_num）就是本文件第 10 张表；
--       - column_diff 里没有任何 only_in_orm / type 条目 ⇒ 列集合与类型基名与真库一致。
--   * 禁止 ORM 生成：不照抄 models.py 的 Python 侧默认值。真库与 ORM 声明的差异如实登记，
--     不在此"修正"（paper_nodes.id 在真库**没有** ix_paper_nodes_id；users.username 与
--     paper_nodes.filename 的唯一性由 unique index 承载而**不是** UNIQUE 约束）。
--   * 非破坏 + 幂等：每句 CREATE 都带 IF NOT EXISTS，可在存量库上重复执行；
--     全文不含 DROP / TRUNCATE / DELETE / ALTER（只"登记"结构，不动存量数据）。
--   * 类型口径：真库全部时间列都是 timestamp without time zone；JSON 列是 json（不是 jsonb）；
--     主键是 integer + nextval（即 SERIAL），不是 SQL 标准 identity。
--     TIMESTAMPTZ 统一是后续独立迁移（05 §4），不混进基线。

-- ══════════════════════════════════════════════════════════════════════
-- 1/10 users —— 用户（认证垂直切片的权威表）
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL       NOT NULL,
    username      VARCHAR(100) NOT NULL,
    -- 格式 pbkdf2_sha256$<rounds>$<salt>$<digest>，Go 侧要逐字节复刻（含 rounds 与 hex 大小写）
    password_hash VARCHAR(255) NOT NULL,
    -- 真库有 DEFAULT 'user'（alembic server_default）；ORM 侧只是 Python 默认值
    role          VARCHAR(20)  NOT NULL DEFAULT 'user',
    -- 真库有 DEFAULT now()；Go 仍应显式写 UTC 值，不要依赖它（05 §4 的语义审计未完成）
    created_at    TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT users_pkey PRIMARY KEY (id)
);

-- ix_users_id 与主键重复，但真库确实存在这条索引 —— 如实登记
CREATE INDEX IF NOT EXISTS ix_users_id ON users (id);
-- 真库用 unique index 表达 username 唯一性（pg_constraint 里查不到 contype='u'）
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username);

-- ══════════════════════════════════════════════════════════════════════
-- 2/10 workspaces —— 工作区/多租户（必须在 chat_sessions.workspace_id 之前建）
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS workspaces (
    id         SERIAL       NOT NULL,
    name       VARCHAR(100) NOT NULL,
    owner_id   INTEGER      NOT NULL,
    created_at TIMESTAMP    NOT NULL DEFAULT now(),
    updated_at TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT workspaces_pkey PRIMARY KEY (id),
    CONSTRAINT workspaces_owner_id_fkey FOREIGN KEY (owner_id)
        REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_workspaces_id ON workspaces (id);
CREATE INDEX IF NOT EXISTS ix_workspaces_owner_id ON workspaces (owner_id);

-- ══════════════════════════════════════════════════════════════════════
-- 3/10 workspace_members —— 工作区成员
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS workspace_members (
    id           SERIAL      NOT NULL,
    workspace_id INTEGER     NOT NULL,
    user_id      INTEGER     NOT NULL,
    role         VARCHAR(20) NOT NULL DEFAULT 'member',
    created_at   TIMESTAMP   NOT NULL DEFAULT now(),
    CONSTRAINT workspace_members_pkey PRIMARY KEY (id),
    CONSTRAINT workspace_members_workspace_id_fkey FOREIGN KEY (workspace_id)
        REFERENCES workspaces (id) ON DELETE CASCADE,
    CONSTRAINT workspace_members_user_id_fkey FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_workspace_members_id ON workspace_members (id);
CREATE INDEX IF NOT EXISTS ix_workspace_members_user_id ON workspace_members (user_id);
CREATE INDEX IF NOT EXISTS ix_workspace_members_workspace_id ON workspace_members (workspace_id);

-- ══════════════════════════════════════════════════════════════════════
-- 4/10 chat_sessions —— 对话会话
-- 列顺序与真库物理顺序一致：workspace_id 是后来 ALTER 追加的，落在最后。
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS chat_sessions (
    id            SERIAL       NOT NULL,
    user_id       INTEGER      NOT NULL,
    session_id    VARCHAR(120) NOT NULL,
    metadata_json JSON         NOT NULL DEFAULT '{}',
    updated_at    TIMESTAMP    NOT NULL DEFAULT now(),
    created_at    TIMESTAMP    NOT NULL DEFAULT now(),
    -- 真库唯一可空列之一：删除工作区时置 NULL
    workspace_id  INTEGER      NULL,
    CONSTRAINT chat_sessions_pkey PRIMARY KEY (id),
    -- 真库是 UNIQUE **约束**（contype='u'）而不是 unique index，两者都要与 baseline 对齐
    CONSTRAINT uq_user_session UNIQUE (user_id, session_id),
    CONSTRAINT chat_sessions_user_id_fkey FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE,
    -- 这条外键在真库里的名字是显式的 fk_chat_sessions_workspace_id，不是 PG 自动命名
    CONSTRAINT fk_chat_sessions_workspace_id FOREIGN KEY (workspace_id)
        REFERENCES workspaces (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_chat_sessions_id ON chat_sessions (id);
CREATE INDEX IF NOT EXISTS ix_chat_sessions_session_id ON chat_sessions (session_id);
CREATE INDEX IF NOT EXISTS ix_chat_sessions_user_id ON chat_sessions (user_id);
CREATE INDEX IF NOT EXISTS ix_chat_sessions_workspace_id ON chat_sessions (workspace_id);

-- ══════════════════════════════════════════════════════════════════════
-- 5/10 chat_messages —— 对话消息
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS chat_messages (
    id             SERIAL      NOT NULL,
    session_ref_id INTEGER     NOT NULL,
    -- human / ai / system
    message_type   VARCHAR(20) NOT NULL,
    content        TEXT        NOT NULL,
    timestamp      TIMESTAMP   NOT NULL DEFAULT now(),
    -- 真库唯一可空列之一：非 RAG 消息为 NULL
    rag_trace      JSON        NULL,
    CONSTRAINT chat_messages_pkey PRIMARY KEY (id),
    CONSTRAINT chat_messages_session_ref_id_fkey FOREIGN KEY (session_ref_id)
        REFERENCES chat_sessions (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_chat_messages_id ON chat_messages (id);
CREATE INDEX IF NOT EXISTS ix_chat_messages_session_ref_id ON chat_messages (session_ref_id);

-- ══════════════════════════════════════════════════════════════════════
-- 6/10 parent_chunks —— 父块正文（无外键，独立存储）
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS parent_chunks (
    chunk_id        VARCHAR(512)  NOT NULL,
    text            TEXT          NOT NULL,
    filename        VARCHAR(255)  NOT NULL,
    file_type       VARCHAR(50)   NOT NULL DEFAULT '',
    file_path       VARCHAR(1024) NOT NULL DEFAULT '',
    page_number     INTEGER       NOT NULL DEFAULT 0,
    parent_chunk_id VARCHAR(512)  NOT NULL DEFAULT '',
    root_chunk_id   VARCHAR(512)  NOT NULL DEFAULT '',
    -- 数值语义以实现为准：1=章级、2=段级、3=叶级（models.py 的 docstring 是错的，05 §3.3）
    chunk_level     INTEGER       NOT NULL DEFAULT 0,
    chunk_idx       INTEGER       NOT NULL DEFAULT 0,
    updated_at      TIMESTAMP     NOT NULL DEFAULT now(),
    CONSTRAINT parent_chunks_pkey PRIMARY KEY (chunk_id)
);

CREATE INDEX IF NOT EXISTS ix_parent_chunks_filename ON parent_chunks (filename);

-- ══════════════════════════════════════════════════════════════════════
-- 7/10 paper_nodes —— 论文知识图谱节点（D5 死表，但结构是现状真相）
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS paper_nodes (
    id             SERIAL        NOT NULL,
    filename       VARCHAR(255)  NOT NULL,
    title          VARCHAR(500)  NOT NULL DEFAULT '',
    year           INTEGER       NOT NULL DEFAULT 0,
    authors        VARCHAR(1000) NOT NULL DEFAULT '',
    abstract       TEXT          NOT NULL DEFAULT '',
    citation_count INTEGER       NOT NULL DEFAULT 0,
    created_at     TIMESTAMP     NOT NULL DEFAULT now(),
    CONSTRAINT paper_nodes_pkey PRIMARY KEY (id)
);

-- 已知漂移，如实登记、不在基线里"修正"（05 §1 / §2.5 交给 000002_fix_drift）：
--   1) 唯一性由这条 unique index 承载，真库**没有** UNIQUE 约束（sqlc 用 contype='u' 查不到它）；
--   2) 真库**没有** ix_paper_nodes_id —— models.py 的 index=True 从未落库，所以这里也不建。
CREATE UNIQUE INDEX IF NOT EXISTS ix_paper_nodes_filename ON paper_nodes (filename);

-- ══════════════════════════════════════════════════════════════════════
-- 8/10 citation_edges —— 引文边（source 引用 target）
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS citation_edges (
    id         SERIAL    NOT NULL,
    source_id  INTEGER   NOT NULL,
    target_id  INTEGER   NOT NULL,
    context    TEXT      NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT citation_edges_pkey PRIMARY KEY (id),
    CONSTRAINT citation_edges_source_id_fkey FOREIGN KEY (source_id)
        REFERENCES paper_nodes (id) ON DELETE CASCADE,
    CONSTRAINT citation_edges_target_id_fkey FOREIGN KEY (target_id)
        REFERENCES paper_nodes (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_citation_edges_id ON citation_edges (id);
CREATE INDEX IF NOT EXISTS ix_citation_edges_source_id ON citation_edges (source_id);
CREATE INDEX IF NOT EXISTS ix_citation_edges_target_id ON citation_edges (target_id);

-- ══════════════════════════════════════════════════════════════════════
-- 9/10 glossary_entries —— 缩略语条目
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS glossary_entries (
    id         SERIAL        NOT NULL,
    paper_id   INTEGER       NOT NULL,
    term       VARCHAR(200)  NOT NULL,
    definition VARCHAR(1000) NOT NULL,
    chunk_id   VARCHAR(512)  NOT NULL DEFAULT '',
    created_at TIMESTAMP     NOT NULL DEFAULT now(),
    CONSTRAINT glossary_entries_pkey PRIMARY KEY (id),
    CONSTRAINT glossary_entries_paper_id_fkey FOREIGN KEY (paper_id)
        REFERENCES paper_nodes (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_glossary_entries_id ON glossary_entries (id);
CREATE INDEX IF NOT EXISTS ix_glossary_entries_paper_id ON glossary_entries (paper_id);

-- ══════════════════════════════════════════════════════════════════════
-- 10/10 alembic_version —— alembic 遗留版本表
--
-- 为什么在基线里：真库的 10 张表包含它（baseline 的 column_diff 第 1 条就是
-- alembic_version.version_num = only_in_db），P0-2 的基线要如实反映真库物理结构，
-- 物理结构一致才能让"存量库打基线戳 / 新库走 000001"两条路径收敛到同一 schema。
--
-- 只建表，**不写版本行**：alembic 已按 05 §2.4 冻结为只读历史，基线不代替它做状态标记；
-- 存量库用 `migrate version 1` 只写 golang-migrate 自己的 schema_migrations。
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
