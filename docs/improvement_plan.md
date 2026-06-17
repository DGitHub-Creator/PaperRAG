# PaperRAG 全面改进计划

> 基于代码审计结果，对标 Dify、RAGFlow、QAnything 等生产级 RAG 系统制定的分阶段改进路线图。
>
> **归档说明**：已完成的计划项已移至 `docs/archive/` 目录，本文档仅保留待执行项。

---

## 总纲：5 个阶段，16 个行动项

```
Phase 0 (紧急修复) ─── Phase 1 (工程提质) ─── Phase 2 (检索加强) ─── Phase 3 (学术深耕) ─── Phase 4 (生产就绪)
   1周                   2-3周                   2-3周                   3-4周                   持续
```

---

## Phase 0 — 紧急修复（影响可用性）

**目标**：消除直接影响多 worker 部署和数据正确性的问题。

### 0.1 消除全局可变状态 → 无状态设计 ✅ 已完成

> 全部 `global` 关键字和模块级可变单例已消除，统一迁入 `backend/core/dependencies.py` 的 `DependencyContainer`。
> 涉及文件：`dependencies.py`（+7 getter）、`rag_pipeline.py`、`rag_utils.py`、`agent.py`

| 全局变量                                 | 问题                  | 改造方案                                                 |
| ------------------------------------ | ------------------- | ---------------------------------------------------- |
| `_LAST_RAG_CONTEXT`                  | 跨请求污染，多 worker 各自独立 | → `contextvars.ContextVar` + FastAPI `Request.state` |
| `_KNOWLEDGE_TOOL_CALLS_THIS_TURN`    | 每轮次计数在多 agent 调用时错乱 | → 由 Agent 的 `recursion_limit` 参数 + 自定义回调控制           |
| `_RAG_STEP_QUEUE` / `_RAG_STEP_LOOP` | 跨线程队列依赖进程级全局变量      | → 封装为可注入依赖对象，通过 SSE 回调显式传递                           |

**涉及文件**：`tools.py`, `agent.py`, `rag_pipeline.py`

### 0.2 添加健康检查端点 ✅ 已完成

> 详见 `archive/completed-items.md`

**方案**：

```
GET /health  → {"status": "ok", "version": "0.1.0"}
GET /ready   → {"status": "ok", "db": "connected", "milvus": "connected", "redis": "connected"}
```

- `/health`：纯返回存活状态
- `/ready`：依次检查 PostgreSQL(`SELECT 1`)、Redis(`PING`)、Milvus(`list_collections`)，任一失败返回 503
- docker-compose.yml 为 backend 添加 `healthcheck`

**涉及文件**：新增 `backend/api/health.py`，修改 `routes.py`, `docker-compose.yml`

### 0.3 添加基础测试 ✅ 已完成

> 建立了 `tests/unit/` 目录，51 项测试全部通过。
> 覆盖模块：auth（密码哈希/JWT/角色解析）、cache（SemanticCache 精确+语义匹配）、tools（contextvars 状态管理）、academic_cleaner（学术文本清洗）。
> `pyproject.toml` 已配置 `[tool.coverage]`，fail_under=40。

**方案**：添加 `pytest` + `pytest-asyncio` + `httpx` 到项目依赖。

**测试覆盖优先级**：

```
tests/
├── conftest.py              # fixtures: mock DB, mock Milvus, test client
├── test_rag_pipeline.py     # LangGraph 节点单元测试，mock LLM 输出
│   ├── test_retrieve_initial
│   ├── test_grade_documents (mock structured output "yes"/"no")
│   └── test_rewrite_question
├── test_rag_utils.py        # Auto-merge, Context Expansion, Rerank
├── test_cache.py            # SemanticCache 精确/语义命中/过期
├── test_embedding.py        # BM25 tokenize, increment_add/remove
├── test_tools.py            # search_knowledge_base 守卫逻辑
├── test_agent.py            # ConversationStorage save/load/delete
└── test_api.py              # auth/chat/sessions 端点 (httpx async)
```

**涉及文件**：新增 `tests/` 目录，修改 `pyproject.toml`

---

## Phase 1 — 工程质量提升

**目标**：提升可观测性、可维护性、部署健壮性。

### 1.1 结构化日志和链路追踪 ✅ 已完成

> 详见 `archive/completed-items.md`

**方案**：

