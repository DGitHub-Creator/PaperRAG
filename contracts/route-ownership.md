# 路由归属表（`scripts/check_route_ownership.py` 执行）

> **这张表回答一个问题**：某条 HTTP 面**今天由谁实现**、**该由谁实现**、**两者不一致时为什么可以暂时不一致**。
>
> 它存在的理由不是文档爱好。2026-10-14 定的处置是「Go 接管一条，Python 那条就删」，但同日实测
> Python 仍在服务 `POST /auth/register`、`POST /auth/login`、`GET /auth/me`、`GET /sessions`、
> `DELETE /sessions/{session_id}` 五条——因为 chain 层的**逐字对拍**要求两侧同时在场。
> "有意保留"与"忘了删"在外面长得一模一样，而 `check_contracts.py` 只比前端↔契约、**看不见服务侧**（台账 C31）。
> 所以这里把每条面的归属写成表，由脚本回查三个真相源：Go 源码、Python 路由表、chain 用例。

## 1. 归属取值

| 归属 | 含义 | 机检要求 |
| --- | --- | --- |
| `go` | Go 原生实现，是这条路径的**唯一裁判** | 必须出现在 Go 的路由注册里 |
| `shared` | 两侧都有、且**刻意**都有（探针：Python 要能报自己的依赖状态） | Go 有 + Python 有 |
| `proxy` | 入口仍是 Go，但它只做转发——业务实现还在 Python | 必须出现在 Python 路由表里，且**不得**被 Go 显式注册 |
| `internal` | 服务间内部面，浏览器不可达 | 路径必须以 `/internal/` 开头，且在 Python 路由表里 |

**`Python 仍在` 那一列是例外登记，不是状态描述**。归属为 `go` 而 Python 仍在服务的，只有两种写法：

| 写法 | 要求 | 为什么 |
| --- | --- | --- |
| `对拍保留（<卡片> 删，tests/chain/<文件>.py::<用例名>）` | 用例文件存在且 `def <用例名>` 在里面 | 保留的唯一正当理由是**跨语言对拍还需要两侧在场**，那就得有可指认的用例 |
| `**未对拍保留**（<卡片> 删，台账 C<NN>）` | 台账号必须存在 | 没有对拍就把它当**欠账**登记。写成"对拍保留"而没有用例，等于用一个不存在的证据占住一条没人会去删的遗留 |

按路径字面量 grep 是判不准的：`test_go_read_sessions.py` 里删除面写的是 `LIST_PATH + 具体 id`，
字面量匹配会把它误判成"没测过"。**所以登记到用例名，不登记到字符串**——这是确定性的。

## 2. 归属表

