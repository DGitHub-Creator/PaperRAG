-- 000002_ai_executions.up.sql —— AI 执行记录表（P0-7，Python 独占写）
--
-- 为什么这张表的每一列都要能回指出处：`ai_executions` 的列清单**没有任何一处文档逐字写过**
-- （`docs/refactor/` 全集里提到它的只有 6 条语义叙述），最接近的清单是实现里的 dataclass。
-- 所以本文件按「列 = executions.py 的字段，约束 = 02 §3.4 + 契约」两条线逐条落，
-- 不给将来留下"这列是干什么的"的考古题。
--
--   * 列集合 = backend/internal_api/executions.py:26-42 的 `Execution` 逐字段对应
--     （该模块 docstring 自陈「字段与将来的 ai_executions 表一一对应」，这里就是那张表）。
--   * 读写归属 = contracts/table-acl.md:34（go=R / python=W / transition=-），
--     由 check_contracts.py:317 机检。**本文件不写 GRANT**：PG 角色名在任何地方都还没定义
--     （compose 现在只有单一 POSTGRES_USER），给不存在的角色授权等于把纪律写成一条必失败的
--     语句；落实留给 P0-8/P1 的部署面，届时和角色创建同批验。
--   * 时间列一律 TIMESTAMPTZ。05:191 只点名 `paper_*`/`research_*` 用 timestamptz，
--     这张新表两边都没点名，按同一方向处理——依据不是偏好而是契约：
--     schemas.py:94-99 强制 `deadline` 必须带时区，naive 列存不下这个语义，
--     而实现写的本来就是 `datetime.now(timezone.utc)`。基线那 9 张表的
--     `timestamp without time zone` 是对存量库的如实登记（转换由 05 §4 另批处理），
--     不是这张新表的模板。
--   * JSON 而不是 JSONB：Python 是独占写方，SQLAlchemy 的 `JSON` 落 PG 就是 `json`，
--     与基线口径一致（`chat_sessions.metadata_json` 同为 json）。当前没有按内容检索的消费者，
--     不为了将来可能的 GIN 索引换类型。
--   * `run_id` NOT NULL DEFAULT ''：契约里 run_id 可空，但 PG 的 UNIQUE 把 NULL 视为互不相等，
--     于是 02:114 要的 `UNIQUE(run_id, idempotency_key)` 在所有 run_id IS NULL 的行上**静默失效**。
--     库里用空串承载"缺失"（与基线 `file_type`/`file_path` 的 `DEFAULT ''` 同族写法），
--     Python 的 PG 后端负责 None ↔ '' 的映射，这条映射写在这里就是为了别丢。
--   * 三个时间戳都不给 DEFAULT：`created_at`/`updated_at`/`deadline` 全由写入方显式给值，
--     库侧 `now()` 会掩盖漏写并让"记录时间"变成"落库时间"。这与基线的 `DEFAULT now()` 惯例
--     **故意不同**：基线在登记存量，本文件在定义新契约。
--   * 不建 `lease_owner`/`lease_expires_at`：02:118 的租约设计提三列，实现（executions.py:36）
--     只有 `lease_token`，P0-7 的语义也只验到"结果落库前比对 token"。没人写的列等于没人维护的
--     字段；等 Go worker 真正起租约时再随续租/reaper 语义同批加（ADD COLUMN 非破坏、可幂等）。
--   * `task_type` 不加 CHECK：11 个类型会随 P1/P2 增长，DDL 与契约双写必然漂，类型集合由
--     check_contracts.py 对契约与实现注册表比对来管。`status` 的 CHECK 不同——五态是状态机的
--     边界，写进第六个字面量会让"终态不可逆"这套判定失去意义。
--   * 不预建额外索引：P0-7 的三条访问路径全走主键或两个唯一键；reaper 的扫描索引等 Go 侧
--     真写出那条查询时再加，加了也没人验的索引不叫优化叫负债。
--   * 非破坏 + 幂等：每句 CREATE 都带 IF NOT EXISTS，全文不含 DROP/TRUNCATE/DELETE/ALTER，
--     可在存量库上重复执行（`audit_schema.py --check-baseline` 判这条）。

-- ══════════════════════════════════════════════════════════════════════
-- 1/1 ai_executions —— 单次 AI 执行的权威记录（幂等键、状态机、结果、用量、错误）
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS ai_executions (
    execution_id        VARCHAR(64)   NOT NULL,
    task_id             VARCHAR(64)   NOT NULL,
    task_type           VARCHAR(32)   NOT NULL,
    -- canonical 形式 run_id:task_type:canonical_target（schemas.py 的 pattern 三段皆非空）；
    -- 第三段是文件名/目标描述，不设上界 → 取 512，与 parent_chunks.chunk_id 同宽
    idempotency_key     VARCHAR(512)  NOT NULL,
    status              VARCHAR(16)   NOT NULL DEFAULT 'queued',
    deadline            TIMESTAMPTZ   NOT NULL,
    created_at          TIMESTAMPTZ   NOT NULL,
    updated_at          TIMESTAMPTZ   NOT NULL,
    -- 可空语义用空串承载，理由见头注释：否则下面的唯一键会静默失效
    run_id              VARCHAR(64)   NOT NULL DEFAULT '',
    trace_id            VARCHAR(64)   NOT NULL DEFAULT '',
    lease_token         VARCHAR(64)   NOT NULL DEFAULT '',
    result              JSON          NULL,
    result_ref          VARCHAR(1024) NULL,
    proposed_tasks      JSON          NOT NULL DEFAULT '[]',
    evidence_candidates JSON          NOT NULL DEFAULT '[]',
    usage               JSON          NULL,
    errors              JSON          NOT NULL DEFAULT '[]',
    CONSTRAINT ai_executions_pkey PRIMARY KEY (execution_id),
    -- 两个幂等键都要唯一：02:114 定 UNIQUE(run_id, idempotency_key)，02:115 又要求
    -- 「以 task_id 建行」——executions.py:64-69 因此两把都查，Go 重试时可能只保住其中一个
    CONSTRAINT uq_ai_executions_run_idempotency UNIQUE (run_id, idempotency_key),
    CONSTRAINT uq_ai_executions_task_id UNIQUE (task_id),
    -- 五态逐字对齐 contracts/ai-execution.schema.json 的 Status 枚举
    CONSTRAINT ck_ai_executions_status CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    -- 互斥已由响应层强制（schemas.py:120-125），DDL 再 mirror 一份：
    -- 库里同时挂着内联结果与结果指针就是矛盾，而这种矛盾只有落库后才看得见
    CONSTRAINT ck_ai_executions_result_exclusive CHECK (result IS NULL OR result_ref IS NULL)
);
