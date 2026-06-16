# Plan 1 — 架构层治理 ✅ 已完成（归档）

> 完成时间：2026-05
> 全部 27 项测试通过，无回归。

---

## 1.1 Alembic 数据库迁移（P0）✅

**实际变更**：

| # | 动作 | 实际结果 |
|---|------|----------|
| 1 | 安装 Alembic，加入 `pyproject.toml` | ✅ `alembic>=1.18.0` 已添加 |
| 2 | 初始化迁移仓库 | ✅ `alembic init alembic` → `alembic/` 目录 |
| 3 | 配置 `alembic.ini` | ✅ 通过 `env.py:config.set_main_option("sqlalchemy.url", DATABASE_URL)` 注入 |
| 4 | 修改 `env.py` | ✅ 导入 `Base.metadata`，设为 `target_metadata` |
| 5 | 生成初始迁移 | ✅ 手动编写，覆盖 4 张表 |
| 6 | 修改 `database.py` | ✅ `init_db()` 优先运行 `alembic upgrade head`，fallback 到 `create_all` |

---

## 1.2 模块级单例治理（P1）✅

**实际变更**：

| # | 动作 | 实际结果 |
|---|------|----------|
| 1 | 新增 `core/dependencies.py` | ✅ `DependencyContainer` 类：double-checked locking + threading.Lock |
| 2 | 迁移 `embedding_service` | ✅ 改为 `get_embedding_service()` |
| 3 | 迁移 `rag_graph` | ✅ 改为 `get_rag_graph()` |
| 4 | 迁移 `_milvus_manager` / `_parent_chunk_store` | ✅ 改用 `get_milvus_manager()` / `get_parent_chunk_store()` |
| 5 | 增加重置 API | ✅ `dependencies.reset_all()` 方法 |

---

## 1.3 LLM Provider 抽象（P1）✅

**实际变更**：

| # | 动作 | 实际结果 |
|---|------|----------|
| 1 | `config.py` 新增统一配置 | ✅ `LLM_PROVIDER`、`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`、`LLM_GRADE_MODEL` |
| 2 | 新增 `core/llm.py` | ✅ `get_chat_model(role)`：据 role 选择模型和温度 |
| 3 | 保留旧变量作为 fallback | ✅ `LLM_API_KEY = os.getenv("LLM_API_KEY", "") or ARK_API_KEY` 等 |
| 4 | 修改引用方 | ✅ `agent.py`、`rag_utils.py`、`rag_pipeline.py` 全部改为 `get_chat_model(role)` |

---

## 1.4 WebSocket 替代 SSE（P2）✅

**实际变更**：

| # | 动作 | 实际结果 |
|---|------|----------|
| 1 | 新增 `backend/api/ws.py` | ✅ `/ws/chat` 端点（JWT 通过 `?token=` 参数传递） |
| 2 | FastAPI 依赖注入 | ✅ `get_user_from_ws_token()` 验证 JWT |
| 3 | Agent 流式接口适配 | ✅ WebSocket 端点消费 `chat_with_agent_stream` 输出并转发为 JSON 事件 |

---

## 涉及文件

- 新增：`alembic/`、`alembic.ini`、`backend/core/dependencies.py`、`backend/core/llm.py`、`backend/api/ws.py`
- 修改：`pyproject.toml`、`backend/core/database.py`、`backend/core/config.py`、`embedding.py`、`rag_pipeline.py`、`rag_utils.py`、`routes.py`、`milvus_writer.py`、`agent.py`、`.env.example`、`backend/app.py`
