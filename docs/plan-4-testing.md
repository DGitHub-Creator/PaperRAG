# Plan 4 — 测试体系完善（部分完成）

> 目标：从 51 个测试覆盖核心模块，逐步提升到覆盖率 > 60%。

---

## 现状

| 测试文件 | 测试数 | 覆盖模块 |
|----------|--------|----------|
| `tests/unit/test_auth.py` | 16 | `auth`（密码哈希/JWT/角色解析） |
| `tests/unit/test_cache.py` | 15 | `SemanticCache`（精确+语义匹配） |
| `tests/unit/test_tools.py` | 7 | `tools`（contextvars 状态管理） |
| `tests/unit/test_academic_cleaner.py` | 13 | `academic_cleaner`（学术文本清洗） |
| **合计** | **51** | |

**未覆盖的核心模块**：路由端点（routes）、RAG 工具函数（rag_utils）、Agent（agent）、文档加载（document_loader）、Milvus 写入（milvus_writer）。

---

## 4.1 测试目录治理（P0）✅

| # | 动作 | 状态 |
|---|------|------|
| 1 | 从 `.gitignore` 移除 `tests/` | ✅ |
| 2 | 创建 `tests/unit/` | ✅ |
| 3 | 创建 `tests/integration/` | ✅ |

## 4.2 认证模块测试（P1）✅

16 个测试覆盖 `get_password_hash`、`verify_password`、`create_access_token`、`resolve_role`。

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

## 4.7 覆盖率门禁（P1）✅

| # | 动作 | 状态 |
|---|------|------|
| 1 | `pyproject.toml` 配置 `[tool.coverage]` | ✅ `fail_under=40` |
| 2 | CI 步骤 `pytest --cov --cov-fail-under=60` | ⏳ 待 Plan 3 CI/CD 实施 |

## 相关改动

Plan 1.2 单例治理已更新测试 mock 路径（`conftest.py`）：
- `mock_embedding_service`: 改为 patch `backend.core.dependencies.get_embedding_service`
- `mock_milvus_manager`: 改为 patch `backend.core.dependencies.get_milvus_manager`
- `mock_parent_chunk_store`: 改为 patch `backend.core.dependencies.get_parent_chunk_store`