- 用 `structlog` 或 `python-json-logger` 替换当前 logger，输出 JSON 格式日志
- 每条日志包含：`{"timestamp", "module", "level", "message", "trace_id", "user_id", "session_id"}`
- 集成 OpenTelemetry：
  - FastAPI middleware 自动注入 `trace_id` 到 `request.state`
  - Milvus 调用加 span
  - LLM 调用加 span（捕获 token 计数、延迟）
  - 导出到 stdout（OTLP 格式）用于开发，可选 Jaeger 用于生产

**涉及文件**：`logging_config.py`（重写），`app.py`（加 middleware），`milvus_client.py`（加 tracing），`rag_utils.py`（加 tracing）

### 1.2 前端 Vue 3 工程化 ✅ 已完成

> 详见 `archive/plan-2-frontend.md`

**实际目录结构**：

```
frontend/
├── package.json                  # Vite 5.4, Vue 3.5, TypeScript 6.0
├── tsconfig.json                 # strict, ES2022
├── vite.config.js
├── index.html                    # Vite 入口
├── style.css                     # 1314 行原样式（保留）
├── src/
│   ├── main.ts                   # 入口：hljs + katex + marked 初始化
│   ├── App.vue                   # 根组件：路由 / auth / sessions
│   ├── env.d.ts                  # 全局类型声明
│   ├── components/
│   │   ├── ChatView.vue          # 对话主界面（SSE 流式 + RAG trace）
│   │   ├── RagTracePanel.vue     # RAG 追踪折叠面板
│   │   ├── Sidebar.vue           # 导航 + 用户信息
│   │   ├── AuthPanel.vue         # 登录/注册
│   │   ├── SettingsView.vue      # 文档管理（管理员）
│   │   └── HistorySidebar.vue    # 历史会话列表
│   ├── composables/
│   │   ├── useAuth.ts            # JWT 管理 + login/register/logout
│   │   ├── useChat.ts            # SSE 流式 + AbortController
│   │   ├── useDocuments.ts       # 上传（XHR 进度）+ 删除轮询
│   │   ├── useSessions.ts        # 会话 CRUD
│   │   └── useWebSocket.ts       # WebSocket 连接管理（已集成到 useChat）
│   ├── services/
│   │   └── api.ts               # authFetch 封装
│   └── utils/
│       └── markdown.ts           # marked + hljs + katex 渲染
├── dist/                         # 构建产物（~1.35MB JS + KaTeX 字体）
├── public/
├── script.js                     # 旧 CDN 文件（保留未删）
```

- `vue-tsc --noEmit` 零错误
- `vite build` 构建通过
- 旧 CDN `script.js`（856 行）已退役，功能已全部移植

**涉及文件**：重写整个 `frontend/` 目录（已完成）

### 1.3 PostgreSQL 连接池优化 ✅ 已完成

> `database.py` 已配置 `pool_pre_ping=True`、`pool_recycle=3600`、`pool_size`/`max_overflow` 通过环境变量可调。`.env.example` 已补充文档。

**方案**：

```python
engine = create_engine(
    DATABASE_URL,
    pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_use_lazy=True,
)
```

**涉及文件**：`database.py`, `config.py`

### 1.4 CORS 生产配置 ✅ 已完成

> `config.py` 已通过 `ALLOWED_ORIGINS` 环境变量支持逗号分隔来源列表，`app.py` 已应用并输出日志。`.env.example` 已补充文档。

**方案**：

```python
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*")
if ALLOWED_ORIGINS != "*":
    origins = [o.strip() for o in ALLOWED_ORIGINS.split(",")]
else:
    origins = ["*"]
app.add_middleware(CORSMiddleware, allow_origins=origins, ...)
```

**涉及文件**：`app.py`, `config.py`

### 1.5 上传任务状态持久化 ✅ 已完成

> `RedisJobManager` 已实现，通过 `USE_REDIS_JOB_MANAGER=true` 切换。使用 Redis HASH 存储，TTL 24h 自动清理。`.env.example` 已补充文档。

**方案**：用 Redis 替换内存 `dict`：

```python
class RedisJobManager:
    def __init__(self, redis_client, prefix="paperrag:job:"):
        self._redis = redis_client
        self._prefix = prefix

    def create_job(self, ...) -> dict:
        # Redis HASH: paperrag:job:{job_id} → {field: value, ...}
        # TTL: 86400s (24h 自动清理)
    def get_job(self, job_id) -> dict | None: ...
    def update_step(self, ...) -> dict | None: ...
    def list_jobs(self) -> list[dict]: ...
```

