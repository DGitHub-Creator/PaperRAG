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
| status | **approved** |
| 适用卡 | P1-1, P1-2, P1-3, P1-4, P1-7 |
| 依据契约 | `contracts/openapi.yaml`, `contracts/error-codes.md`, `contracts/ai-execution.schema.json`, `contracts/table-acl.md`, `contracts/route-ownership.md` |
| 关联决策 | D3（已关闭）、D4（保留 P1 → P2）、D6（使用审计已完成，目标归属与生命周期待定）、K1/K3/K4（`openapi.yaml` 的 `info.x-decisions`） |
| 关联台账 | C33, C34, C35, C36, C37, C38, C39, C40（C39 监听地址与 C40 的 `/documents` 接管前置是执行期新登记，验收条件见 `docs/plans/12-known-code-issues.md` 的当前条目；登记不改变本审查五维结论与适用卡范围） |
| 不做什么 | 不新增退出标准（**不加 Y7**）、不改工时与分母、不改 P1/P2 依赖、不为未来建无真实需求的抽象 |

---

## 0. 当前事实与开工资格（2026-10-17 校准）

日程唯一来源是 `docs/progress.json` 的 `schedule`，本文件不另排周次。
2026-10-17 用户授权按推荐方案确认，五维设计已批准；T0 仍需执行 agent 核验环境就绪。
修复完成、模块范围确认、结构门禁通过均不自动批准设计，也不自动完成 P1 任务卡。

| 项目 | 当前事实 | 对下一步的影响 |
| --- | --- | --- |
| C33 | Go 已实现 Redis 限流并挂载认证/会话路由；已有第 21 次登录 429、伪造代理头无效的历史验收 | 已修复，不是取消任务，也不是新增限流待办 |
| C34 | 新追踪写前校验并投影；坏历史追踪置 null，正文保留并告警 | 详情读取的投影技术阻塞已消除 |
| C35 | Python 会话缓存已移除，直接读取 PG | 不再要求新增缓存失效机制；并发验收仍按任务要求执行 |
| 会话详情 GET | 2026-10-18 起由 Go 原生读取（路由 `server/cmd/api/main.go:139`，投影 `server/internal/session/trace.go`），归属表已改 `go`；Python 那条按 P1-1 作**对拍保留**，删掉它才算卡片收口 | 逐字判据 `tests/chain/test_go_read_session_detail.py`；投影面三方核对 `scripts/check_contracts.py` |

上述实现核对入口为 `server/internal/httpapi/ratelimit.go`、
`backend/services/conversation_storage.py`、`backend/schemas/schemas.py`；
历史运行证据见问题台账与 WORKLOG，本次文档校准没有重新运行真实 HTTP 栈。
现有 `tests/chain/test_go_read_sessions.py` 可复用行为基线，但经 Go 反代得到相同 JSON
不能证明 Go 原生读取；接管验收还必须核对显式路由、实际 SQL 路径与归属表。

## 1. 数据标识

- **结论**：以下为已批准设计方向；接口与运行行为变更由执行 agent 在对应任务中落实并验收。
  1. 保留已有业务键寻址；PG 代理主键与对外业务键分开，不因接管批量重编号。
  2. Milvus auto_id 是物理键，不作为未来可重建引用的身份。现有逻辑 chunk_id
     并非统一 UUID：解析路径存在文件名、页码、块序号组成的键。P1 保留已有逻辑键；
     P2 的版本化身份与 content_hash 需另行设计，不能声称现有键已跨覆盖/重解析稳定。
  3. 内部执行沿用 task_id 与 (run_id, idempotency_key) 唯一约束及 PG 持久化校验；
     上传业务 job 与局部 execution 的身份关系在 P1-3 明确，不把两种实体强行当同一个 id。
  4. 当前 Go 无上游值时生成 16 位 hex，Python 直连无上游值时生成 32 位 hex；
     两侧均接受已有 X-Trace-Id。建议 P1 保留透传兼容，将头名、生成形态、输入长度/字符边界
     写入 OpenAPI；当前契约未声明该头，代码注释不能替代契约。
- **依据**：`backend/rag/document_loader.py`、`backend/internal_api/postgres_executions.py`、
  `server/internal/observability/trace.go`、`backend/app.py`、`contracts/openapi.yaml`
