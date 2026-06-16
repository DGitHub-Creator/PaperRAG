# Plan 3 — 运维与安全（部分完成）

> 目标：CI/CD、限流、JWT Refresh Token、结构化日志。
>
> **归档说明**：3.2 结构化日志已完成，详见 `archive/completed-items.md`。

---

## 3.1 CI/CD（P0）

| # | 动作 | 状态 |
|---|------|------|
| 1 | GitHub Actions `test.yml` | ⏳ |
| 2 | `Dockerfile` | ⏳ |
| 3 | CI 中 `alembic check` 迁移一致性 | ⏳ |
| 4 | CI 覆盖率门禁 `pytest --cov --cov-fail-under=60` | ⏳ |

## 3.2 结构化日志（P0）✅

| # | 动作 | 状态 |
|---|------|------|
| 1 | `JsonFormatter` 类 | ✅ 已实现 |
| 2 | `JSON_LOG=true` 环境变量开关 | ✅ 已实现 |
| 3 | `config.py` 中 `JSON_LOG` 变量 | ✅ 已实现 |

## 3.3 速率限制（P1）

| # | 动作 | 状态 |
|---|------|------|
| 1 | slowapi 集成 | ⏳ |
| 2 | `RATE_LIMIT` 配置 | ⏳ |

## 3.4 JWT Refresh Token（P1）

| # | 动作 | 状态 |
|---|------|------|
| 1 | `create_refresh_token()` | ⏳ |
| 2 | `POST /auth/refresh` 端点 | ⏳ |

## 3.5 使用量统计（P1）

| # | 动作 | 状态 |
|---|------|------|
| 1 | 请求日志中间件 | ⏳ |

## 涉及文件

- 已改：`backend/core/logging_config.py`（已实现）
- 待改：`backend/core/config.py`、`backend/api/routes.py`、`backend/app.py`、`Dockerfile`
- 新增：`.github/workflows/test.yml`
