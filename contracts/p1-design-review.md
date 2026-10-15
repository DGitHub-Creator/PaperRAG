# P1 设计审查（接管卡开工前的架构准入）

> **这份文件是什么**：P1 的 Go 接管动作**开工前的设计结论**，不是 P1 的退出标准。
> 它回答的是"按现在的契约与数据形状接管完，P2 会不会反过来推翻 P1"。
>
> **它不是什么**：不是第二套真相。表归属看 [`table-acl.md`](table-acl.md)，面归属看
> [`route-ownership.md`](route-ownership.md)，响应与错误看 [`openapi.yaml`](openapi.yaml) 与
> [`error-codes.md`](error-codes.md)，执行面看 [`ai-execution.schema.json`](ai-execution.schema.json)。
> 本文件只写**这些文件之间还缺哪一条约定**，并对每一条给出引用；
> 一旦发现与权威契约冲突，**改权威契约并在这里记下改了什么**，不在这里另立一套。
>
> **门禁语义**（由 `scripts/check_design_review.py` 执行）：
> `status: proposed` 时仓库其余门禁不受影响；**任一适用卡进入 `in_progress` 或 `done` 而本文件仍不是
> `approved` → 校验失败**。`approved` 只能在五个维度的"人工确认"格全部签完之后改。

| 字段 | 值 |
| --- | --- |
| status | **proposed** |
| 适用卡 | P1-1, P1-2, P1-3, P1-4, P1-7 |
| 依据契约 | `contracts/openapi.yaml`, `contracts/error-codes.md`, `contracts/ai-execution.schema.json`, `contracts/table-acl.md`, `contracts/route-ownership.md` |
| 关联决策 | D3（已关闭）、D4（保留 P1 → P2）、D6（5 张未登记归属的表）、K1/K3/K4（`openapi.yaml` 的 `info.x-decisions`） |
| 关联台账 | C33, C34, C35, C36, C37（验收条件见 `rules/12` 的 A-2） |
| 不做什么 | 不新增退出标准（**不加 Y7**）、不改工时与分母、不改 P1/P2 依赖、不为未来建无真实需求的抽象 |

---

## 1. 数据标识

- **结论**：
  1. **PG 内部键与业务键分开看**。今天三类实体的形态是：代理主键 `SERIAL`（`users.id`、
     `chat_sessions.id`、`chat_messages.id`，见 `000001_baseline.up.sql`）＋ 业务键
     （`chat_sessions.session_id VARCHAR(120)`，由调用方给）＋ 生成的 UUID 串
     （`ai_executions.execution_id VARCHAR(64)` = `uuid4()`，`000002_ai_executions.up.sql:45`）。
     **P1 接管一律按业务键寻址，代理主键不出进程**——否则 P2 建 `papers` 系列表时会撞进
     "对外 id 是自增整数"这条无法回头的路。
  2. **同一条 chunk 现在有两个身份**：Milvus 的物理主键是 `INT64 auto_id`
     （`backend/vectordb/milvus_client.py:226`），逻辑键是 `chunk_id VARCHAR(512)`（UUID，同文件 `:252`）。
     P2 的正文真相层要用哪个键被引用，**必须在 P1-4 之前就定**，因为引用一旦带上 auto_id，
     "Milvus 可重建"这条定位当场作废（重建集合 → auto_id 全变）。本审查的结论：
     **`chunk_id`（UUID）是唯一可跨服务、可重建存活的标识；auto_id 只允许作为 Milvus 内部物理键存在，
     禁止出现在任何 HTTP 响应、PG 列或契约字段里。**
  3. **任务标识已经有两把幂等键，不能再加第三把**：`(run_id, idempotency_key)` 与 `task_id`
     都是 UNIQUE（`000002_ai_executions.up.sql:66-69`），而 Python 侧两把都查
     （`backend/internal_api/executions.py:64-92`）。P1-3 的上传编排任务态**沿用这套**，
     不复用 `upload_jobs.py:128` 的 `uuid4().hex` 私有形态去新造第三种 job id。
  4. **跨服务关联靠 `trace_id`**，不靠把上游 id 塞进下游 id 命名里。Go 侧已有注入
     （`server/internal/observability/trace.go`），P1-0 的透传必须保证 trace_id 在
     Go → Python → 日志三处同一个值。