- **未决**：路径参数占位名目前契约 camelCase、实现 snake_case；它们表示同一 URL 结构，
  不是第三条公开接口。建议契约统一 snake_case，影响文档与生成客户端符号；确认后再改契约。
  trace 建议保留已有 16/32 hex 生成形态及合法上游值，统一输入边界；若统一生成长度，需要相应兼容测试。
- **判据**：契约与实现检查；跨 Go/Python trace 透传、非法输入、旧逻辑键引用回归。
  新增验收在对应任务中实施，不冒充已有用例通过。

## 2. 服务职责

- **结论**：Go 是公开入口与未来全局编排方；Python 执行局部 AI 任务。
  接管复用已有数据与能力，不提前创建 P2 业务表。Redis 任务管理的状态保存与启动恢复
  不等于第二个全局调度器；当前局部恢复不得被误删。
  逐条迁移后更新路由归属与旧路径保留理由，不能仅凭存在 ratelimit.go 就宣称接管完成。
- **依据**：`contracts/route-ownership.md`、`contracts/table-acl.md`、
  `docs/reference/13-frontend-backend-architecture.md`、`backend/services/upload_jobs.py`
- **未决**：D6 的使用情况已有审计；待定的是 parent_chunks、paper_nodes、citation_edges、
  glossary_entries、alembic_version 的目标归属与生命周期，而不是重做一轮不存在的审计。
  建议 G01 明确过渡边界，具体切换随对应 P1/P2 卡落实，不删现有 parent_chunks 能力。
- **判据**：路由归属检查、逐条真实行为对拍与旧路径退出证据；数据不存在时不得用空实现冒充迁移。

## 3. 错误语义

- **结论**：沿用 detail 信封、既有内部错误码和 retryable 语义；重试有界且沿用首次接受的幂等输入。
  当前会话存储异常已向上传播，不能再把旧的吞异常行为列为现存缺陷。
  校验失败按现行契约核对，不能将 PARSE_FAILED 的 422 与请求校验的 400 混为一谈。
- **依据**：`contracts/error-codes.md`、`backend/internal_api/codes.py`、
  `backend/services/conversation_storage.py`、`contracts/openapi.yaml`
- **未决**：/metrics 当前是 Python 实现、Go 未原生接管且 nginx 未公开该路径；这是访问边界问题，
  不应从契约删除来制造一致。建议保留内部采集，公开监控入口与访问控制另经明确设计，不阻塞会话读取。
- **判据**：真实存储失败不得返回空历史；接管时对拍状态码与错误体，重试/超时/取消分别验证。

## 4. 流式事件契约

- **结论**：OpenAPI 已有 SSE/WS 事件定义，不能再写“没有契约”。当前完整答案事件
  不证明逐 token 输出。SSE 以字面量 [DONE] 终止、WS 以 type=done 终止，是现有传输契约，
  不因两种编码不同就认定错误。建议 P1 保持两种通道与兼容编码，验证各自只终止一次、终止后无事件。
  持久事件日志/续传属 P2；Go 到内部执行取消的接线仍需在接管卡验证，断开连接不等于取消成功。
- **依据**：`contracts/openapi.yaml`、`backend/api/chat.py`、`contracts/ai-execution.schema.json`
- **未决**：新增 delta/tool/citation/done/error 五类事件会改变协议，是可选的新设计，尚未批准；
  建议本轮不将其作为接管前提。是否在帧内增加 trace_id、是否统一新协议需另定兼容与前端测试，
  当前不根据未知字段是否能忽略来声称已兼容。
- **判据**：P1-4 首帧到达、取消、断线、错误和唯一终止语义的跨语言与浏览器验证；不能只比最终正文。

## 5. 数据所有权

- **结论**：目标权限看 table-acl，当前过渡权限由角色工具落实。
  ai_executions 已由 Python PostgresExecutionStore 实际写入并持久化恢复输入，不再是内存空壳；
  该存储由 internal_api/router.py 装配，含 advisory lock 与两个幂等轴，C37 已闭；这不等于 Go 全局调度已实现。未来 papers 系列表仍待 P2。
  Go 管理的库显式 migrate-go，Python 启动校验版本至少 5 且 clean 后跳过旧 Alembic；
  未由 Go 管理的旧库走原 Alembic 路径，不能以 IF NOT EXISTS 为由混跑两条迁移链。
  新时间列用 TIMESTAMPTZ，唯一性按业务语义设计，不把所有可空唯一成员一律改为空串。
  会话已无 Redis 缓存，不新增无实际需要的失效系统。
