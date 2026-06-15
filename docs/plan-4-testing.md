# Plan 4 — 测试体系完善（⏳ 待执行）

> 目标：从 27 个测试覆盖关键模块，到覆盖率 > 60%，并集成 CI。

---

## 现状

| 测试文件 | 测试数 | 覆盖模块 |
|----------|--------|----------|
| `test_cache.py` | 10 | `SemanticCache` |
| `test_embedding.py` | 7 | `EmbeddingService.BM25` |
| `test_health.py` | 2 | `/health`、`/ready` |
| `test_rag_pipeline.py` | 8 | `grade_documents`、`rewrite_question`、`retrieve_expanded` |

**未覆盖的核心模块**：认证（auth）、路由端点（routes）、RAG 工具（rag_utils）、Agent（agent）、文档加载（document_loader）、Milvus 写入（milvus_writer）。

**问题**：
- `tests/` 目录被 `.gitignore` 排除
- 部分测试依赖真实基础设施（DB/Milvus）
- 无覆盖率门禁

---

## 4.1 测试目录治理（P0）

| # | 动作 | 状态 |
|---|------|------|
| 1 | 从 `.gitignore` 移除 `tests/` | ⏳ |
| 2 | 创建 `tests/unit/` | ⏳ |
| 3 | 创建 `tests/integration/` | ⏳ |

## 4.2 认证模块测试（P1）

计划 13 个测试覆盖 `get_password_hash`、`verify_password`、`create_access_token`、`get_current_user`、`require_admin`。

| # | 文件 | 状态 |
|---|------|------|
| 1 | `tests/unit/test_auth.py` | ⏳ |

## 4.3 API 端点测试（P1）

计划 ~22 个测试覆盖所有端点。

| # | 文件 | 状态 |
|---|------|------|
| 1 | `tests/integration/test_api.py` | ⏳ |

## 4.4 RAG 工具函数测试（P1）

计划 ~10 个测试覆盖 rerank、auto-merge、context expansion、step-back。

| # | 文件 | 状态 |
|---|------|------|
| 1 | `tests/unit/test_rag_utils.py` | ⏳ |

## 4.5 Agent 模块测试（P1）

计划 ~7 个测试覆盖 ConversationStorage 和 create_agent。

| # | 文件 | 状态 |
|---|------|------|
| 1 | `tests/unit/test_agent.py` | ⏳ |

## 4.6 文档加载测试（P2）

计划 ~4 个测试。

| # | 文件 | 状态 |
|---|------|------|
| 1 | `tests/unit/test_document_loader.py` | ⏳ |

## 4.7 覆盖率门禁（P1）

| # | 动作 | 状态 |
|---|------|------|
| 1 | `pyproject.toml` 配置 `[tool.coverage]` | ⏳ |
| 2 | CI 步骤 `pytest --cov --cov-fail-under=60` | ⏳ |

## 相关改动

Plan 1.2 单例治理已更新测试 mock 路径（`conftest.py`）：
- `mock_embedding_service`: 改为 patch `backend.core.dependencies.get_embedding_service`
- `mock_milvus_manager`: 改为 patch `backend.core.dependencies.get_milvus_manager`
- `mock_parent_chunk_store`: 改为 patch `backend.core.dependencies.get_parent_chunk_store`
