# PaperRAG

> 面向学术论文的 RAG 知识库平台 —— 专为排版复杂、含大量公式、逻辑严密的学术论文打造的深度检索增强生成系统。

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org)
[![Built with uv](https://img.shields.io/badge/built%20with-uv-6111fb.svg)](https://github.com/astral-sh/uv)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![LangChain](https://img.shields.io/badge/LangChain-0.2-green.svg)](https://github.com/langchain-ai/langchain)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![Milvus](https://img.shields.io/badge/VectorDB-Milvus-00b4d8.svg)](https://milvus.io)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791.svg)](https://www.postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7-ff4438.svg)](https://redis.io)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

---

## 目录

- [项目简介](#项目简介)
- [核心特性](#核心特性)
- [系统架构](#系统架构)
- [快速开始](#快速开始)
- [功能详解](#功能详解)
- [项目结构](#项目结构)
- [API 文档](#api-文档)
- [配置参考](#配置参考)
- [技术栈](#技术栈)
- [许可证](#许可证)

---

## 项目简介

**PaperRAG** 是一个面向学术研究场景（密码学、计算机科学、数学等）深度优化的 RAG（检索增强生成）知识库平台。它解决的核心问题是：**如何让大语言模型准确理解并回答关于学术论文内容的问题**。

学术论文相比普通文档有三大挑战：
- **排版复杂**：双栏布局、页眉页脚、参考文献块等干扰元素
- **公式密集**：LaTeX 数学公式的语义保留与渲染
- **逻辑严密**：定理-证明-推论之间的跨页关联

PaperRAG 通过多解析器降级链路、学术文本智能清洗、结构感知分块、定理/证明检测、HyDE 假设文档嵌入、双轨 Rerank 精排和上下文扩展等技术，系统性地解决了上述挑战。

### 运行形态

```
FastAPI 后端 + Vue 3 前端（Vite + TypeScript） + Milvus 向量数据库 + PostgreSQL + Redis
```

---

## 核心特性

### 检索增强

- **混合检索**：稠密向量（BGE-M3） + BM25 稀疏向量，Milvus Hybrid Search + RRF 融合排序
- **HyDE 假设文档嵌入**：LLM 生成假设性学术回答作为检索 Query，弥合自然语言与学术术语的语义鸿沟
- **双轨 Rerank 精排**：Jina API 远程精排 / BGE-Reranker-v2-M3 本地精排，按环境灵活切换
- **上下文扩展**：检索命中后自动拉取兄弟块与相邻父块，确保定理+证明完整召回
- **三级分块 + Auto-merging**：L1（结构父块）/ L2（语义子块）/ L3（叶子块），检索时自动合并
- **公式检索**：LaTeX 公式提取、标准化、专用 embedding，支持变体匹配

### 文档解析

- **四解析器自动降级链路**：OpenDataLoader → PyMuPDF → pdfplumber → PyPDF
- **学术文本智能清洗**：自动移除会议页眉页脚、页码、参考文献块、重复行
- **布局分析**：pdfplumber 页面布局分析，智能区分页眉/正文/标题/引用/图片/表格
- **公式提取**：LaTeX 公式提取与标准化，支持 $...$ 和 $$...$$ 格式
- **基于文档结构的父子分块**：按 Markdown 标题层级粗分 → 递归字符切分兜底
- **定理/证明检测**：正则识别 Theorem / Lemma / Proof / Definition 等关键结构

### 对话交互

- **流式输出**：SSE + ReadableStream 实现打字机效果
- **实时 RAG 过程可视化**：检索、评分、重写等步骤在前端实时展示
- **回答终止**：AbortController + 后端 CancelledError 实现确定性资源回收
- **会话摘要记忆**：长对话自动摘要压缩，维持上下文窗口可控
- **答案溯源**：Agent 回答中标注来源块，前端可点击引用跳转

### 多轮检索

- **LangGraph 循环边**：grade → rewrite → retrieve 循环最多 3 次
- **历史感知检索**：对话历史拼接到查询中，支持多轮追问
- **检查点**：支持检索中途失败时从断点继续

### 工程化

- **用户鉴权**：JWT 令牌 + RBAC 权限控制（admin / user 双角色）
- **密码强度校验**：最少8位 + 至少2/3类别（大小写/数字），可通过环境变量禁用
- **增量导入**：MD5 哈希追踪 PDF 变更，仅处理新增/修改文件
- **BM25 统计持久化**：词表+文档频次落盘，与向量库增量同步
- **两级语义缓存**：精确匹配 + 余弦相似度语义缓存（阈值可配）
- **异步任务管理**：上传/删除/批量导入均通过后台任务 + 进度轮询
- **结构化日志**：JSON 格式日志，支持 OpenTelemetry 链路追踪

### 多租户与限流

- **工作空间**：支持多团队协作，数据按工作空间隔离
- **API 限流**：基于 slowapi 的速率限制，防止滥用
- **用量统计**：记录每次 API 调用的延迟和状态码

### 学术增强

- **公式检索**：LaTeX 公式提取、标准化、专用 embedding，支持变体匹配
- **答案溯源**：Agent 回答中标注来源块，前端可点击跳转
- **布局分析**：pdfplumber 页面布局分析，智能区分页眉/正文/引用/图表
- **多模态支持**：CLIP 图像 embedding，为图表检索预留扩展

### CI/CD

- **GitHub Actions**：自动测试、lint、Docker 构建
- **Docker 多阶段构建**：Node 前端构建 + Python 运行时
- **生产部署**：docker-compose.prod.yml + nginx 反向代理

---

## 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│                  前端 (Vue 3 + Vite + TypeScript)              │
│   App.vue  │  ChatView.vue  │  RagTracePanel.vue  │ KaTeX   │
└──────────┬───────────────────────────────────────────────────┘
           │ POST /chat/stream (SSE)
           ▼
┌──────────────────────────────────────────────────────────────┐
│                     FastAPI 后端 (Uvicorn)                     │
│                                                              │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ routes  │  │  agent   │  │   RAG    │  │  embedding   │  │
│  │ (API)   │─▶│ (Lang-   │─▶│ pipeline │─▶│  (dense +     │  │
│  │ +限流   │  │  Graph)  │  │ (Lang-   │  │   sparse +    │  │
│  │ auth    │  │  tools   │  │  Graph)  │  │   CLIP)      │  │
│  │ sessions│  │ storage  │  │          │  └──────┬───────┘  │
│  │ docs    │  │ cache    │  │ rerank   │         │          │
│  │ workspace│  │         │  │ 公式检索  │         │          │
│  └─────────┘  └──────────┘  └──────────┘         │          │
└──────────────────────────────────────────────────┼───────────┘
                                                   │
        ┌──────────────────────────────────────────┼──────────┐
        │                     Data Layer           ▼          │
        │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
        │  │PostgreSQL│  │  Redis   │  │  Milvus (向量库)  │  │
        │  │ 会话消息  │  │ 热点缓存 │  │  Dense + Sparse  │  │
        │  │ 父级分块  │  │ 语义缓存 │  │  + Formula       │  │
        │  │ 用户数据  │  │          │  │  HNSW + BM25     │  │
        │  │ 工作空间  │  │          │  │                  │  │
        │  └──────────┘  └──────────┘  └──────────────────┘  │
        └────────────────────────────────────────────────────┘
```

### 核心流程

#### 端到端对话

1. 用户在前端输入问题 → `POST /chat/stream`（SSE 流式）
2. FastAPI 返回 `StreamingResponse(media_type="text/event-stream")`
3. LangChain Agent 根据问题类型路由：
   - 天气问题 → `get_current_weather`（高德地图 API）
   - 知识问答 → `search_knowledge_base`（RAG 流水线）
4. RAG 流水线分阶段执行，各步骤实时推送到前端
5. Agent 流式生成最终回答（含 LaTeX 公式渲染）
6. 消息持久化到 PostgreSQL，Redis 缓存加速回放

#### 文档入库

```
上传 PDF → MD5 去重检查 → 多解析器降级解析
  → 学术文本清洗 → 结构感知分块 → 定理检测标记
  → 父块写入 PostgreSQL → 叶子块向量化写入 Milvus
  → BM25 统计增量更新 → 更新 ingested.json
```

#### RAG 检索

```
语义缓存检查 (精确 + 余弦相似度)
  → HyDE 假设文档生成 (可选)
  → Hybrid 检索 (Dense + Sparse + RRF)
  → Rerank 精排 (Jina API / 本地 BGE-Reranker)
  → Auto-merging (L3→L2→L1)
  → 上下文扩展 (兄弟块 + 相邻父块)
  → 相关性评分门控 (structured output)
  → 查询重写 (Step-Back / HyDE) → 二次检索
  → 答案生成 + RAG Trace 追踪
```

---

## 快速开始

### 前置条件

- Python **3.12+**
- 包管理建议：[uv](https://github.com/astral-sh/uv)（也支持 `pip`）
- Docker / Docker Compose（用于启动 Milvus、PostgreSQL、Redis 等依赖）

### 安装依赖

```bash
# 方式 A：推荐 (uv)
uv sync

# 方式 B：pip
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U pip
pip install -e .
```

### 启动基础设施

```bash
docker compose up -d
```

启动以下服务：

| 服务 | 端口 | 说明 |
|------|------|------|
| PostgreSQL | 5432 | 会话历史、用户数据、父级分块 |
| Redis | 6379 | 热点缓存、语义缓存 |
| Milvus | 19530 | 向量存储与混合检索 |
| MinIO | 9000/9001 | Milvus 底层对象存储 |
| etcd | 2379 | Milvus 元数据管理 |
| Attu | 8080 | Milvus Web 管理界面 |

### 配置环境变量

复制模板并填写关键配置：

```bash
cp .env.example .env
```

**必填项：**

```env
# LLM 模型
ARK_API_KEY=your_api_key
MODEL=your_model_name
BASE_URL=https://your-llm-endpoint/v1

# 嵌入模型（默认 BAAI/bge-m3）
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DEVICE=cpu
```

完整配置项见 [配置参考](#配置参考) 和 `.env.example`。

### 启动应用

```bash
uv run uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
```

浏览器访问：
- 前端页面：**http://127.0.0.1:8000/**
- API 文档：**http://127.0.0.1:8000/docs**

---

## 功能详解

### 1. 多解析器 PDF 降级链路

采用四解析器自动降级策略，保证任何格式的学术论文 PDF 都能成功提取文本：

```
OpenDataLoader → PyMuPDF (fitz) → pdfplumber → PyPDFLoader
```

- 任一解析器失败时自动切换下一级
- 支持并行解析（`PARSE_MAX_WORKERS` 配置），充分利用多核 CPU

### 2. 学术文本智能清洗

自动检测并移除论文中的干扰内容：
- **页眉/页脚**：如 "EUROCRYPT 2025"、"Springer-Verlag"、"LNCS"
- **独立页码行**
- **参考文献引用块**：≥5 行连续引用 + DOI/卷/页码特征才删除，防止误删正文
- **重复行与版权声明**

### 3. 基于文档结构的父子分块

```
L1 (结构父块)     ┌──────────────────────┐
  ┌──────┤   Section 2. Prelim   ├──────┐
  │      └──────────────────────┘      │
  ▼                                     ▼
L2 (语义子块)  ┌── 2.1 Notation ──┐  ┌── 2.2 Definitions ──┐
               └──────────────────┘  └──────────────────────┘
                                      │
                                      ▼
L3 (叶子块)     ┌─── chunk ───┐ ┌─── chunk ───┐ ┌─── chunk ───┐
                └─────────────┘ └─────────────┘ └─────────────┘
```

- **粗拆分**：按 Markdown 标题层级（`#`、`##`、`###`）切分为语义完整的父块
- **精细拆分**：父块内部用 `RecursiveCharacterTextSplitter` 进一步切分为子块
- **元数据继承**：每个子块携带所属父块文本、章节路径、定理/证明标记
- **Leaf-only 向量化**：仅叶子分块写入 Milvus，父块写入 PostgreSQL，减少向量冗余

### 4. 定理与证明检测

两阶段正则匹配自动识别学术关键结构：

- **定理类**：`Theorem`、`Lemma`、`Corollary`、`Proposition`、`Definition`、`Claim`、`Conjecture`
- **证明类**：`Proof`、`Proof Sketch`、`Proof Overview`

检测结果作为元数据标记在父块上。检索时含定理/证明的父块在上下文扩展阶段获得更高优先级，确保完整推理链路不被截断。

### 5. HyDE（假设文档嵌入）

对于自然语言问题，先调用 LLM 生成一段假设性学术回答，再以此进行向量检索：

```
"什么是安全多方计算？"
  → LLM 生成："安全多方计算（Secure Multi-Party Computation, MPC）允许多个参与方..."
  → 用假设回答检索 → 命中更准确的论文片段
```

假设回答在措辞风格上更接近论文正文，能显著弥合"口语提问 ↔ 学术术语"之间的语义鸿沟。

### 6. 双轨 Rerank 精排

| 模式 | 模型 | 适用场景 |
|------|------|----------|
| **远程** | Jina Rerank API | 有稳定外网环境 |
| **本地** | BGE-Reranker-v2-M3 Cross-Encoder | 内网或离线环境 |

通过 `LOCAL_RERANKER=true` 切换本地模式。

### 7. 上下文扩展

检索命中的子块并非孤立返回，而是自动拉取：
- **同父兄弟块**：同一父块下的其他子块，保证语义完整性
- **相邻父块**：前一/后一父块（窗口可配置 `EXPAND_PREV_PARENT` / `EXPAND_NEXT_PARENT`）

含定理/证明标记的父块展开更激进，避免"定理在前一页、证明在后一页被切断"的问题。

### 8. 流式输出与实时 RAG 可视化

采用 **"Global Loop Capture + Threadsafe Callback"** 架构：

```python
# 核心机制 (tools.py)
def set_rag_step_queue(queue):
    _RAG_STEP_QUEUE = queue
    _RAG_STEP_LOOP = asyncio.get_running_loop()  # 主线程捕获 Loop

def emit_rag_step(icon, label):
    _RAG_STEP_LOOP.call_soon_threadsafe(          # 跨线程安全投递
        _RAG_STEP_QUEUE.put_nowait,
        {"icon": icon, "label": label}
    )
```

前端 SSE 事件流：

| 事件类型 | 说明 |
|----------|------|
| `content` | 文本 token（打字机效果，含 LaTeX） |
| `rag_step` | 实时检索步骤（`正在检查语义缓存...` → `正在检索知识库...` → ...） |
| `trace` | 完整 RAG 追踪信息（回答完成后发送） |
| `error` | 错误信息 |
| `[DONE]` | 流结束标记 |

### 9. 增量导入与哈希追踪

- 对每个 PDF 计算 MD5 哈希，记录于 `ingested.json`
- 再次导入时只处理新增或修改文件，未变动的跳过解析与向量化
- 删除文件自动从向量库中按文件维度清理

### 10. LaTeX 数学公式渲染

前端集成 **KaTeX**，支持行内 `$E = mc^2$` 与块级 `$$\sum_{i=1}^n$$` 即时渲染。Markdown 解析管道保护 LaTeX 代码块不被误解析，确保 `_`、`^`、`\{` 等字符原样保留。

---

## 项目结构

```
PaperRAG/
├── backend/
│   ├── app.py                  # FastAPI 入口、CORS、限流、静态资源挂载
│   ├── api/
│   │   └── routes.py           # 所有 HTTP 端点（auth、chat、sessions、documents、workspaces、stats）
│   ├── core/
│   │   ├── auth.py             # 注册登录、JWT 鉴权、权限校验、工作空间访问控制
│   │   ├── config.py           # 集中配置：所有常量、路径、模型参数
│   │   ├── database.py         # 数据库引擎与会话工厂
│   │   ├── dependencies.py     # 依赖注入容器（懒加载单例）
│   │   ├── logging_config.py   # 结构化日志配置
│   │   ├── models.py           # ORM 模型（User、ChatSession、ChatMessage、ParentChunk、Workspace、UsageLog）
│   │   └── rate_limit.py       # slowapi 限流配置
│   ├── rag/
│   │   ├── academic_cleaner.py    # 学术论文文本清洗 + 布局分析
│   │   ├── document_loader.py     # PDF 多解析器降级、结构分块、定理检测、公式提取
│   │   ├── embedding.py           # 稠密向量 + BM25 稀疏向量 + CLIP 图像 + 公式嵌入
│   │   ├── parent_chunk_store.py  # 父级分块存储（PostgreSQL + Redis）
│   │   ├── rag_pipeline.py        # LangGraph RAG 工作流（多轮检索 + 检查点）
│   │   ├── rag_utils.py           # 检索工具函数（HyDE、Rerank、上下文扩展）
│   │   └── theorem_detector.py    # 定理/证明正则检测
│   ├── schemas/
│   │   └── schemas.py           # Pydantic 请求/响应模型
│   ├── services/
│   │   ├── agent.py             # LangChain Agent、对话管理、答案溯源
│   │   ├── cache.py             # Redis 缓存 + 语义缓存
│   │   ├── tools.py             # 天气查询、知识库检索工具
│   │   └── upload_jobs.py       # 文档上传任务管理（Redis 持久化）
│   └── vectordb/
│       ├── milvus_client.py     # Milvus 集合管理、混合检索、公式检索
│       └── milvus_writer.py     # 向量写入（稠密+稀疏+公式）
├── frontend/
│   ├── src/
│   │   ├── main.ts              # Vite 入口
│   │   ├── App.vue              # 根组件（路由、认证、会话）
│   │   ├── components/
│   │   │   ├── ChatView.vue     # 对话界面（SSE 流式 + 引用跳转）
│   │   │   ├── RagTracePanel.vue # RAG 追踪面板
│   │   │   ├── Sidebar.vue      # 导航侧边栏
│   │   │   ├── AuthPanel.vue    # 登录/注册
│   │   │   ├── SettingsView.vue # 文档管理
│   │   │   └── HistorySidebar.vue # 历史会话
│   │   ├── composables/
│   │   │   ├── useAuth.ts       # JWT 管理
│   │   │   ├── useChat.ts       # SSE 流式 + 引用解析
│   │   │   ├── useDocuments.ts  # 文档上传/删除
│   │   │   └── useSessions.ts   # 会话 CRUD
│   │   └── services/
│   │       └── api.ts           # authFetch 封装
│   ├── package.json             # Vite + Vue 3 + TypeScript
│   └── vite.config.js           # Vite 配置
├── tests/
│   └── unit/                    # 94 个单元测试
│       ├── test_auth.py
│       ├── test_cache.py
│       ├── test_citations.py
│       ├── test_layout_analysis.py
│       ├── test_rate_limit.py
│       ├── test_tools.py
│       └── test_workspaces.py
├── data/                        # 运行时数据（gitignored）
│   ├── bm25_state.json          # BM25 统计持久化
│   ├── ingested.json            # 已导入论文 MD5 追踪
│   └── documents/               # 上传文档原文件
├── nginx/
│   └── nginx.conf               # 生产环境 nginx 配置
├── .github/
│   └── workflows/
│       └── ci.yml               # GitHub Actions CI/CD
├── pyproject.toml               # 项目元数据与依赖
├── Dockerfile                   # 多阶段构建（Node + Python）
├── docker-compose.yml           # 开发环境编排
├── docker-compose.prod.yml      # 生产环境编排
├── .env.example                 # 环境变量模板
├── .gitignore
└── README.md
```

---

## API 文档

### 鉴权

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/register` | 注册（支持普通用户/管理员邀请码） |
| POST | `/auth/login` | 登录，返回 Bearer Token |
| GET | `/auth/me` | 获取当前用户信息 |

### 对话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat` | 同步对话（非流式） |
| POST | `/chat/stream` | 流式对话（SSE，推荐） |

### 会话（用户隔离）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sessions` | 列出当前用户会话 |
| GET | `/sessions/{session_id}` | 拉取会话消息 |
| DELETE | `/sessions/{session_id}` | 删除会话 |

### 文档（管理员权限）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/documents` | 列出已入库文档 |
| POST | `/documents/upload` | 同步上传并向量化 |
| POST | `/documents/upload/async` | 异步上传（推荐） |
| GET | `/documents/upload/jobs` | 查询所有上传任务 |
| GET | `/documents/upload/jobs/{job_id}` | 查询单个任务进度 |
| POST | `/documents/ingest` | 增量导入目录中 PDF |
| DELETE | `/documents/{filename}` | 同步删除文档 |
| DELETE | `/documents/delete/async/{filename}` | 异步删除文档（推荐） |

### 缓存

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/cache/clear` | 清空所有缓存 |

### 工作空间（多租户）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/workspaces` | 创建工作空间 |
| GET | `/workspaces` | 列出用户的工作空间 |
| POST | `/workspaces/{id}/members` | 添加成员 |
| GET | `/workspaces/{id}/members` | 列出成员 |

### 用量统计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/stats/usage` | 当前用户用量统计 |

---

## 配置参考

完整配置请参见 `.env.example`。关键配置项分类如下：

### 模型

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ARK_API_KEY` | — | LLM API 密钥 |
| `MODEL` | — | 主模型名称 |
| `BASE_URL` | — | LLM 端点地址 |
| `GRADE_MODEL` | `gpt-4.1` | 评分模型 |
| `FAST_MODEL` | — | 快速模型 |

### 嵌入

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | 稠密向量模型 |
| `EMBEDDING_DEVICE` | `cpu` | 推理设备 |
| `DENSE_EMBEDDING_DIM` | `1024` | 向量维度 |

### Rerank

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RERANK_MODEL` | — | Rerank 模型名 |
| `RERANK_BINDING_HOST` | — | Rerank API 地址 |
| `LOCAL_RERANKER` | `false` | 切换本地 BGE-Reranker |

### 检索

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `COARSE_K` | `30` | 粗召回数 |
| `RERANK_TOP_N` | `5` | 精排保留数 |
| `AUTO_MERGE_THRESHOLD` | `2` | 自动合并阈值 |
| `ENABLE_HYDE` | `true` | 启用假设文档嵌入 |
| `EXPAND_PREV_PARENT` | `1` | 向前扩展父块数 |
| `EXPAND_NEXT_PARENT` | `1` | 向后扩展父块数 |

### 分块

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CHUNK_SIZE` | `800` | 分块大小（字符数） |
| `CHUNK_OVERLAP` | `100` | 分块重叠（字符数） |

### 鉴权

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `JWT_SECRET_KEY` | — | JWT 签名密钥 |
| `ADMIN_INVITE_CODE` | `paperrag-admin-2026` | 管理员邀请码 |
| `JWT_ALGORITHM` | `HS256` | JWT 算法 |
| `JWT_EXPIRE_MINUTES` | `1440` | Token 过期时间（分钟） |

---

## 技术栈

### 后端
- **框架**：FastAPI、Uvicorn
- **AI 框架**：LangChain Agents、LangGraph、Pydantic
- **数据库**：SQLAlchemy + PostgreSQL、Redis
- **向量库**：Milvus（HNSW 稠密索引 + SPARSE_INVERTED_INDEX 稀疏索引）
- **嵌入**：BAAI/bge-m3（本地稠密向量）+ 中英混合 BM25 稀疏向量
- **文档解析**：OpenDataLoader → PyMuPDF → pdfplumber → PyPDFLoader 四级降级

### 前端
- **框架**：Vue 3 (Vite + TypeScript + SFC)
- **状态管理**：Composables (useAuth, useChat, useDocuments, useSessions)
- **Markdown**：marked + highlight.js
- **公式渲染**：KaTeX（LaTeX）
- **图标**：Font Awesome
- **构建**：Vite 5.4, TypeScript 6.0

### 部署
- **容器编排**：Docker Compose（开发 + 生产）
- **CI/CD**：GitHub Actions（测试 + lint + Docker 构建）
- **反向代理**：nginx（gzip、缓存、WebSocket）
- **包管理**：uv / pip

---

## 许可证

[MIT](LICENSE)

---

> PaperRAG — 让每一篇论文都被准确理解。
