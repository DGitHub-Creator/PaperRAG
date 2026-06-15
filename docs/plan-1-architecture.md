# Plan 1 — 架构层治理 ✅ 已完成

> 目标：解决数据库迁移、模块级单例、LLM Provider 硬编码、WebSocket 四个架构问题。
> 全部 27 项测试通过，无回归。

---

## 1.1 Alembic 数据库迁移（P0）✅

**现状**：`database.py:init_db()` 使用 `Base.metadata.create_all(bind=engine)`，生产环境无法回滚，字段变更需手动写 DDL。

**实际变更**：

| # | 动作 | 实际结果 |
|---|------|----------|
| 1 | 安装 Alembic，加入 `pyproject.toml` | ✅ `alembic>=1.18.0` 已添加 |
| 2 | 初始化迁移仓库 | ✅ `alembic init alembic` → `alembic/` 目录 |
| 3 | 配置 `alembic.ini` | ✅ 通过 `env.py:config.set_main_option("sqlalchemy.url", DATABASE_URL)` 注入（而非 ini 占位符） |
| 4 | 修改 `env.py` | ✅ 导入 `Base.metadata`，设为 `target_metadata` |
| 5 | 生成初始迁移 | ✅ 手动编写（autogenerate 需要 PostgreSQL 运行中），覆盖 4 张表 |
| 6 | 修改 `database.py` | ✅ `init_db()` 优先运行 `alembic upgrade head`，成功则 return |
| 7 | 保持兜底 | ✅ `alembic upgrade head` 失败 → fallback 到 `Base.metadata.create_all` |
| 8 | CI 步骤 | ⏳ 待 Plan 3 CI/CD 实施时添加 `alembic check` |

**涉及文件**：
- 新增：`alembic/`、`alembic.ini`、`alembic/versions/21f6caf0b15b_init.py`
- 修改：`pyproject.toml`、`backend/core/database.py`

---

## 1.2 模块级单例治理（P1）✅

**现状**：4 个模块级单例在 import 时立即初始化。

**实际变更**：

| # | 动作 | 实际结果 |
|---|------|----------|
| 1 | 新增 `core/dependencies.py` | ✅ `DependencyContainer` 类：double-checked locking + threading.Lock |
| 2 | 迁移 `embedding_service` | ✅ 从 `embedding.py` 模块级移除，改为 `get_embedding_service()` |
| 3 | 迁移 `rag_graph` | ✅ 移除 `rag_pipeline.py` 模块级实例，`run_rag_graph()` 内部调用 `get_rag_graph()` |
| 4 | 迁移 `_milvus_manager` / `_parent_chunk_store` | ✅ `rag_utils.py` 移除模块级实例，改用 `get_milvus_manager()` / `get_parent_chunk_store()` |
| 5 | 修改引用方 | ✅ `routes.py`（28 处引用）、`milvus_writer.py`、`conftest.py` 全部更新 |
| 6 | 增加重置 API | ✅ `dependencies.reset_all()` 方法 |

**涉及文件**：
- 新增：`backend/core/dependencies.py`
- 修改：`embedding.py`、`rag_pipeline.py`、`rag_utils.py`、`routes.py`、`milvus_writer.py`、`conftest.py`

---

## 1.3 LLM Provider 抽象（P1）✅

**现状**：所有 `init_chat_model(model_provider="openai", ...)` 硬编码。

**实际变更**：

| # | 动作 | 实际结果 |
|---|------|----------|
| 1 | `config.py` 新增统一配置 | ✅ `LLM_PROVIDER`、`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`、`LLM_GRADE_MODEL` |
| 2 | 新增 `core/llm.py` | ✅ `get_chat_model(role)`：`role="grade"` 用 `LLM_GRADE_MODEL`，其他用 `LLM_MODEL`，据 role 选择温度 |
| 3 | 保留旧变量作为 fallback | ✅ `LLM_API_KEY = os.getenv("LLM_API_KEY", "") or ARK_API_KEY` 等 |
| 4 | 修改引用方 | ✅ `agent.py`、`rag_utils.py`、`rag_pipeline.py` 全部改为 `get_chat_model(role)` |
| 5 | 更新 `.env.example` | ✅ 添加 `LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_GRADE_MODEL` 注释 |

**注意**：`get_chat_model` 不返回 None（与旧 `init_chat_model` 行为一致），当模型名或 API Key 缺失时返回 `ConfigurableModel`（延迟到调用时解析）。

**涉及文件**：
- 新增：`backend/core/llm.py`
- 修改：`config.py`、`rag_pipeline.py`、`rag_utils.py`、`agent.py`、`.env.example`

---

## 1.4 WebSocket 替代 SSE（P2）✅

**现状**：SSE 单向推送，前端无法打断正在执行的检索。

**实际变更**：

| # | 动作 | 实际结果 |
|---|------|----------|
| 1 | 新增 `backend/api/ws.py` | ✅ `/ws/chat` 端点（JWT 通过 `?token=` 参数传递） |
| 2 | FastAPI 依赖注入 | ✅ `get_user_from_ws_token()` 验证 JWT，无效时 `WS_1008_POLICY_VIOLATION` |
| 3 | Agent 流式接口适配 | ✅ WebSocket 端点消费 `chat_with_agent_stream` 输出并转发为 JSON 事件 |
| 4 | 前端 WebSocket 支持 | ⏳ 待 Plan 2 前端开发时添加 |
| 5 | 上传进度推送 | ⏳ 待后续迭代 |

**消息协议**：
```
客户端 → 服务端: {"message": "...", "session_id": "..."}
服务端 → 客户端: {"type": "content", "content": "..."}
                 {"type": "rag_step", "step": {...}}
                 {"type": "trace", "rag_trace": {...}}
                 {"type": "done"}
                 {"type": "error", "content": "..."}
```

**涉及文件**：
- 新增：`backend/api/ws.py`
- 修改：`backend/app.py`（注册 `ws_router`）

---

## 工作总结

| 子项 | 文件数 | 实际工时 |
|------|--------|---------|
| 1.1 Alembic | 5 个文件 | ~0.3 天 |
| 1.2 单例治理 | 7 个文件 | ~0.5 天 |
| 1.3 Provider 抽象 | 6 个文件 | ~0.2 天 |
| 1.4 WebSocket | 2 个文件 | ~0.2 天 |
| **合计** | **~15 个文件** | **~1.2 天** |