- **依据**：`contracts/ai-execution.schema.json::ExecuteRequest`、
  `server/migrations/000002_ai_executions.up.sql`、`backend/vectordb/milvus_client.py`、
  `backend/services/upload_jobs.py`、`docs/rules/02-target-architecture.md`
- **未决**：
  - 文档（`/documents` 那条面）今天**没有稳定 id**——它的标识是文件名，而文件名可被覆盖写。
    P2-1 建 `paper_files` 时要不要引入 `content_hash` 作为跨库身份（`rules/14` M2 提过按 hash 去重），
    **属 P2 决策，本审查不替它拍**，只登记为待决。
  - 契约里的路径参数用 **camelCase**（`/sessions/{sessionId}`、`/documents/upload/jobs/{jobId}`），
    而两侧实现与 `route-ownership.md` 都用 **snake_case**（`{session_id}`）。这是**第三套拼写**。
    本审查的建议：契约改成 snake_case 与实现对齐；因为改的是 `openapi.yaml`，
    **需要人工确认后再动**（`check_contracts.py` 按 operationId 与路径双向校验，改名会牵动它）。
- **判据**：`uv run python scripts/check_contracts.py`（路径与前端实调双向吻合）＋
  新增用例断言"响应体里不出现 Milvus auto_id"（属 P1-1 的验收项，写进卡）。

## 2. 服务职责

- **结论**：
  1. **一个业务能力只有一个执行方**，且这条事实由 `route-ownership.md` 承载、由
     `check_route_ownership.py` 校验；本审查不重复列举谁做什么。
  2. **P1 期间 Go 的角色是门面 + 认证/偏好/会话读删的执行方**。判"这条面该不该在 P1 搬进 Go 执行"的唯一
     尺子是：**它是否需要 PG 里还不存在的数据**——需要就不搬（`documents` 搬不动的根因正是文档真相不在 PG），
     不需要就搬（sessions 读删已验证过这条）。
  3. **权威来源逐条唯一**：业务真相 = PostgreSQL（`users` / `user_preferences` / `chat_sessions` /
     `chat_messages` / `ai_executions`）；召回索引 = Milvus（**可重建**）；缓存与队列 = Redis
     （**不是真相**，任何"只有 Redis 里有"的状态都算缺陷）；文件对象 = `UPLOAD_DIR` 文件系统（P2 前）。
     这条与 `AGENTS.md` §1 的三条架构定位同义，本审查的作用是**把它翻译成 P1 每张卡能执行的判据**。
  4. **Python 不引入第二个全局调度器**：`USE_REDIS_JOB_MANAGER` 之类的进程内循环只允许服务于
     单次执行，跨请求的任务编排属 Go（P1-3）。
- **依据**：`contracts/route-ownership.md`、`contracts/table-acl.md`、`AGENTS.md`、
  `docs/rules/13-frontend-backend-architecture.md`、`backend/services/upload_jobs.py`
- **未决**：D6 的 5 张表（`parent_chunks` / `paper_nodes` / `citation_edges` / `glossary_entries` /
  `alembic_version`）归属仍未定；按 D6 的拍板**先审计使用情况**再一次性定归属与生命周期，
  本审查不提前定。
- **判据**：`uv run python scripts/check_route_ownership.py` ＋ 每张接管卡的验收里必须写
  "本卡把哪条面从 `proxy` 改成 `go`，并同步改了归属表"。

## 3. 错误语义

