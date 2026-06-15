# PaperRAG — 面向学术论文的 RAG 知识库平台

面向学术研究场景（密码学、计算机科学等）进行深度优化的 RAG（检索增强生成）知识库平台。

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org) [![Built with uv](https://img.shields.io/badge/built%20with-uv-6111fb.svg)](https://github.com/astral-sh/uv) [![Framework-LangChain](https://img.shields.io/badge/framework-LangChain-green.svg)](https://github.com/langchain-ai/langchain) [![VectorDB-Milvus](https://img.shields.io/badge/VectorDB-Milvus-00b4d8.svg)](https://milvus.io)

---

## 项目概览

*   **核心定位**：专为排版复杂、含大量公式、逻辑严密的学术论文打造的现代化知识库平台。
*   **运行形态**：FastAPI 后端 + 前端（Vue 3 CDN 单页）+ Milvus 分布式向量库。
*   **四大核心能力**：
    *   **智能路由**：LangChain Agent + 自定义工具链，自主判定问答逻辑与检索路径。
    *   **高保真解析**：多解析器自动降级链路 + 学术级文本清洗，剔除无效干扰。
    *   **结构化分块**：基于 Markdown 标题层级的父子分块 + 定理/证明自适应检测。
    *   **深度检索增强**：混合检索（Dense + Sparse）+ 双轨 Rerank + HyDE（假设文档嵌入）+ 上下文动态扩展。

---

## 本地部署

### 1) 环境准备
- Python `3.12+`
- 包管理建议：`uv`（也支持 `pip`）
- Docker / Docker Compose（用于启动 Milvus 依赖）

### 2) 使用 pyproject 安装依赖
在项目根目录执行：

```bash
# 方式 A：推荐（uv）
uv sync

# 运行服务
uv run python backend/app.py
# 或
uv run uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
```

```bash
# 方式 B：pip
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .

# 运行服务
python backend/app.py
# 或
uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
```

### 3) 创建 `.env` 文件
在项目根目录新建 `.env`，可直接使用下面模板：

```env
# ===== Model =====
ARK_API_KEY=your_ark_api_key
MODEL=your_model_name
BASE_URL=https://your-llm-endpoint/v1

# ===== 本地稠密向量（langchain_huggingface，默认 BAAI/bge-m3）=====
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DEVICE=cpu
DENSE_EMBEDDING_DIM=1024

# ===== Rerank（支持 Jina API 或本地 BGE-Reranker）=====
RERANK_MODEL=BAAI/bge-reranker-v2-m3
RERANK_BINDING_HOST=https://your-rerank-host
RERANK_API_KEY=your_rerank_api_key
# 本地 Reranker 模式（与 API 二选一，设置后优先使用本地模型）
# LOCAL_RERANKER=true

# ===== Milvus =====
MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530
MILVUS_COLLECTION=embeddings_collection

# ===== Qdrant（可选替代 Milvus，适合单机轻量部署）=====
# QDRANT_URL=http://127.0.0.1:6333
# QDRANT_COLLECTION=academic_papers

# ===== Database / Cache =====
DATABASE_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/langchain_app
REDIS_URL=redis://127.0.0.1:6379/0

# ===== 语义缓存（可选）=====
ENABLE_CACHE=true
CACHE_MAX_SIZE=500
CACHE_TTL_SECONDS=604800
CACHE_SIM_THRESHOLD=0.92

# ===== Auth =====
JWT_SECRET_KEY=replace-with-strong-random-secret
ADMIN_INVITE_CODE=paperrag-admin-2026
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440
PASSWORD_PBKDF2_ROUNDS=310000

# ===== BM25 稀疏统计持久化（默认 data/bm25_state.json，可改路径）=====
# BM25_STATE_PATH=/path/to/bm25_state.json

# ===== 文档解析 =====
# 并行解析工作线程数（PDF 多解析器链路）
PARSE_MAX_WORKERS=4
# 论文文本清洗开关（移除页眉页脚、引用块等）
ENABLE_ACADEMIC_CLEANING=true

# ===== 分块参数 =====
CHUNK_SIZE=800
CHUNK_OVERLAP=100

# ===== 检索参数 =====
COARSE_K=30
RERANK_TOP_N=5
# Auto-merging 触发阈值（同级子块数 >= 此值则合并到父块）
AUTO_MERGE_THRESHOLD=2
# 上下文扩展参数（拉取相邻父块）
EXPAND_PREV_PARENT=1
EXPAND_NEXT_PARENT=1
EXPAND_MAX_TOTAL_CHUNKS=30

# ===== HyDE =====
ENABLE_HYDE=true

# ===== Tools（可选）=====
AMAP_WEATHER_API=https://restapi.amap.com/v3/weather/weatherInfo
AMAP_API_KEY=your_amap_api_key
```

### 4) Docker 部署（数据库 + 缓存 + 向量库）
当前仓库的 `docker-compose.yml` 同时承载业务依赖与 Milvus 依赖：
- 业务依赖：`postgres`、`redis`
- 向量依赖：`etcd`、`minio`、`standalone`、`attu`

```bash
# 启动所有依赖
docker compose up -d

# 查看服务状态
docker compose ps

# 查看日志（可选）
docker compose logs -f standalone
```

端口说明：
- PostgreSQL：`5432`
- Redis：`6379`
- Milvus：`19530`
- Milvus 健康检查：`9091`
- MinIO API：`9000`
- MinIO Console：`9001`
- Attu：`8080`

### 5) 启动应用并访问
在所有依赖启动后，运行后端应用：

```bash
uv run uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
```

浏览器访问：
- 前端页面：`http://127.0.0.1:8000/`
- API 文档：`http://127.0.0.1:8000/docs`

## 项目概览
- **核心定位**：面向学术论文（密码学、计算机科学、数学等）的 RAG 知识库平台。
- **核心能力**：
  - LangChain Agent + 自定义工具，智能路由问答与知识检索。
  - 学术 PDF 多解析器自动降级链路（OpenDataLoader → PyMuPDF → pdfplumber → PyPDF），保证不同格式论文的可解析性。
  - 论文文本智能清洗：自动移除会议页眉页脚、页码、参考文献块等干扰内容。
  - 基于文档结构的父子分块：先按 Markdown 标题层级粗分，再用递归字符切分兜底，保留论文章节上下文。
  - 定理/证明智能检测：正则识别论文中的 Theorem、Lemma、Proof、Definition 等关键结构，检索时优先保证完整召回。
  - 三级滑动窗口分块 + Auto-merging：叶子分块向量化写入 Milvus，父级分块写入 PostgreSQL。
  - HyDE（假设文档嵌入）：对学术问题生成假设性回答，以其向量检索真实论文片段，弥合自然语言提问与学术术语之间的语义鸿沟。
  - 上下文扩展（Context Expansion）：检索时自动拉取同级兄弟块与相邻父块，确保定理+证明完整返回。
  - 双轨 Rerank：支持 Jina API 远程精排与 BGE-Reranker-v2-M3 本地精排，可按环境灵活切换。
  - 用户注册/登录、JWT 鉴权、基于角色的 RBAC 权限控制（admin/user）。
  - 会话记忆与摘要，聊天与历史记录落地 PostgreSQL，并引入 Redis 缓存热点会话与父文档。
  - LaTeX 数学公式渲染：前端集成 KaTeX，支持行内 `$...$` 与块级 `$$...$$` 学术公式展示。
- **运行形态**：FastAPI 后端 + 纯前端（Vue 3 CDN 单页）+ Milvus 向量库。

## 学术论文特色功能

### 1. 多解析器 PDF 降级链路
- 采用四级解析器自动降级：**OpenDataLoader → PyMuPDF（fitz）→ pdfplumber → PyPDFLoader**。
- 任一解析器失败时自动切换下一级，保证排版复杂、双栏、含大量公式的论文 PDF 可成功提取文本。
- 支持并行解析（`PARSE_MAX_WORKERS`），批量论文导入时充分利用多核 CPU。

### 2. 学术文本智能清洗
- 自动检测并移除会议论文中的干扰内容：
  - 页眉/页脚（如 "EUROCRYPT 2025"、"Springer-Verlag"、"LNCS"）
  - 独立页码行
  - 参考文献引用块（需满足至少 5 行连续引用 + DOI/卷/页码特征才删除，防止误删正文）
  - 重复行与会议版权声明
- 清洗后的文本更纯净，显著提升分块质量与检索信号密度。

### 3. 基于文档结构的父子分块
- **粗拆分（结构感知）**：先按 Markdown 标题层级（`#`、`##`、`###`）将论文切分为语义完整的父块（Parent Block），每个父块对应论文章节或子章节。
- **精细拆分（语义兜底）**：父块内部用 `RecursiveCharacterTextSplitter` 按字数进一步切分为子块（Child Chunk），同时保留 `parent_content` 引用。
- **元数据继承**：每个子块携带所属父块的完整文本、章节路径、定理/证明标记，检索时可动态扩展上下文。

### 4. 定理与证明检测
- 两阶段正则匹配自动识别论文中的关键学术结构：
  - **定理类**：`Theorem`、`Lemma`、`Corollary`、`Proposition`、`Definition`、`Claim`、`Conjecture`
  - **证明类**：`Proof`、`Proof Sketch`、`Proof Overview`
- 检测结果作为元数据标记在父块上（`has_theorem_in_parent`、`has_proof_in_parent`）。
- 检索时，含定理/证明的父块在上下文扩展阶段获得更高优先级，确保完整推理链路不被截断。

### 5. HyDE（假设文档嵌入）
- 对于用户提出的自然语言问题，先调用 LLM 生成一段简短假设性学术回答。
- 使用假设回答（而非原始问题）进行向量检索——假设回答在措辞风格上更接近论文正文，能显著弥合"口语提问 ↔ 学术术语"之间的语义鸿沟。
- 若 HyDE 生成失败，自动降级为原始查询检索。

### 6. 上下文扩展（Context Expansion）
- 检索命中的子块并非孤立返回，而是自动拉取：
  - **同父兄弟块**：同一父块下的其他子块，保证语义完整性。
  - **相邻父块**：前一/后一父块（展开窗口可配置 `EXPAND_PREV_PARENT` / `EXPAND_NEXT_PARENT`），获取更广泛的论文章节上下文。
- 对于含定理/证明标记的父块，展开策略更加激进，避免"定理在前一页、证明在后一页被切断"的经典问题。
- 最终按 `(parent_idx, child_idx)` 排序后截断至 `EXPAND_MAX_TOTAL_CHUNKS`，定理块优先保留。

### 7. 双轨 Rerank 精排
- **远程模式**：Jina Rerank API，适合有稳定外网环境的场景。
- **本地模式**：`BAAI/bge-reranker-v2-m3` Cross-Encoder，适合内网或离线环境，通过 `LOCAL_RERANKER=true` 切换。
- 本地模式避免 API 调用延迟与成本，远程模式模型更新更及时——两者可灵活选择。

### 8. 增量导入与哈希追踪
- 对每个 PDF 计算 MD5 哈希，记录于 `ingested.json`。
- 再次导入时只处理新增或修改的论文，未变动的论文跳过解析与向量化，大幅提升批量更新效率。
- 删除的论文自动从向量库中按文件维度清理。

### 9. LaTeX 数学公式渲染
- 前端集成 **KaTeX**，支持行内公式 `$E = mc^2$` 与块级公式 `$$\sum_{i=1}^n$$` 即时渲染。
- Markdown 解析管道保护 LaTeX 代码块不被误解析，确保 `_`、`^`、`\{` 等字符原样保留。

## 关键创新点
- **混合检索落地**：稠密向量 + BM25 稀疏向量，Milvus Hybrid Search + RRF 排序，兼顾语义与词匹配。
- **结构感知分块**：基于 Markdown 标题层级的文档结构分块 + 递归字符切分兜底，保留论文语义单元不被截断。
- **定理/证明检测**：正则识别学术论文关键结构，检索时优先保证定理+证明完整召回。
- **HyDE 学术检索增强**：LLM 生成假设性回答作为检索 Query，弥合自然语言与学术文本之间的语义鸿沟。
- **上下文扩展**：检索命中后自动拉取兄弟块与相邻父块，解决"定理与证明跨页截断"问题。
- **学术文本清洗**：自动移除会议页眉、页码、参考文献块等干扰内容，提高分块纯净度。
- **双轨 Rerank**：Jina API 远程精排 + BGE-Reranker-v2-M3 本地精排，适应不同网络环境；支持返回 `rerank_score` 并在前端可视化。
- **双向降级**：稀疏生成或 Hybrid 调用失败时自动降级为纯稠密检索；HyDE 生成失败时自动降级为原始查询，提升稳定性。
- **流式输出（Streaming）**：后端基于 `agent.astream(stream_mode="messages")` 逐 token 推送，前端 SSE + ReadableStream 实现打字机效果。
- **实时 RAG 过程可视化**：检索过程在模型"思考中"阶段就开始展示，通过 `asyncio.Queue` + 后台任务架构实现工具执行期间的实时推送。
- **回答终止功能**：前端 `AbortController` + 后端 `StreamingResponse` 支持用户随时中断正在生成的回答。
- **会话摘要记忆**：自动摘要旧消息并注入系统提示，维持上下文且控制 token。
- **文档处理链路**：多解析器降级解析 → 学术清洗 → 结构分块 → 稠密/稀疏向量同步生成 → Milvus 入库，支持增量导入与重复上传自动清理。
- **BM25 统计持久化**：`词表 + 文档频次 df + 文档数 N` 落盘到 `data/bm25_state.json`，入库时增量增加、删除/覆盖上传前按文件名从 Milvus 拉取 chunk 文本后增量扣减，与向量库同步；`embedding_service` 在 API 与检索模块间单例共享。
- **三级分块 + Auto-merging**：L1（结构父块）/L2（语义子块）/L3（叶子块）三层切分；检索时优先召回 L3，满足阈值后自动合并到父块（L3→L2→L1）。
- **Leaf-only 向量化存储**：仅叶子分块写入 Milvus，父块写入 DocStore，减少向量冗余并保留上下文聚合能力。
- **两级语义缓存**：精确匹配 + 余弦相似度语义缓存（阈值 0.92），可选对接 Redis 实现跨进程共享。
- **工具可扩展**：天气查询示例 + 知识库检索，便于按需增添第三方 API 或企业数据源。
- **RAG 过程可观测**：记录检索、评分、重写与来源信息，前端可展开查看每一步细节。
- **查询重写体系**：Step-Back 与 HyDE 两种扩展方式 + 路由选择，必要时触发重写检索。
- **相关性评分门控**：基于结构化输出的 `grade_documents` 判断是否需要重写检索。
- **实时思考链路展示**：通过 `asyncio` 事件循环穿透技术，实现 Agent 在执行 RAG、评分、重写等同步工具时，实时向前端推送思考步骤（Searching → Grading → Rewriting），彻底解决"静默思考"问题。
- **增量导入**：MD5 哈希追踪 PDF 变更状态，仅处理新增/修改论文，大幅提升批量导入效率。


## 目录与架构

```
PaperRAG/
├── backend/
│   ├── app.py              # FastAPI 入口、CORS、静态资源挂载
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py       # 所有 HTTP 端点（auth、chat、sessions、documents）
│   ├── core/
│   │   ├── __init__.py
│   │   ├── auth.py         # 注册登录、JWT 鉴权、权限检查、密码哈希与校验
│   │   ├── config.py       # 集中配置：所有常量、路径、模型参数
│   │   ├── database.py     # 数据库引擎与会话工厂、建表入口
│   │   ├── logging_config.py # 统一日志配置
│   │   └── models.py       # ORM 模型定义（User、ChatSession、ChatMessage、ParentChunk）
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── academic_cleaner.py  # 学术论文文本清洗
│   │   ├── document_loader.py   # PDF 多解析器降级、结构分块、定理检测集成
│   │   ├── embedding.py         # 本地稠密向量 + BM25 稀疏向量；统计持久化与增量更新
│   │   ├── parent_chunk_store.py # 父级分块仓储（PostgreSQL + Redis）
│   │   ├── rag_pipeline.py      # LangGraph RAG 工作流（检索-评分-重写-扩展）
│   │   ├── rag_utils.py         # 检索工具函数（HyDE、混合检索、Rerank、上下文扩展）
│   │   └── theorem_detector.py  # 定理/证明/定义的正则检测与元数据标记
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── schemas.py     # Pydantic 请求/响应模型
│   ├── services/
│   │   ├── __init__.py
│   │   ├── agent.py       # LangChain Agent、对话管理、同步/流式对话
│   │   ├── cache.py       # Redis JSON 缓存 + 语义相似度缓存
│   │   ├── tools.py       # 天气查询、知识库检索工具
│   │   └── upload_jobs.py # 文档上传任务管理与进度追踪
│   └── vectordb/
│       ├── __init__.py
│       ├── milvus_client.py  # Milvus 集合管理、混合检索、分页查询
│       └── milvus_writer.py  # 向量写入（稠密+稀疏）
├── frontend/
│   ├── index.html          # Vue 3 SPA 结构
│   ├── script.js           # 聊天、历史、文档管理、SSE 处理
│   └── style.css           # 全局样式
├── data/                   # 运行时数据（gitignored）
│   ├── bm25_state.json     # BM25 词表与统计
│   ├── ingested.json       # 已导入论文的 MD5 哈希追踪
│   └── documents/          # 上传文档原文件
├── main.py                 # 旧版入口（已废弃，保留做参考）
├── pyproject.toml          # 项目依赖与元数据
├── docker-compose.yml      # PostgreSQL + Redis + Milvus + MinIO + etcd + Attu
└── README.md
```

## 核心流程

### 1) 项目全链路（端到端）
1. 用户在前端输入问题，调用 `POST /chat/stream`（流式）。
2. FastAPI `routes.py` 返回 `StreamingResponse(media_type="text/event-stream")`。
3. LangChain Agent 根据问题类型决定是否调用工具：
  - 天气问题 → `get_current_weather`
  - 知识问答 → `search_knowledge_base`
4. 若命中知识库工具，进入 `rag_pipeline.py` 执行检索工作流，各阶段通过 `emit_rag_step()` 实时推送到前端。
5. 检索结果与 RAG Trace 一起返回，Agent 流式生成最终回答（逐 token 推送，含 LaTeX 公式）。
6. 前端 ReadableStream 逐块解析 SSE，KaTeX 即时渲染数学公式，打字机效果实时展示。
7. 同时消息持久化到 PostgreSQL，并通过 Redis 缓存加速历史会话回放。

### 2) 文档入库链路（学术论文增强版）
1. 前端上传 PDF 到 `POST /documents/upload` 或 `POST /documents/upload/async`。
2. **MD5 去重检查**：计算文件哈希，若 `ingested.json` 中已存在且未变化则跳过。
3. **多解析器降级解析**：OpenDataLoader → PyMuPDF → pdfplumber → PyPDF，任一成功即停止。
4. **学术文本清洗**：移除页眉页脚、页码、引用块、重复行。
5. **结构分块**：先按 Markdown 标题层级粗分为父块（L1），再用 `RecursiveCharacterTextSplitter` 细分为子块（L2/L3），同时标记定理/证明元数据。
6. 若同名文件已存在：先从 Milvus 分页查询旧 chunk 文本，同步扣减 BM25 统计，再删除旧向量与父块缓存。
7. L1/L2 父级分块写入 `parent_chunk_store.py`（PostgreSQL + Redis 缓存）。
8. L3 叶子分块在 `milvus_writer.py` 中先生成 Dense 与 Sparse 向量，再 increment_add BM25 统计，最后写入 Milvus。
9. 更新 `ingested.json` 记录本次导入。

### 3) RAG 全链路（学术增强版）
1. **语义缓存检查**：精确匹配 + 查询嵌入余弦相似度缓存（相似度阈值 0.92），命中直接返回。
2. **HyDE（可选）**：LLM 生成假设性学术回答，以此作为检索 Query 弥合语义鸿沟。
3. **初次召回**：`retrieve_initial`
  - 调用 `retrieve_documents`，对 HyDE 生成文本执行 Milvus Hybrid 检索（Dense + Sparse + RRF）。
  - 取更大候选集（`candidate_k = top_k * 3`）后走 Rerank 精排（Jina API 或本地 BGE-Reranker-v2-M3）。
  - Auto-merging（L3→L2→L1），父块从 DocStore 读取。
4. **上下文扩展**：对 rerank 后的每个命中块，拉取同父兄弟块 + 相邻父块，按章节坐标排序；含定理/证明的块优先保留。
5. **相关性打分门控**：`grade_documents`
  - 使用结构化输出打分 `yes/no`。
  - `yes` 直接进入生成回答；`no` 进入重写阶段。
6. **查询重写路由**：`rewrite_question`
  - 在 `step_back / hyde / complex` 中选择策略。
7. **二次召回**：`retrieve_expanded`
  - 对重写后的查询再次检索 + Auto-merging + 上下文扩展。
8. **答案生成**：Agent 结合上下文生成最终回答（含 LaTeX 公式、引用来源标注）。
9. **可观测追踪**：返回 `rag_trace`，包括评分结果、重写策略、检索结果、定理命中标记、来源章节路径等。

### 4) BM25 状态文件（`data/bm25_state.json`）
- **内容**：`version`、全局 `total_docs`（chunk 篇数）、`sum_token_len`、`vocab`（词 → 稀疏维度下标）、`doc_freq`（词 → 文档频次，用于 IDF）。`vocab` 与 `doc_freq` 职责不同：前者定 Milvus 稀疏向量维度，后者定 BM25 统计。
- **增量**：每入库一批叶子 chunk 增加统计；删除文档或覆盖上传前按文件名扣减。词表下标不回收，避免与历史稀疏向量维度冲突。
- **注意**：`data/` 默认被 `.gitignore` 忽略，状态文件通常不落库；若 Milvus 已有数据但状态文件缺失，需清空重导或自行重建统计。

### 5) 会话记忆链路
1. 每轮问答按当前登录用户 + `session_id` 写入 PostgreSQL。
2. 当消息过长时触发摘要压缩，保留长期上下文。
3. Redis 缓存会话列表与会话消息，减少高频读取数据库压力。
4. 前端可通过会话接口读取、删除当前用户自己的历史对话。

## 技术栈
- **后端**：FastAPI、LangChain Agents / LangGraph、Pydantic、Uvicorn、SQLAlchemy、PostgreSQL、Redis。
- **向量与检索**：Milvus（HNSW 稠密索引 + SPARSE_INVERTED_INDEX 稀疏索引）、RRF 融合；可选 Qdrant（COSINE 距离）用于单机轻量部署。
- **Rerank 双轨**：Jina Rerank API（远程） / BGE-Reranker-v2-M3 Cross-Encoder（本地）。
- **嵌入与稀疏**：`langchain_huggingface` 本地稠密向量（默认 `BAAI/bge-m3`）；中英混合规则分词 + BM25 手写稀疏向量，统计持久化至 `bm25_state.json`。
- **文档解析**：OpenDataLoader → PyMuPDF（fitz）→ pdfplumber → PyPDFLoader 四级降级链路。
- **前端**：Vue 3 (CDN)、marked、highlight.js、KaTeX（LaTeX 渲染）、纯静态部署。
- **工具链**：dotenv 配置、requests、langchain_text_splitters、langchain_community.loaders。

## 环境变量
需在仓库根目录或运行环境配置：
- 模型相关：`ARK_API_KEY`、`MODEL`、`BASE_URL`
- 稠密向量：`EMBEDDING_MODEL`、`EMBEDDING_DEVICE`、`DENSE_EMBEDDING_DIM`（需与 Milvus 集合 `dense_embedding` 维度一致）
- BM25 持久化：`BM25_STATE_PATH`（可选，默认 `data/bm25_state.json`）
- Rerank 相关：`RERANK_MODEL`、`RERANK_BINDING_HOST`、`RERANK_API_KEY`、`LOCAL_RERANKER`
- Milvus：`MILVUS_HOST`、`MILVUS_PORT`、`MILVUS_COLLECTION`
- Qdrant（可选）：`QDRANT_URL`、`QDRANT_COLLECTION`
- 数据库缓存：`DATABASE_URL`、`REDIS_URL`
- 语义缓存：`ENABLE_CACHE`、`CACHE_MAX_SIZE`、`CACHE_TTL_SECONDS`、`CACHE_SIM_THRESHOLD`
- 鉴权相关：`JWT_SECRET_KEY`、`ADMIN_INVITE_CODE`、`JWT_ALGORITHM`、`JWT_EXPIRE_MINUTES`
- 密码参数：`PASSWORD_PBKDF2_ROUNDS`
- 文档解析：`PARSE_MAX_WORKERS`、`ENABLE_ACADEMIC_CLEANING`
- 分块参数：`CHUNK_SIZE`、`CHUNK_OVERLAP`
- 检索参数：`COARSE_K`、`RERANK_TOP_N`
- Auto-merging：`AUTO_MERGE_ENABLED`、`AUTO_MERGE_THRESHOLD`、`LEAF_RETRIEVE_LEVEL`
- 上下文扩展：`EXPAND_PREV_PARENT`、`EXPAND_NEXT_PARENT`、`EXPAND_MAX_TOTAL_CHUNKS`
- HyDE：`ENABLE_HYDE`
- 工具：`AMAP_WEATHER_API`、`AMAP_API_KEY`

## API 速览
- **鉴权**
  - `POST /auth/register`：注册（支持普通用户/管理员邀请码模式）。
  - `POST /auth/login`：登录，返回 Bearer Token。
  - `GET /auth/me`：获取当前登录用户信息。
- **聊天**
  - `POST /chat`：聊天（非流式），入参 `message`、`session_id`。
  - `POST /chat/stream`：聊天（流式 SSE），入参同上，返回 `text/event-stream`。
- **会话（用户隔离）**
  - `GET /sessions`：列出当前用户会话。
  - `GET /sessions/{session_id}`：拉取当前用户某会话消息。
  - `DELETE /sessions/{session_id}`：删除当前用户会话。
- **文档（管理员权限）**
  - `GET /documents`：列出已入库文档及 chunk 数。
  - `POST /documents/upload`：上传并向量化 PDF/Word/Excel（自动执行多解析器降级 + 学术清洗 + 结构分块）。
  - `POST /documents/upload/async`：异步上传，返回任务 ID 供进度查询。
  - `GET /documents/upload/jobs`：查询所有上传任务状态与进度。
  - `GET /documents/upload/jobs/{job_id}`：查询单个上传任务进度。
  - `POST /documents/ingest`：增量导入指定目录中的 PDF，仅处理新增/修改文件。
  - `DELETE /documents/{filename}`：删除指定文档向量数据（同步扣减 BM25 统计与 `ingested.json` 记录）。
- **缓存**
  - `POST /cache/clear`：清空所有 Redis 缓存。

## 流式输出与实时检索过程 — 技术细节

### 1. 跨线程事件调度（Cross-Thread Event Scheduling）
这是一个解决 **"同步工具阻塞异步事件循环"** 问题的关键架构设计，常用于 Python 异步 Web 服务与 CPU 密集型/IO 密集型任务的混合场景。

**痛点**：
FastAPI 运行在单线程的 asyncio Event Loop 上。为了不阻塞主线程，LangChain 通常将同步工具（如 `search_knowledge_base`）放到 `ThreadPoolExecutor` 中运行。但在子线程中，无法直接访问主线程的 `asyncio.Queue`，且 `asyncio.get_event_loop()` 通常会失败。

**解决方案**：
采用 **"Global Loop Capture + Threadsafe Callback"** 模式：

1. **Loop 捕获 (Main Thread)**：在 Agent 开始生成前，主线程调用 `set_rag_step_queue()` 捕获当前运行循环并保存为全局变量。
2. **跨线程发射 (Worker Thread)**：当 RAG 工具在子线程运行时，调用 `emit_rag_step()`，函数内部使用 `call_soon_threadsafe` 将数据安全投递到主 Loop。
3. **原理**：`call_soon_threadsafe` 是 asyncio 唯一允许从其他线程向 Loop 注入回调的方法，主 Loop 在下一次 tick 立即执行。

```python
# 核心代码摘要 (tools.py)
def set_rag_step_queue(queue):
    global _RAG_STEP_QUEUE, _RAG_STEP_LOOP
    _RAG_STEP_QUEUE = queue
    _RAG_STEP_LOOP = asyncio.get_running_loop()  # 在主线程捕获 Loop

def emit_rag_step(icon, label):
    if _RAG_STEP_LOOP and not _RAG_STEP_LOOP.is_closed():
        _RAG_STEP_LOOP.call_soon_threadsafe(
            _RAG_STEP_QUEUE.put_nowait,
            {"icon": icon, "label": label}
        )
```

### 2. 混合检索（Hybrid Search）深度实现
- **Dense Pathway**：使用 `langchain_huggingface.HuggingFaceEmbeddings`（默认 `BAAI/bge-m3`）生成稠密向量，维度由 `DENSE_EMBEDDING_DIM` 与集合 schema 对齐（默认 1024）。
- **Sparse Pathway**：在 `embedding.py` 中基于中英混合规则分词实现 BM25，生成 `{稀疏维度下标: BM25 分数}`，写入 Milvus `SPARSE_FLOAT_VECTOR`。全局统计持久化在 `bm25_state.json`。
- **Milvus 融合**：使用 `AnnSearchRequest` 同时发起两个请求，**RRFRanker** 采用 `k=60` 倒数排名融合算法合并两路召回结果。

### 3. HyDE 与上下文扩展的协同
- **HyDE 先生成后检索**：LLM 生成的假设性回答在风格上贴近论文正文，作为检索 Query 比原始口语问题更准确。
- **检索后上下文扩展**：命中子块自动展开，拉取同父兄弟块 + 相邻父块，按章节坐标排序后截断。
- **定理优先策略**：含定理/证明标记的父块在展开阶段获得更高优先级，确保形式化定义与证明完整返回。

### 4. 前端 "Thinking State Machine"
前端 `script.js` 维护了一个微型状态机来处理通过 SSE 传回的复杂混合流：

1. **Idle**：等待用户输入。
2. **Thinking (Initial)**：收到请求，创建消息气泡，`isThinking=true`，显示默认动画。
3. **Thinking (Active RAG)**：收到 `type: rag_step` 事件，动态更新 Header 文字，向 `ragSteps` 数组追加步骤。
4. **Streaming**：收到第一个 `type: content` 事件，立即切换 `isThinking=false`，隐藏思考 header，在同一气泡内追加 Markdown 文本。

## 整体架构

```
用户发送消息
    │
    ▼
POST /chat/stream → StreamingResponse(text/event-stream)
    │
    ▼
chat_with_agent_stream()
    │
    ├── 创建统一输出队列 (asyncio.Queue)
    ├── 设置 _RagStepProxy → emit_rag_step() 的输出直接入队
    ├── 启动 _agent_worker 后台任务 (asyncio.create_task)
    │     └── agent.astream(stream_mode="messages") 逐 token 产出
    │           ├── AIMessageChunk (文本) → {"type": "content"} 入队
    │           └── tool_call_chunks (工具调用) → 跳过
    │
    └── 主循环：await output_queue.get() → yield SSE
          ▲
          │ (并发) RAG 工具在线程池中执行
          │   ├── 语义缓存检查
          │   ├── HyDE 生成（可选）
          │   ├── Hybrid 检索（Dense + Sparse + RRF）
          │   ├── Rerank（Jina API 或本地 BGE-Reranker）
          │   ├── Auto-merging + 上下文扩展
          │   ├── Grade Documents（相关性评分）
          │   ├── Query Rewrite（Step-Back / HyDE）
          │   └── Retrieve Expanded（二次召回）
          │
          │ emit_rag_step() → loop.call_soon_threadsafe → 入队
          │ {"type": "rag_step"} 立即从队列取出并推送到前端
```

### 后端实现

#### 1) 流式生成 (`agent.py`)
- 使用 LangGraph `agent.astream(stream_mode="messages")` 获取逐 token 的 `AIMessageChunk`。
- 过滤 `tool_call_chunks`，只转发文本内容给前端。
- Agent 流式循环运行在 `asyncio.create_task` 后台任务中，主生成器从统一 `output_queue` 取事件并 yield。

#### 2) 实时 RAG 步骤推送 (`tools.py` + `rag_pipeline.py`)
- `emit_rag_step(icon, label, detail)` 通过 `call_soon_threadsafe()` 将步骤从同步线程安全地推送到异步队列。
- `_RagStepProxy` 代理对象将原始 step dict 包装后放入统一输出队列。
- `rag_pipeline.py` 在每个关键节点发射步骤：
  - `check_cache` → "正在检查语义缓存..."
  - `hyde_generate` → "正在生成假设文档..."
  - `retrieve_initial` → "正在检索知识库..."
  - `context_expand` → "正在扩展上下文（兄弟块+相邻父块）..."
  - `grade_documents` → "正在评估文档相关性..."
  - `rewrite_question` → "正在重写查询..."
  - `retrieve_expanded` → "使用扩展查询重新检索..."

#### 3) SSE 协议格式
每个事件格式：`data: {JSON}\n\n`，类型字段：
- `content`：文本 token（打字机效果，含 LaTeX）
- `rag_step`：实时检索步骤（`{icon, label, detail}`）
- `trace`：完整 RAG 追踪信息（回答完成后发送）
- `error`：错误信息
- `[DONE]`：流结束标记

#### 4) StreamingResponse 配置 (`routes.py`)
```python
StreamingResponse(
    event_generator(),
    media_type="text/event-stream",
    headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
    },
)
```

### 前端实现

#### 1) ReadableStream 解析 (`script.js`)
- 使用 `response.body.getReader()` + `TextDecoder` 逐块读取。
- 手动按 `\n\n` 分割 SSE 事件，解析 `data: ` 前缀后的 JSON。
- `content` 事件追加到消息文本；`rag_step` 事件追加到检索步骤数组。

#### 2) 思考气泡二合一
- 发送消息后立即创建带 `isThinking: true` 的气泡。
- 收到第一个 `content` token 时，`isThinking = false`，同一气泡无缝切换为正常文本流。

#### 3) LaTeX 数学公式渲染
- 前端集成 KaTeX CDN，自动检测 `$...$`（行内）和 `$$...$$`（块级）语法即时渲染。

### 终止功能

#### 前端
- 发送按钮在 `isLoading` 期间切换为红色终止按钮。
- 点击调用 `AbortController.abort()`，捕获 `AbortError` 在气泡中显示"(已终止回答)"。

#### 后端
- 客户端断开连接时，Python 生成器协议抛出 `GeneratorExit` 异常。
- 显式捕获 `GeneratorExit` 并执行 `agent_task.cancel()`，实现确定性资源回收。
- `agent_task.cancel()` 在任务挂起点注入 `CancelledError`，触发 `httpx` 关闭 TCP 连接，服务端停止推理，真正节省 Token。

## 未来迭代（Todo Lists）

### RAG部分

#### 数据层、Chunk分块
1. 先做文档结构解析，按文档结构做粗拆分，再用递归字符分块兜底，保证打的主题单元不被拆分 --done
2. 代码块、表格、图片特殊处理
3. 实现 ParentDocument/Auto-merging Retriever 策略 --done
4. 定理/证明检测与检索优先级 --done
5. 学术论文文本清洗 --done

#### 召回层
1. BM25的k1和b新增参数扫描
2. RRF额外做BM25和dense的权重，可以通过AB test确定
3. 做一个小型标注集比较dense only、sparse only、hybrid、hybrid + rerank的gold chunk
4. 本地 Reranker 与 Jina API Reranker 的精度/延迟对比评估

#### 生成层
1. 子问题分解（CoT、专门的分解小模型、判断分几个子问题）
2. 多文档Refine（一次拼接、串行Refine）
3. 多文档冲突处理（A文档说X，B文档说非X），回答中显式输出"来源存在冲突"
4. 跨论文学术主张对比（如"方案A假设随机预言机，方案B基于标准模型"）

#### 学术专项
1. 论文元数据自动提取（标题、作者、会议/期刊、年份）
2. 参考文献图谱构建与引用链追溯
3. 跨语言论文检索（中英双语对齐）
4. 数学公式语义理解与检索

#### 其他
1. 向量嵌入：新增多模态 embedding 能力
2. 搭建 RAG 评估体系（基于学术论文标注集）
3. Rerank 策略评估（top_k、candidate_k、召回/精排比例）
4. 增量导入性能优化（大文件批量场景）

### 其他能力拓展
1. 开发 SQL assistant Skill
2. 实现暂停功能与人工介入机制 --done
3. 新增问题类型判断，简单问题跳过复杂处理流程
4. 扩展网络搜索能力（arXiv、Google Scholar 等学术源）
5. 支持多步骤规划与任务并行执行
6. 搭建路由器节点，由 LLM 自主判断下一步动作
7. 优化 memory 管理：集成 MemO、LangMem 等方案
8. multi-agent：工具过多，把工具拆分给职责明确的专业化agent，提升工具选择的准确性和整体稳定性
9. 历史记录会话名称可修改
10. 死循环检测与恢复：`_is_stuck + attempt_loop_recovery`

### 后端服务建设（已完成）
1. 账号体系与权限体系
- 新增注册登录接口：`/auth/register`、`/auth/login`。
- 新增用户信息接口：`/auth/me`。
- 引入 JWT 鉴权中间能力：请求通过 Bearer Token 识别当前用户。
- 权限隔离：
  - `admin`：可执行文档上传、删除、文档列表查询。
  - `user`：仅可聊天、查询和删除自己的会话历史。
2. 数据库建模与持久化迁移
- 使用 SQLAlchemy 建立核心模型：`User`、`ChatSession`、`ChatMessage`、`ParentChunk`。
- 聊天历史由本地 JSON 迁移到 PostgreSQL。
- 父级分块文档（L1/L2）由本地 JSON 迁移到 PostgreSQL。
3. Redis 缓存策略
- 会话消息缓存：按 `user + session` 维度缓存消息列表。
- 会话列表缓存：按 `user` 维度缓存会话摘要列表。
- 父文档缓存：按 `chunk_id` 缓存父级分块内容。
- 语义缓存（新增）：按查询嵌入余弦相似度缓存问答对。
- 写入/删除后执行缓存失效，保证一致性。
4. 密码安全与兼容
- 新注册用户采用 PBKDF2-SHA256 存储密码哈希（避免 bcrypt 后端兼容问题）。
- 登录校验兼容历史 bcrypt 哈希，支持平滑迁移。