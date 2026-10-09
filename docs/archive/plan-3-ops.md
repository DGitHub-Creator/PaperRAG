# Plan 3 — 运维与安全 ✅ 已完成（归档）

> ⚠️ **已归档，不作为实施依据。** 标题里的「✅ 已完成」是旧计划的自评口径；
> 实测核查见 [00-audit.md](../refactor/00-audit.md) §3（多处「宣称 ✅ 但实际断链」）。
> 现行进度真相源是 [progress.json](../progress.json)，验收口径见 [09-milestone-p0.md](../refactor/09-milestone-p0.md) §0。
> 完成时间：2026-06
> CI/CD、限流、JWT Refresh Token、结构化日志。

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
| 1 | `JsonFormatter` 类 | ✅ |
| 2 | `JSON_LOG=true` 环境变量开关 | ✅ |
| 3 | `config.py` 中 `JSON_LOG` 变量 | ✅ |

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

- 新增：`Dockerfile`、`backend/core/rate_limit.py`、`backend/core/stats.py`
- 修改：`backend/core/config.py`、`backend/core/auth.py`、`backend/schemas/schemas.py`、`backend/api/routes.py`、`backend/app.py`、`pyproject.toml`
- 测试：`tests/test_stats.py`、`tests/test_rate_limit.py`