- **结论**：
  1. **信封只有一种**：`{"detail": ...}`（K1、K4 已定案，见 `openapi.yaml` 的 `info.x-decisions`）。
     Go 侧一律走 `server/internal/httpapi/envelope.go`，不许 handler 手拼。
  2. **内部面的九码映射不许新造码**：`contracts/error-codes.md` 与
     `backend/internal_api/codes.py` 是同一份映射（`INVALID_PAYLOAD` 400 / `PARSE_FAILED` 422 /
     `MODEL_TIMEOUT` 504 / `CANCELLED` 409 / `INDEX_UNAVAILABLE` 503 …）。
     Go 门面接管某条面时，**必须原样映射同一批码与 HTTP 状态**，逐字对拍写在 chain 层。
  3. **422 的降级要显式保留**：K4 把 FastAPI 的校验数组降成 `400 + 字符串`。Go 侧本来就是 400，
     所以"接管后错误码变化"这件事必须在卡面上声明，别让前端按 422 分支的代码静默失效。
  4. **超时/重试/幂等三件是一套，不是三个特性**：只有 `retryable=true` 的码（`MODEL_TIMEOUT` /
     `MODEL_RATE_LIMIT` / `INDEX_UNAVAILABLE` / `INTERNAL`）允许 Go 重试；重试必须带
     `idempotency_key`，否则就是在制造重复执行。**`UNSUPPORTED_TASK_TYPE` 与 `PARSE_FAILED` 永不重试。**
  5. **失败恢复靠状态机可见，不靠把失败伪装成空**：Python 的
     `conversation_storage.py:170` 把存储异常吞成空列表是**已知反面样本**，Go 如实回 500
     （第十四轮定的有意分歧）。接管时不许把这条"对齐"回去。
- **依据**：`contracts/error-codes.md`、`backend/internal_api/codes.py`、
  `docs/plans/09-milestone-p0.md`、`docs/rules/12-known-code-issues.md`
- **未决**：`/metrics` 仍是三不管端点（C31）：契约有、Python 有、nginx 无 location、Go 未实现。
  它归 Go 还是归"从契约里删掉"，**需要人工拍**，本审查不擅自定。
- **判据**：`uv run python -m pytest -q -m chain`（错误文案逐字对拍已在 `tests/chain`）＋
  P1-4 的 Y3（帧序列与错误码一起比）。

## 4. 流式事件契约

- **结论**：
  1. **今天没有真正的流式契约，只有实现形状**：SSE 的实际行为是**整段答案一次性下发**
     （`rules/14` M6 记为折扣；`docs/reference/00-audit.md` 也记过同一事实）。
     因此 P1-4 的"接管流式"必须**先定事件协议再接管**，否则门面会把一个未定义的形状固化下来。
  2. **最小事件集（本审查的建议，待人工确认）**：`delta`（增量文本）/ `tool`（工具调用可见进度）/
     `citation`（引用出现，**P1 期间显式标为非证据级**）/ `done`（正常终止）/ `error`（带九码之一）。
     终止语义唯一：`done` 之后不得再有任何帧；客户端**不得以 `[DONE]` 与 `{"type":"done"}` 两种写法并存**
     ——今天两侧分歧（`docs/reference/01-current-architecture.md` §4 记过），必须择一并写进契约。
  3. **能力边界要说白**：断线续传（`Last-Event-ID` + 持久事件日志）属 **P2-5**，
     所以 P1 的 e2e/chain **不许把"刷新后能续上"当已实现**；P1 只保证一次会话内不丢帧。
  4. **取消**：Go 侧取消要落到内部面的 `POST /executions/{id}/cancel`（`contracts/ai-execution.schema.json::x-endpoints`），
     而不是悄悄断开连接——断开连接不产生任何可观测状态。
- **依据**：`contracts/ai-execution.schema.json`、`docs/reference/01-current-architecture.md`、
  `docs/rules/14-feature-modules.md`、`backend/api/chat.py`
- **未决**：①WS（`/api/v1/ws/chat`）与 SSE 的关系——两条通道今天能力重叠，P1-4 是收口成一条还是并存，
  **需要人工拍**；②事件帧是否带 `trace_id`（建议带，但要确认前端能忽略未知键而不炸，今天前端解析器未验过）。
- **判据**：Y3（SSE 字节级帧序列跨语言比对）＋ 一条新 chain 用例断言"`done` 帧之后连接关闭且无第二终止帧"。

