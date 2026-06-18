# 已完成改进项归档

> 从 `improvement_plan.md` 和 `code-review-action-items.md` 中提取的已完成项目。

---

## 0.2 添加健康检查端点 ✅

**完成时间**：2026-05

**实际变更**：

| # | 动作 | 结果 |
|---|------|------|
| 1 | 新增 `backend/api/health.py` | ✅ `/health`（存活探针）+ `/ready`（就绪探针，检查 DB/Redis/Milvus） |
| 2 | `app.py` 注册 `health_router` | ✅ |
| 3 | `docker-compose.yml` backend healthcheck | ✅ `curl -f http://localhost:8000/health` |

**涉及文件**：新增 `backend/api/health.py`，修改 `backend/app.py`、`docker-compose.yml`

---

## 1.2 前端 Vue 3 工程化 ✅

**完成时间**：2026-05

**实际变更**：从 CDN 单页（470 行 HTML + 856 行 script.js + 1314 行 style.css）迁移为 Vite + Vue 3 SFC + TypeScript。

详见 `archive/plan-2-frontend.md`。

---

## 3.2 结构化日志 ✅

**完成时间**：2026-05

**实际变更**：

| # | 动作 | 结果 |
|---|------|------|
| 1 | `JsonFormatter` 类 | ✅ `logging_config.py` 中实现 |
| 2 | `JSON_LOG=true` 环境变量开关 | ✅ |
| 3 | `config.py` 中 `JSON_LOG` 变量 | ✅ |

**涉及文件**：`backend/core/logging_config.py`、`backend/core/config.py`

---

## 0.1 消除全局可变状态 ✅

**完成时间**：2026-06-16

**实际变更**：

| # | 动作 | 结果 |
|---|------|------|
| 1 | `tools.py` global → contextvars | ✅ `_rag_context_var`, `_knowledge_calls_var`, `_rag_step_queue_var`, `_rag_step_loop_var` |
| 2 | `rag_pipeline.py` global → dependency | ✅ `_grader_model`, `_router_model` → `get_grader_model()`, `get_router_model()` |
| 3 | `rag_utils.py` global → dependency | ✅ `_stepback_model`, `_local_reranker` → `get_stepback_model()`, `get_local_reranker()` |
| 4 | `agent.py` module-level → dependency | ✅ `agent`, `model`, `storage` → `get_agent_instance()`, `get_agent_model()`, `get_conversation_storage()` |

**涉及文件**：`backend/core/dependencies.py`（+7 getter）、`backend/rag/rag_pipeline.py`、`backend/rag/rag_utils.py`、`backend/services/agent.py`

**验证结果**：0 个 `global` 关键字、0 个模块级可变单例赋值、全部文件语法正确

---

## 0.3 添加基础测试 ✅

**完成时间**：2026-06-16

**实际变更**：

| # | 动作 | 结果 |
|---|------|------|
| 1 | 从 `.gitignore` 移除 `tests/` | ✅ |
| 2 | 创建 `tests/unit/` + `tests/integration/` | ✅ |
| 3 | `tests/conftest.py` — mock database/Redis/Milvus | ✅ |
| 4 | `tests/unit/test_auth.py` — 16 tests (hash/JWT/role) | ✅ 全部通过 |
| 5 | `tests/unit/test_cache.py` — 15 tests (SemanticCache) | ✅ 全部通过 |
| 6 | `tests/unit/test_tools.py` — 7 tests (contextvars) | ✅ 全部通过 |
| 7 | `tests/unit/test_academic_cleaner.py` — 13 tests | ✅ 全部通过 |
| 8 | `pyproject.toml` 添加 `[tool.coverage]` | ✅ fail_under=40 |

**涉及文件**：新增 `tests/`（4 个测试文件 + conftest），修改 `.gitignore`、`pyproject.toml`

**验证结果**：51/51 tests passed

---

## 1.4 CORS 生产配置 ✅

**完成时间**：2026-06-16

**实际变更**：

| # | 动作 | 结果 |
|---|------|------|
| 1 | `config.py` 读取 `ALLOWED_ORIGINS` 环境变量 | ✅ 已有，逗号分隔解析 |
| 2 | `app.py` 应用 CORS 中间件 | ✅ 已有，含日志区分开放/限制模式 |
| 3 | `.env.example` 补充文档 | ✅ 已添加 `ALLOWED_ORIGINS` 和认证配置说明 |

**涉及文件**：修改 `.env.example`

---

## 1.3 PostgreSQL 连接池优化 ✅

**完成时间**：2026-06-16

**实际变更**：

| # | 动作 | 结果 |
|---|------|------|
| 1 | `database.py` 配置 `pool_pre_ping=True` | ✅ 每次取连接前 ping 探测 |
| 2 | `database.py` 配置 `pool_recycle=3600` | ✅ 每小时回收连接 |
| 3 | `config.py` `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | ✅ 通过环境变量可调（默认 10/20） |
| 4 | `.env.example` 补充文档 | ✅ |

**涉及文件**：修改 `.env.example`

---

## 1.5 上传任务状态持久化 ✅

**完成时间**：2026-06-16

**实际变更**：

| # | 动作 | 结果 |
|---|------|------|
| 1 | `RedisJobManager` 类 | ✅ 使用 Redis HASH 存储，TTL 24h |
| 2 | `USE_REDIS_JOB_MANAGER` 环境变量 | ✅ `config.py` 中定义 |
| 3 | `.env.example` 补充文档 | ✅ |

**涉及文件**：修改 `.env.example`