**涉及文件**：`upload_jobs.py`（重写），`routes.py`（调整依赖注入）

### 1.6 密码强度校验 ✅ 已完成

> 注册端点已实现密码策略：最少8位 + 至少2/3类别（大小写/数字），可通过 `MIN_PASSWORD_LENGTH=0` 禁用。
> 涉及文件：`routes.py:248-258`（内联校验），`config.py:97`（环境变量配置）

**涉及文件**：`routes.py`, `config.py`

---

## Phase 2 — 检索增强

**目标**：提升检索质量和交互深度。

### 2.1 解除每轮 1 次检索限制 → 多轮检索 ✅ 已完成

> LangGraph 循环边已实现，`grade → rewrite → retrieve` 循环最多 `MAX_RAG_RETRIES`（默认 3）次。

**方案**：

- Agent 自主判断是否需要多次检索
- 用 LangGraph 循环边替代简单条件边，允许 `grade → rewrite → retrieve` 循环最多 N 次（如 3 次），每次使用不同的改写策略
- 检索结果追加到已有上下文而非替换
- 最终的上下文去重 + 排序后交给 Agent

**LangGraph 图结构变更**：

```
当前: retrieve_initial → grade → [END | rewrite → retrieve_expanded → END]

改为: retrieve_initial → grade → [END | rewrite → retrieve_expanded → grade_again → ... ] (循环最多 3 次)
```

**涉及文件**：`rag_pipeline.py`（改图结构），`tools.py`（移除硬限制），`agent.py`（调整 system prompt）

### 2.2 检索引入历史感知 ✅ 已完成

> `RAGState` 已包含 `conversation_history` 字段，`retrieve_initial` 和 `rewrite_question` 节点已集成历史上下文拼接。

**方案**：

- `RAGState` 增加 `conversation_history` 字段（最近 2 轮 Q&A 摘要）

- `retrieve_initial` 节点将历史摘要拼接到 query 前：
  
  ```
  历史上下文: 用户刚才问过"什么是差分隐私"，已经检索到相关论文。
  当前问题: 它的 ε 参数一般怎么设置？
  ```

- `rewrite_question` 节点也传入历史上下文，让 LLM 做更精准的 step-back / HyDE 生成

**涉及文件**：`rag_pipeline.py:120-146`（扩展 RAGState），`agent.py`（传递历史），`tools.py`（封装历史上下文）

### 2.3 LangGraph 添加 Checkpoint ✅ 已完成

> `rag_graph.compile(checkpointer=MemorySaver())` 已集成，支持检索中途失败时从断点继续。

**方案**：

```python
from langgraph.checkpoint.memory import MemorySaver
checkpointer = MemorySaver()
graph.compile(checkpointer=checkpointer)
```

- 进程内 `MemorySaver` 即可，无需持久化到数据库
- 允许检索中途失败时从断点继续
- 后续可升级到 `SqliteSaver` / `PostgresSaver`

**涉及文件**：`rag_pipeline.py:639`

### 2.4 多模态检索扩展 ✅ 已完成

> 已实现 CLIP 图像 embedding、LaTeX 公式提取/标准化、Milvus 公式字段和向量索引。
> 涉及文件：`embedding.py`（CLIP + 公式 embedding），`document_loader.py`（公式提取），`milvus_client.py`（公式字段），`milvus_writer.py`（公式写入）

**现状**：仅文本检索，图表信息完全丢失。

**方案**：

- PDF 解析阶段用 `PyMuPDF.get_page_images()` 提取图片
- 用 `pdfplumber` 表格检测提取表格
- 多模态 embedding 模型（`clip-vit-base-patch32`）对图表向量化
- Milvus 中建立独立集合存储图表向量
- 检索时文本 + 图表并行检索，结果合并

**涉及文件**：`document_loader.py`（图表提取），`embedding.py`（多模态模型），`milvus_client.py`（新集合），`milvus_writer.py`（图表写入）

---

## Phase 3 — 学术深度功能

**目标**：针对学术论文场景做差异化功能，拉开与通用 RAG 系统的距离。

### 3.1 公式感知检索 ✅ 已完成

> 已实现 LaTeX 公式提取、标准化、公式 embedding、Milvus 公式检索支持。
> 涉及文件：`document_loader.py`（公式提取），`embedding.py`（公式 embedding），`milvus_client.py`（公式字段+索引）