## 5. 数据所有权

- **结论**：
  1. **表级 owner 的唯一出处是 `table-acl.md`**，本审查不复制一份。P1 期间要做的只有一件事：
     **让"声明的归属"与"实际的写入方"一致**——今天的偏差已点名：
     `ai_executions` 声明 `python: W`，但**没有任何写入方**（`ExecutionStore` 是进程内 dict，台账 C37）；
     `paper_chunks` 声明 `go: W / python: W until-P2`，而**这张表在库里不存在**（台账 C30）。
  2. **迁移责任**：Go 侧 schema 走 `server/migrations/` + `dev.py migrate-go`（决策 D8 已定案：
     显式动作，不进启动路径）；Python 那条线走 alembic，两张版本表互不知晓，
     **共存的前提是迁移一律 `IF NOT EXISTS`**。P1 不许把两条线合并（合并属 P2 建表时一并设计）。
  3. **列规范沿用既有三条**（`plans/05 §2.6`）：新表一律 `TIMESTAMPTZ`；可空列做唯一键成员时必须
     `NOT NULL DEFAULT ''`（PG 里 NULL 互不相等，唯一约束会静默失效——`000002` 的 `run_id` 就是这条的落地）；
     实现没写到的列不预先建；`GRANT` 在角色定义之前不写。
  4. **缓存不是归属方**：Redis 里的会话缓存不构成第二个写者，但**写者必须负责失效**（C35）。
     P1-1 的删除面在 C35 处置前，不许被宣称为"已完整接管"。
- **依据**：`contracts/table-acl.md`、`server/migrations/000002_ai_executions.up.sql`、
  `docs/plans/05-database-migration.md`、`docs/rules/12-known-code-issues.md`
- **未决**：D6 那 5 张表；以及 `papers` 系列 4 张表的建表时点（P2-1）——P1 **不建 P2 的表**，
  本审查只登记它们的归属意图与切换后旧路径的移除时点。
- **判据**：`uv run python scripts/check_contracts.py`（ACL 值域与 ≤2 张 Python 可写表）＋
  `uv run python scripts/audit_schema.py --check-baseline`。

---

## 6. 人工确认（`approved` 的唯一条件）

**机器只能查结构与一致性，不能证明架构正确。** 下列五项各自确认后，把 `status` 改成 `approved`；
缺任一项就停在 `proposed`。

| # | 维度 | 需要人回答的问题 | 确认 |
| --- | --- | --- | --- |
| 1 | 数据标识 | 业务键对外、代理主键不出进程、`chunk_id` 作为唯一可存活标识——认可吗？契约的 camelCase 路径参数要不要改成 snake_case？ | ☐ |
| 2 | 服务职责 | "需要 PG 里还不存在的数据就不搬"这条尺子认可吗？D6 的 5 张表审计由谁、在哪个卡里做？ | ☐ |
| 3 | 错误语义 | 九码不许新造、`UNSUPPORTED_TASK_TYPE`/`PARSE_FAILED` 永不重试——认可吗？`/metrics` 归谁？ | ☐ |
| 4 | 流式事件契约 | 五类事件与"唯一终止帧"建议认可吗？WS 与 SSE 收口成一条还是并存？ | ☐ |
| 5 | 数据所有权 | P1 不建 P2 的表、两条迁移线暂不合并、写者负责缓存失效——认可吗？ | ☐ |

## 7. 本审查明确不做的事

- **不为"未来扩展性"预建抽象**：没有真实需求的分层（例如先把 `evidence`/`report`/`guard` 做成 Go 包）
  一律不做——D7 才是要讨论它的地方，且它仍待拍。
- **不在 P1 建临时可信存储、双写系统或兼容层**（`08 §10`）。
- **不把 P1 的引用呈现为可信证据**：P1 期间引用可以不是证据级，但**未经验证的来源编号不得被描述为
  已完成语义接地或原文定位**；证据级引用属 P2（Z1/Z3）。
- **不改阶段依赖、不加退出标准、不动工时与分母**。