- **依据**：`contracts/table-acl.md`、`backend/internal_api/postgres_executions.py`、
  `backend/core/database.py`、`scripts/configure_database_roles.py`
- **未决**：D6 目标归属、P1 旧 Python 写入退出时点与 P2 建表切换仍需批准；
  建议保留当前必需权限，接管验证完成后逐项收回，不能提前撤权破坏现有调用。
- **判据**：数据库基线、存量迁移与受限角色真实读写验收；目标 ACL 静态通过不证明当前运行权限完整落实。

## 6. 人工确认（approved 的唯一条件）

机器只检查结构与状态一致性。2026-10-17 用户明确要求“按照你的推荐进行确认”，以下五项按推荐方案批准；签署依据为本轮用户授权，由本 agent 记录，不冒充人工逐项操作。

| # | 维度 | 已确认方案与影响 | 确认 |
| --- | --- | --- | --- |
| 1 | 数据标识 | 保留业务键/现有逻辑 chunk_id；路径占位名统一 snake_case；trace 保留 Go 16/Python 32 hex 生成形态，补头契约与有界输入校验，不统一生成长度。 | ☑ |
| 2 | 服务职责 | 建议 Go 逐条接管、Python 保留局部执行恢复；沿用 D6 已有审计，明确目标归属后随任务切换，不重做限流/缓存修复。 | ☑ |
| 3 | 错误语义 | 建议沿用现有信封、九码与有界幂等重试；metrics 保留内部采集，公开访问单独设计，不删除契约消除差距。 | ☑ |
| 4 | 流式事件契约 | 建议 P1 保留 SSE/WS 及各自终止编码，补首帧/取消验收；五类新事件与统一协议另行批准，避免接管时扩大协议变更。 | ☑ |
| 5 | 数据所有权 | 建议沿用当前实际持久化与迁移分流，接管后收回旧写入权限；不新增缓存、不提前建 P2 表，D6 生命周期逐项明确。 | ☑ |

## 7. 本审查明确不做的事

不改变阶段依赖、工时、产品分母或退出标准；不提前建抽象、临时存储或双写系统；
不把 P1 引用展示说成证据级接地，不把历史验收或代理对拍说成本轮原生接管验收。

## 8. 批准范围与执行交接

本次批准的是上述推荐设计，不表示接口契约已修改、功能已实现、环境已就绪或真实验收通过。
各节“未决”中，路径占位名对齐、trace 兼容、内部 metrics、保留双通道与迁移分流已按 §6 选定；
P2 身份设计、新流式协议、公开监控入口仍属于后续独立设计，不作为本次接管阻塞。

- 第一项任务：执行 agent 先读取全局计划和 progress.json，盘点环境/端口/容器，核验迁移 clean、依赖与隔离验收条件；满足后再更新 schedule 和对应任务状态，不沿用历史环境结果。
- G02 首个切片：GET /api/v1/sessions/{session_id} 从 proxy 迁至 Go 原生读取。保持鉴权、越权/不存在行为、正文/引用/坏历史追踪投影及时间格式；验证真实 SQL 路径，再更新归属表和契约，按既定卡片退出旧路径。
- trace 输入方案：接受 1–128 个 ASCII 字母、数字、点、下划线或连字符；缺失/不合法则生成新 id，不回显非法值，不将 trace 用于认证。先把规则写入 OpenAPI，再同步 Go/Python 实现与边界测试；这是待执行要求，不是当前已实现行为。
- D6 过渡处置：parent_chunks 保留 Python 当前读写，随 P2 正文切换再审批迁移；paper_nodes/citation_edges/glossary_entries 保留现有结构，不新增业务写入授权，启用或删除须对应设计；alembic_version 仅旧迁移工具维护，Go 库不重放旧链。当前必需权限不提前撤销。
- 路径占位名改动只统一契约符号，不新增 URL；trace/契约准备纳入既有 P1-0/对应卡，不新增并行调度层，不扩大第一切片。
- C33/C34/C35 不重做；Go 全局编排、PG 全文、逐 token 输出等未完成能力继续按正式任务推进。新五类事件与帧内 trace 不在本次批准范围。

远端整合说明：已保留 C38 追踪头契约缺口与 Go 反代响应头去重修复；执行 agent 应沿用边缘单点回写 X-Trace-Id，不能重新追加上游同名响应头。
