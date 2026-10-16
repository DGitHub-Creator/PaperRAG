# 13 — 当前实现与目标差距

> 性质：可维护的实现说明。核验日期：2026-10-16；对应本轮未提交重构工作区。
> 本文不授予阶段完成状态。进度只看 [progress.json](../progress.json)，运行读数见 [WORKLOG](../WORKLOG.md)。
> 目标见 [02](../rules/02-target-architecture.md)，整理前版本见 [历史快照](../archive/2026-10-16-13-frontend-backend-architecture.md)。

## 0. 请求与运行拓扑

开发：浏览器 → Vite → Go API → 尚未接管的 Python 路由。
Go、Python、前端运行源码；dev compose 仅中间件。prod compose 使用应用容器部署。
默认端口和配置以 compose、frontend/vite.config.js、server/internal/config 与 .env.example 为准。

## 1. 入口与归属

- Go 入口：[cmd/api/main.go](../../server/cmd/api/main.go)。原生提供认证、偏好、会话列表/删除及探针，其余按前缀反代。
- Python 入口：[app.py](../../backend/app.py)。仍保留浏览器业务接口和内部 AIExecution，尚未收缩成纯执行端。
- 逐路径归属只维护在 [route-ownership](../../contracts/route-ownership.md)，由 check_route_ownership.py 检查。
- Go worker 仍为骨架，全局研究调度与崩溃恢复没有完成。

## 2. 会话与聊天

- [ConversationStorage](../../backend/services/conversation_storage.py) 直接读 PostgreSQL，不再缓存会话与消息。
- append_turn 在一笔事务中追加问答，锁定同用户同会话的更新，不覆盖已有历史及追踪数据。
- Go 删除会话之后，Python 下一次读取以数据库为准；已用真实 HTTP 验证先读后删的可见性。删除与正在生成的新消息并发的产品语义仍需设计。
- [agent/core.py](../../backend/agent/core.py) 使用单层 LangGraph；消息累积、工具结果与引用来源通过图状态传递。
- 长历史仅在模型输入中压缩，不把摘要覆盖回完整数据库历史。
- 新追踪按 RagTrace 校验并投影；引用校验结果随答案保存，历史恢复区分 supported 真/假。旧追踪不合法时仅追踪置 null，保留正文并告警，不推断或伪造来源。
- SSE/WS 输出完成事件前提交问答；失败发 error，不伪装 DONE。
- 目前输出完整回答帧，**并非模型逐 token 流式输出**。断开会取消协程，但不能据此保证已启动的线程/模型调用立即终止。
- 引用标签校验只证明标签来自检索结果，未达到 P2 所要求的 PG 正文证据链。

## 3. 文档与检索

- [documents.py](../../backend/api/documents.py) 处理 HTTP；[document_jobs.py](../../backend/services/document_jobs.py) 统一同步/异步索引及删除。
- 上传按实际字节限制，先写独立 staging 文件；解析失败保留旧原件和旧索引。
- JSON 指纹状态使用锁、临时文件及原子替换，只登记成功文件；批量失败不覆盖成功前缀。
- 索引替换涉及文件、PostgreSQL、Milvus 和 BM25，**没有跨存储原子事务**；写入中途失败仍可能留下部分索引，原件与失败信息用于恢复。
- 文档目录与指纹仍依赖文件系统，不存在完整的 PG 文档真相层；Milvus text 长度限制仍存在。
- [workflow.py](../../backend/rag/workflow.py) 编排检索，[rag_pipeline.py](../../backend/rag/rag_pipeline.py) 实现节点，[state.py](../../backend/rag/state.py) 定义状态。
- 不使用长期 MemorySaver 保留每次 RAG 状态；PDF 多模态/布局能力代码保留，但不宣称端到端已验收。
- [MilvusManager](../../backend/vectordb/milvus_client.py) 用 query_iterator 遍历结果并关闭游标；插入失败不自动重放，避免不确定结果下重复写。

## 4. 数据库与任务状态

- DDL 由 [Go migrations](../../server/migrations/) 管理；显式 `dev.py migrate-go` 执行。已接管库的 Python 启动只读检查 schema_migrations，版本至少 3 且 clean，禁止重放旧建表链；未接管旧库仍沿用 Alembic。
- ai_executions 已由 [PostgresExecutionStore](../../backend/internal_api/postgres_executions.py) 读写；复用既有表与唯一约束。
- 并发幂等提交、租约、终态与过期更新受数据库事务保护；新进程可读取执行记录。
- **执行记录持久化不等于执行恢复**：后台任务仍为进程内执行，没有可靠消息投递、崩溃后续跑或全局调度。
- 文档任务可选内存/Redis；Redis 用 WATCH/MULTI 防丢更新，终态不可重开；仍非 PG 任务真相，不保证进程重启后继续执行。
- [table-acl](../../contracts/table-acl.md) 含目标表与规划权限，不能据它推断物理表或实际调用方存在。
- ORM 既有时间列沿用 naive UTC，新表使用 TIMESTAMPTZ；不能在未调查历史语义时直接转换。
- schema-baseline.json 是历史快照。当前库另行只读导出；--check-baseline 是形态检查，--verify-columns 比快照，--live 才连接当前库。

## 5. 安全与横切能力

- Go [ratelimit.go](../../server/internal/httpapi/ratelimit.go)：Redis 原子固定窗口，注册/登录独立限额，其余原生路由用配置限额；Redis 故障返回 503。
- 代理 IP 只有来自配置的可信 CIDR 才采信；项目所有 Uvicorn 启动入口禁用底层代理头改写，避免应用拿不到真实直连地址。Go/Python 均不能无条件信任客户端 X-Forwarded-For；限流使用项目 Redis 前缀隔离。
- [middleware.go](../../server/internal/httpapi/middleware.go) 保留流式刷新和连接升级，跨服务透传 trace_id。
- Python [logging_config.py](../../backend/core/logging_config.py) 注入请求 trace_id 并轮转日志；对外边界不返回内部异常原文。
- Markdown 经 DOMPurify 净化后渲染；引用、模型文本、检索文档仍视为不可信。

## 6. 前端状态

分层与约束见 [10](../rules/10-frontend-structure.md)，入口由 vue-router 管理。
readSse 检查终止事件、UTF-8/CRLF 与帧大小，释放 reader；旧请求通过 generation 隔离。
切换/新建会话取消活动请求；WebSocket 中断释放 loading；XHR 上传可取消并拒绝无效 JSON。
页面及样例可视化的存在不代表比较矩阵、研究实验室、自主科研等产品能力已经实现。

## 7. 复核命令与范围

```bash
uv run python scripts/check_route_ownership.py
uv run python scripts/check_contracts.py
uv run python scripts/verify_storage.py --http
uv run python -m pytest -q
```

verify_storage 使用隔离 PG 库与 Redis 测试键，--http 另起并清理真实 Go/Python 进程，覆盖认证/限流/会话；不调用外部 LLM/Milvus。
真实 RAG 验收另需 Milvus、模型服务、PDF 和对应 chain/e2e，跳过不算通过。

## 8. 维护方式

变更相关实现时同步本文；用文件与符号定位，不维护易失效行号。
运行数量、机器配置、历史排查过程只记 WORKLOG，不复制成规则。
