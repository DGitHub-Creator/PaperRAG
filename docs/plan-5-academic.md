# Plan 5 — 学术深度功能（⏳ 待执行）

> 目标：实现公式感知检索、论文知识图谱、ML 布局分析、多模态检索四个差异化功能。

---

## 5.1 公式感知检索（P2）

| # | 动作 | 状态 |
|---|------|------|
| 1 | 公式提取 (`document_loader.py`) | ⏳ |
| 2 | 公式标准化 (`rag/formula_normalizer.py`) | ⏳ |
| 3 | LSH 索引 (`rag/formula_index.py`) | ⏳ |
| 4 | Milvus `formula_embedding` 字段 | ⏳ |
| 5 | 检索分支 (`rag_utils.py`) | ⏳ |

## 5.2 论文知识图谱（P2–P3）

| # | 动作 | 状态 |
|---|------|------|
| 1 | 引文提取 (`rag/citation_extractor.py`) | ⏳ |
| 2 | 缩略语映射 (`rag/glossary_extractor.py`) | ⏳ |
| 3 | 论文元数据提取 | ⏳ |
| 4 | 图存储表（PaperNode, CitationEdge, GlossaryEntry） | ⏳ |
| 5 | 图谱检索集成 | ⏳ |

## 5.3 ML 布局分析（P3）

| # | 动作 | 状态 |
|---|------|------|
| 1 | `layoutparser` 集成 | ⏳ |
| 2 | 替换正则清理逻辑 | ⏳ |
| 3 | 图表/表格/公式图片提取 | ⏳ |

## 5.4 多模态检索（P3）

| # | 动作 | 状态 |
|---|------|------|
| 1 | 图表提取 (`document_loader.py`) | ⏳ |
| 2 | CLIP 多模态 Embedding | ⏳ |
| 3 | Milvus `figure_embeddings` 集合 | ⏳ |
| 4 | 并行文本+图表检索 | ⏳ |

## 5.5 答案可溯源增强（P2）

| # | 动作 | 状态 |
|---|------|------|
| 1 | Agent prompt 标注事实来源 | ⏳ |
| 2 | 前端渲染可点击引用标记 | ⏳ |

## 前置依赖

- Plan 1.2 已完成（`dependencies.py` 单例容器为后续新增模块提供注册机制）
- Plan 1.3 已完成（`get_chat_model()` 可在新模块中直接使用）
