# Plan 5 — 学术深度功能（🏗️ 进行中）

> 目标：实现公式感知检索、论文知识图谱、ML 布局分析、多模态检索四个差异化功能。

---

## 5.1 公式感知检索（P2）✅

| # | 动作 | 状态 |
|---|------|------|
| 1 | 公式提取 (`document_loader.py`) | ✅ |
| 2 | 公式标准化 (`rag/formula_normalizer.py`) | ✅ |
| 3 | LSH 索引 (`rag/formula_index.py`) | ✅ |
| 4 | Milvus 动态字段（`enable_dynamic_field` 已启用，无需额外字段） | ✅ |
| 5 | 检索分支 (`rag_utils.py`) — `_formula_search` + `_build_formula_index` | ✅ |
| 6 | 单元测试 — `test_formula_normalizer.py` (17)、`test_formula_index.py` (9) | ✅ |

**实现内容**：
- `formula_normalizer.py`: LaTeX 公式标准化（空白、指令大小写、分数简化、根号简化、变量通用化）、公式提取、Jaccard 相似度
- `formula_index.py`: MinHash LSH 索引（添加、查询、删除、清空、全局单例）
- `document_loader.py`: `_split_structural` 和 `_split_standard` 中提取公式并写入 `has_formula`/`formulas` 元数据
- `rag_utils.py`: `_formula_search()` 提取查询中 LaTeX → LSH 匹配 → Milvus 精确查询；`_build_formula_index()` 入库后构建索引；`retrieve_documents()` 中融合公式与文本结果

## 5.2 论文知识图谱（P2–P3）✅

| # | 动作 | 状态 |
|---|------|------|
| 1 | 引文提取 (`rag/citation_extractor.py`) — 支持 5 种引文格式 | ✅ |
| 2 | 缩略语映射 (`rag/glossary_extractor.py`) — Definition(ABBR) + ABBR: Definition | ✅ |
| 3 | 论文元数据提取 — document_loader 集成 `has_citation`/`citations`/`has_glossary`/`glossary_terms` | ✅ |
| 4 | 图存储表（PaperNode, CitationEdge, GlossaryEntry）— models.py 新增 | ✅ |
| 5 | 图谱检索集成 — `_citation_boost` 在 `retrieve_documents` 中提级引文匹配 chunk | ✅ |
| 6 | 单元测试 — `test_citation_extractor.py` (13)、`test_glossary_extractor.py` (8) | ✅ |

**实现内容**：
- `citation_extractor.py`: 5 种引文格式（`[1]`, `[Author, Year]`, `(Author, Year)`, `Author (Year)`, `\cite{label}`）+ 数字引用提取
- `glossary_extractor.py`: `"Definition (ABBR)"` 和 `"ABBR: Definition"` 两种模式，自动去重
- `models.py`: 新增 `PaperNode`, `CitationEdge`, `GlossaryEntry` 三个 ORM 表
- `document_loader.py`: `_split_structural` 和 `_split_standard` 提取引文/缩略语写入 chunk 元数据
- `rag_utils.py`: `_citation_boost()` 在检索结果中提升引用相关 chunk 优先级

## 5.3 ML 布局分析（P3）✅

| # | 动作 | 状态 |
|---|------|------|
| 1 | `layoutparser` 集成 (`rag/layout_analyzer.py`) — PubLayNet/PRImA 双模型 | ✅ |
| 2 | 集成到 document_loader 可选检测图表/表格区域 | ✅ |
| 3 | 图表/表格区块提取（`extract_regions_by_type` 筛选） | ✅ |
| 4 | 单元测试 — `test_layout_analyzer.py` (6) | ✅ |

**实现内容**：
- `layout_analyzer.py`: layoutparser 封装（懒加载 + 降级），支持 PubLayNet 和 PRImA 模型
- `document_loader.py`: `_load_pdf` 末尾可选执行 ML 布局分析，标记 `has_figure`/`has_table` 到 chunk 元数据

## 5.4 多模态检索（P3）✅

| # | 动作 | 状态 |
|---|------|------|
| 1 | FigureExtractor 从 PDF 提取图片（PyMuPDF 双策略） | ✅ |
| 2 | CLIP 多模态 Embedding（sentence-transformers 懒加载） | ✅ |
| 3 | Milvus `figure_embeddings` 集合（HNSW 索引） | ✅ |
| 4 | 并行文本+图表检索（`search_by_text` + `index_figures`） | ✅ |
| 5 | 单元测试 — `test_multimodal.py` (12) | ✅ |

**实现内容**：
- `multimodal.py`: FigureExtractor（内嵌图片 + 页面截图提取）、MultimodalEmbedding（CLIP 文本/图片统一向量空间，降级返回占位向量）、MultimodalRetriever（独立 Milvus 集合管理，`search_by_text`/`index_figures` 接口，全局单例）
- 所有组件懒加载 + 降级：依赖不可用时返回空结果

## 5.5 答案可溯源增强（P2）✅

| # | 动作 | 状态 |
|---|------|------|
| 1 | Agent prompt 标注事实来源 | ✅ |
| 2 | 前端渲染可点击引用标记（返回 `source_map` 供前端使用） | ✅ |

**实现内容**：
- `agent.py`：system prompt 增加来源引用指令（要求 LLM 使用 `[Source N](filename, page P)` 格式标注每个事实的来源）
- `tools.py`：`search_knowledge_base` 改为使用 `[Source N]` 格式编号，并保存 `source_map`（N → filename/page/chunk_id）
- `agent.py` 同步/流式接口：`source_map` 随 `rag_trace` 一起返回（REST 响应和 SSE 事件均包含）

## 前置依赖

| Module | 依赖 |
|--------|------|
| `formula_normalizer.py` | 无外部依赖 |
| `formula_index.py` | `formula_normalizer` |
| `document_loader.py` 公式提取 | `formula_normalizer.extract_formulas` |
| `rag_utils.py` 公式检索 | `formula_normalizer` + `formula_index` + `milvus_manager` |
| 知识图谱 | `backend/core/models.py` 新 ORM 表 |
| 多模态 | CLIP (sentence-transformers) + Milvus 新集合 |
| Plan 1.2 | `dependencies.py` 单例容器 |
| Plan 1.3 | `get_chat_model()` |