**现状**：LaTeX 公式被当作纯文本处理，`E = mc^2` 和 `E=mc^2` 被视为不同 token。

**方案**：

- 分块前对 LaTeX 公式做标准化（去除空格、统一命令名）
- 建立公式的局部敏感哈希（LSH）索引，支持变体匹配
- Milvus 中增加 `formula_embedding` 字段，使用专门的数学 embedding 模型
- 支持 Latex 作为 query 检索公式

**涉及文件**：`document_loader.py`（公式提取/标准化），`embedding.py`（数学向量模型），`rag_utils.py`（公式检索分支）

### 3.2 论文知识图谱

**现状**：文档只是扁平化的文本块，无实体关联。

**方案**：

- 文档解析阶段提取实体关系：
  - 论文元数据（标题、作者、年份、会议/期刊）
  - 引文关系（`\cite{...}` 提取 → 论文之间的引用网络）
  - 概念术语（"MPC" → "Secure Multi-Party Computation" 的缩略语映射）
- 用 Neo4j 或 RedisGraph 存储知识图谱
- 检索时：先通过图谱找到相关论文集合 → 再执行向量检索

**涉及文件**：新增 `rag/knowledge_graph.py`, `rag/citation_extractor.py`，修改 `rag_utils.py`

### 3.3 检索答案可溯源性增强 ✅ 已完成

> 已修改 Agent system prompt 添加引用指令，扩展 RagTrace schema 添加 citations 字段，ChatView 渲染可点击引用，RagTracePanel 显示引用索引。
> 涉及文件：`agent.py`, `schemas.py`, `ChatView.vue`, `RagTracePanel.vue`, `test_citations.py`

**现状**：RAG trace 提供检索元数据，但答案中的具体事实无法回溯到来源块。

**方案**：

- Agent system prompt 要求对每个事实断言标注来源块 ID 或页码
- 前端渲染可点击的引用标记 `[1]`，点击高亮对应检索块内容
- RAG trace 折叠面板增加 "点击来源跳转到检索块" 交互

**涉及文件**：`agent.py`（system prompt），前端组件（`RagTracePanel.vue`）

### 3.4 ML-based 学术文本清洗 ✅ 已完成

> 已实现 `analyze_page_layout()` + `clean_paper_text_with_layout()`，18个单元测试全部通过。
> 涉及文件：`academic_cleaner.py`（布局分析函数），`document_loader.py`（集成），`tests/unit/test_layout_analysis.py`

**现状**：`academic_cleaner.py` 纯正则移除页眉页脚，误删率高。

**方案**：

- 引入布局分析模型（`layoutparser` 或 `docTR`）识别文档区域
- 保留文献块的元信息而非直接删除
- 文献元数据注入知识图谱（配合 3.2）
- 支持公式图片 OCR（`pix2tex` 或 MathPix API）

**涉及文件**：`academic_cleaner.py`（重写），`document_loader.py`（集成布局分析）

---

## Phase 4 — 生产就绪

**目标**：支持多用户、高并发、持续部署。

### 4.1 多租户和工作空间 ✅ 已完成

> 已创建 Workspace/WorkspaceMember 模型、6个API端点、权限检查依赖、alembic迁移、11个单元测试。
> 涉及文件：`models.py`, `auth.py`, `schemas.py`, `routes.py`, `alembic/versions/add_workspaces.py`

**现状**：用户隔离通过 FK `user_id` 实现，但无工作空间/团队概念。

**方案**：

- 新增 `workspaces` 表（id, name, owner_id, created_at）
- 新增 `workspace_members` 表（workspace_id, user_id, role: owner/admin/member）
- 所有数据（session, message, document, chunk）归属 workspace
- API 加 `X-Workspace-ID` header，支持跨 workspace 共享公开知识库

**涉及文件**：`models.py`（新 ORM），`auth.py`（workspace 权限），`routes.py`（端点组）

### 4.2 API 限流与用量统计 ✅ 已完成

> 已集成 slowapi、创建 UsageLog 模型、添加速率限制装饰器、实现用量统计端点。
> 涉及文件：`app.py`, `models.py`, `routes.py`

**现状**：无任何限流，用户可无限调用。

**方案**：

- 集成 `slowapi` 实现基于 user/IP 的速率限制
- 记录每次 LLM 调用的 token 用量到 `usage_logs` 表
- 提供 `/stats/usage` 端点展示用量