| 方法 | 路径 | 归属 | Python 仍在 | 说明 |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/auth/register` | go | **未对拍保留**（P1-2 删，台账 C36） | chain 的种子是直接写 PG 的（第十三轮定的做法），所以这条面两侧从未对拍过。删它之前要先取一致基线 |
| POST | `/api/v1/auth/login` | go | 对拍保留（P1-2 删，tests/chain/test_contract_chain.py::test_login_response_shape_matches） | X4 的两侧互验与响应形状都钉在用例里 |
| GET | `/api/v1/auth/me` | go | 对拍保留（P1-2 删，tests/chain/test_contract_chain.py::test_me_returns_identical_json） | 同一份 JSON 逐字一致，含 role 的取库不取 claims |
| POST | `/api/v1/auth/password` | go | — | Python 从来没有这条面，Go 是新面而非复刻（P0-6） |
| GET | `/api/v1/me/preferences` | go | — | 同上，配迁移 `000003` |
| PUT | `/api/v1/me/preferences` | go | — | 同上 |
| GET | `/api/v1/sessions` | go | 对拍保留（P1-1 删，tests/chain/test_go_read_sessions.py::test_go_read_session_list_matches_python_byte_for_byte） | naive TIMESTAMP 的 isoformat 形状与空列表 `[]` 都钉住 |
| DELETE | `/api/v1/sessions/{session_id}` | go | 对拍保留（P1-1 删，tests/chain/test_go_read_sessions.py::test_go_read_unknown_session_delete_matches_python_text） | C35 已修复：Python 会话缓存已移除，删除后直接读 PG；并发验收仍按 P1-1 执行 |
| GET | `/api/v1/health` | go | — | 契约声明的前缀探针。Python 的 health **不带** `/api/v1` 前缀（C31） |
| GET | `/api/v1/ready` | go | — | 两个探测键 `database` + `redis`，键名与 detail 文案与 Python 逐字对齐 |
| GET | `/health` | shared | 是 | 两侧都有是刻意的：Python 容器的 healthcheck 打的是自己（`Dockerfile` backend 段） |
| GET | `/ready` | shared | 是 | 同上。dev 形态下 Python 由 `dev.py serve` 起，探针仍归它自己 |
| GET | `/api/v1/sessions/{session_id}` | proxy | 是 | C34 投影技术阻塞已消除；仍由 Python 实现，G01 批准且环境就绪后可作为 G02 首个接管切片，不能据此提前开工 |
| POST | `/api/v1/auth/refresh` | proxy | 是 | 前端不调但仍可达；刷新面归 Go 之前要先对齐 JWT claims 的 `type` 语义 |
| POST | `/api/v1/chat` | proxy | 是 | 非流式问答。流式那一向由下面的 `/chat/stream` 承担 |
| POST | `/api/v1/chat/stream` | proxy | 是 | SSE。Go 门面属 P1-4，事件日志与续传属 P2-5 |
| WS | `/api/v1/ws/chat` | proxy | 是 | WebSocket。Go 的反代已支持 Upgrade，但接管要连会话状态一起搬（P1-4） |
| GET | `/api/v1/documents` | proxy | 是 | 文档真相不在 PG：读文件系统 `UPLOAD_DIR` + `ingested_state.json` + Milvus 的 chunk 数 |
| POST | `/api/v1/documents/upload` | proxy | 是 | 前端不调但仍可达（同步形态） |
| POST | `/api/v1/documents/upload/async` | proxy | 是 | 前端在用。任务态在进程内存 `upload_jobs`，搬 Go 的前置是先持久化到 PG（P1-3） |
| GET | `/api/v1/documents/upload/jobs` | proxy | 是 | 前端不调但仍可达 |
| GET | `/api/v1/documents/upload/jobs/{job_id}` | proxy | 是 | 前端在用 |
| DELETE | `/api/v1/documents/{filename}` | proxy | 是 | 前端不调但仍可达（同步删除） |
| DELETE | `/api/v1/documents/delete/async/{filename}` | proxy | 是 | 前端在用 |
| GET | `/api/v1/documents/delete/jobs/{job_id}` | proxy | 是 | 前端不调但仍可达 |
| POST | `/api/v1/documents/ingest` | proxy | 是 | 前端不调但仍可达（直接入库） |
| POST | `/api/v1/cache/clear` | proxy | 是 | 前端不调但仍可达。这是检索等缓存清理面，不是已移除的会话缓存；接管时单独核对清理范围 |
| GET | `/api/v1/stats/usage` | proxy | 是 | 前端不调但仍可达。usage 持久化属 P2-6 |
| DELETE | `/api/v1/stats/usage` | proxy | 是 | 同上 |
| GET | `/metrics` | proxy | 是 | 契约与 Python 实现已存在；nginx 未公开该路径，Go 未原生实现。公开访问与采集边界待设计，不通过删除契约消除差距 |
| POST | `/internal/v1/ai/execute` | internal | 是 | 内部执行面。R3 保证 nginx 不把它暴露给浏览器 |
| POST | `/internal/v1/ai/executions` | internal | 是 | 同上 |
| GET | `/internal/v1/ai/executions/{execution_id}` | internal | 是 | 同上 |
| GET | `/internal/v1/ai/executions/{execution_id}/result` | internal | 是 | 同上 |
| POST | `/internal/v1/ai/executions/{execution_id}/cancel` | internal | 是 | 同上 |
| GET | `/internal/v1/ai/healthz` | internal | 是 | 内部面自己的探针，不对浏览器开放 |
| GET | `/internal/v1/ai/readyz` | internal | 是 | 同上 |

## 3. 三个真相源（脚本读的就是这三处）

| 侧 | 取数方式 |
| --- | --- |
| Go 的路由注册 | 扫 `server/cmd/api/main.go` 与 `server/internal/httpapi/*.go` 里的 `.Get/.Post/.Put/.Delete(...)` 字面量；`/api/*` 那类通配**不算**注册 |
| Python 的路由表 | `from backend.app import app` 后取 `APIRoute`/`APIWebSocketRoute`，不看静态挂载 |
| chain 对拍 | `tests/chain/*.py` 里是否出现该路径字面量 |

## 4. 这张表**不**回答的事

- 不回答"这条面有没有鉴权"——那在 `openapi.yaml` 与 `contracts/error-codes.md`。
- 不回答"哪张表谁能写"——那在 [`table-acl.md`](table-acl.md)。归属是**进程**的事，ACL 是**数据**的事，
  两者会不一致（Go 已经在写 `chat_sessions`，而 `paper_chunks` 那类纸面归属的表根本还不存在，见 C30）。
- 不回答"前端调不调"——那由 `check_contracts.py` 的前端↔契约双向吻合负责。
