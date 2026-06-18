# Plan 3 — 运维与安全（✅ 已完成）

> 目标：CI/CD、限流、JWT Refresh Token、结构化日志。
>
> **归档说明**：3.2 结构化日志已完成，详见 `archive/completed-items.md`。

---

## 3.1 CI/CD（P0）✅

| # | 动作 | 状态 |
|---|------|------|
| 1 | GitHub Actions `test.yml` | ✅ |
| 2 | `Dockerfile` | ✅ |
| 3 | CI 中 `alembic check` 迁移一致性 | ✅ |
| 4 | CI 覆盖率门禁 `pytest --cov --cov-fail-under=45` | ✅ |

## 3.2 结构化日志（P0）✅

| # | 动作 | 状态 |
|---|------|------|
| 1 | `JsonFormatter` 类 | ✅ 已实现 |
| 2 | `JSON_LOG=true` 环境变量开关 | ✅ 已实现 |
| 3 | `config.py` 中 `JSON_LOG` 变量 | ✅ 已实现 |

## 3.3 速率限制（P1）✅

| # | 动作 | 状态 |
|---|------|------|
| 1 | slowapi 集成 | ✅ |
| 2 | `RATE_LIMIT` 配置 | ✅ |

## 3.4 JWT Refresh Token（P1）✅

| # | 动作 | 状态 |
|---|------|------|
| 1 | `create_refresh_token()` | ✅ |
| 2 | `POST /auth/refresh` 端点 | ✅ |

## 3.5 使用量统计（P1）✅

| # | 动作 | 状态 |
|---|------|------|
| 1 | 请求日志中间件 | ✅ |

## 涉及文件

| 文件 | 动作 |
|------|------|
| `.github/workflows/test.yml` | 新增 — CI 流水线（lint + alembic check + pytest --cov） |
| `Dockerfile` | 新增 — python:3.12-slim + uvicorn |
| `backend/core/rate_limit.py` | 新增 — slowapi 共享 limiter 实例 |
| `backend/core/stats.py` | 新增 — 线程安全的内存请求计数器 |
| `backend/core/config.py` | 修改 — 新增 `RATE_LIMIT`、`JWT_REFRESH_EXPIRE_DAYS` |
| `backend/core/auth.py` | 修改 — 新增 `create_refresh_token()` |
| `backend/schemas/schemas.py` | 修改 — `AuthResponse` 新增 `refresh_token` 字段；新增 `RefreshTokenRequest` |
| `backend/api/routes.py` | 修改 — login/register 返回 refresh_token；新增 `POST /auth/refresh`、`GET/DELETE /stats/usage`；auth 端点加 rate limit 装饰器 |
| `backend/app.py` | 修改 — 注册 SlowAPIMiddleware + 统计中间件 |
| `pyproject.toml` | 修改 — 新增 `slowapi` 依赖 |
| `tests/test_auth.py` | 新增 — JWT/Refresh 令牌、密码哈希测试 |
| `tests/test_stats.py` | 新增 — 请求计数、重置、排序测试 |
| `tests/test_rate_limit.py` | 新增 — limiter 实例测试 |