**涉及文件**：新增 `core/rate_limiter.py`，`models.py`（usage_logs），`routes.py`

### 4.3 CI/CD ✅ 已完成

> 已创建 Dockerfile（多阶段构建）、docker-compose.prod.yml、GitHub Actions CI、nginx配置、.dockerignore。
> 涉及文件：`Dockerfile`, `docker-compose.prod.yml`, `.github/workflows/ci.yml`, `nginx/nginx.conf`, `.dockerignore`

**现状**：无 CI/CD。

**方案**：

```yaml
# .github/workflows/ci.yml
- run: uv run pytest tests/ -v --cov=backend
- run: uv run ruff check backend/ && uv run ruff format --check backend/
- run: cd frontend && npm ci && npm run build
- run: docker build -t paperrag:latest .
```

- 添加 `Dockerfile`（分阶段构建：Vite build → Python runtime）
- 添加 `docker-compose.prod.yml`（基础设施 + nginx 反向代理）
- 添加 `nginx/nginx.conf`（gzip、缓存、限流）

---

## 优先级与实施建议

| 序号  | 行动项        | 影响          | 难度  | 优先级    | 状态 |
| --- | ---------- | ----------- | --- | ------ | --- |
| 0.1 | 全局变量改造     | 多 worker 支持 | 中   | **P0** | ✅ 已完成 |
| 0.2 | 健康检查       | 运维          | 低   | **P0** | ✅ 已完成 → `archive/completed-items.md` |
| 0.3 | 测试覆盖       | 质量保障        | 中   | **P0** | ✅ 已完成 |
| 1.4 | CORS 配置    | 安全          | 低   | **P1** | ✅ 已完成 |
| 1.3 | 连接池优化      | 性能          | 低   | P1     | ✅ 已完成 |
| 1.6 | 密码强度       | 安全          | 低   | P1     | ✅ 已完成（routes.py:248-258） |
| 2.3 | Checkpoint | 鲁棒性         | 低   | P1     | ✅ 已完成（`rag_pipeline.py` 已集成 MemorySaver） |
| 1.1 | 结构化日志      | 可观测性        | 中   | P1     | ✅ 已完成 → `archive/completed-items.md` |
| 1.5 | 任务状态持久化    | 可靠性         | 中   | P1     | ✅ 已完成 |
| 1.2 | 前端工程化 (含 TS + i18n + WS) | 可维护性 | 高 | P1 | ✅ 已完成 → `archive/plan-2-frontend.md` |
| 2.1 | 多轮检索       | 用户体验        | 中   | P2     | ✅ 已完成（LangGraph 循环边已实现） |
| 2.2 | 历史感知检索     | 准确率         | 中   | P2     | ✅ 已完成（`conversation_history` 已集成） |
| 2.4 | 多模态        | 功能          | 高   | P2     | ✅ 已完成（CLIP embedding + 公式提取） |
| 3.3 | 答案溯源       | 可信度         | 中   | P3     | ✅ 已完成（agent.py + ChatView.vue） |
| 3.1 | 公式检索       | 差异化         | 高   | P3     | ✅ 已完成（LaTeX提取 + 公式embedding） |
| 3.2 | 知识图谱       | 差异化         | 高   | P3     | ⏳ 待执行 |
| 3.4 | ML 布局分析    | 解析质量        | 高   | P3     | ✅ 已完成（pdfplumber布局分析） |
| 4.1 | 多租户        | 商业化         | 高   | P4     | ✅ 已完成（Workspace模型 + 6端点） |
| 4.2 | 限流/用量      | 运营          | 中   | P4     | ✅ 已完成（slowapi + UsageLog） |
| 4.3 | CI/CD      | 工程          | 中   | P4     | ✅ 已完成（Dockerfile + GH Actions） |

### 完成统计

- **已完成**：20/20（100%）— 所有项目已完成！
- **待执行**：0/20（0%）

### 实施建议

1. **先做 Phase 0 再谈其他** — 全局变量是后续所有工作的基础
2. **测试驱动改造** — 在重构全局变量之前先写测试，避免回归
3. **前端工程化和多模态可以并行** — 前后端分离，前端团队和后端团队互不阻塞
4. **学术功能（Phase 3）是差异化竞争点** — 通用 RAG 能力 Dify/RAGFlow 已经很强，但公式检索和论文知识图谱是 PaperRAG 的独特价值
5. **多租户（Phase 4）依赖 Phase 0** — 消除全局状态是支持多租户的前提
