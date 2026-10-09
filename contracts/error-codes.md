# 错误码与错误信封契约

> 出处：`02-target-architecture.md` §3.5（Python→Go 内部码）、`01-current-architecture.md` §6.1（对浏览器信封）。
> 本文件由 `scripts/check_contracts.py` 机检：两张表的列名与取值集合都是校验对象，
> 改表格式会让 CI 变红——**这是有意的**，契约腐烂比契约严格更贵。

## 1. 内部错误码（Python `ai-core` → Go `go-api`）

每个码**必须**有 `retryable` 与 HTTP 映射。Go 的重试器只读 `retryable`，不解析 `detail` 文本
（`02` §3.4：`retryable=false` 的错误不重试）。

| code | retryable | http | 含义 | 归因侧 |
| --- | --- | --- | --- | --- |
| `INVALID_PAYLOAD` | false | 400 | 请求体缺字段、类型不符、`task_type` 需要的 payload 不合法 | Python 拒绝，Go 属编码错误 |
| `UNSUPPORTED_TASK_TYPE` | false | 400 | `task_type` 不在注册表内（P0 只注册 `PARSE_PAPER`/`INDEX_PAPER`） | Go 发了 Python 不认识的任务 |
| `BUDGET_EXCEEDED` | false | 422 | 请求体本身合法，但 `budget` 判定超限；重试只会再烧一次预算 | Python 策略拒绝 |
| `MODEL_TIMEOUT` | true | 504 | 上游 LLM 超过 `deadline`；`usage` 仍要写，Go 据此记账 | 上游 |
| `MODEL_RATE_LIMIT` | true | 429 | 上游限流/配额耗尽（区别于本服务自己的限流，见 §2） | 上游 |
| `PARSE_FAILED` | false | 422 | PDF 无法解析/非文档内容；同一份文件重试必然同样失败 | 数据 |
| `INDEX_UNAVAILABLE` | true | 503 | Milvus 不可达或 collection 缺失 | 依赖 |
| `CANCELLED` | false | 409 | 任务被协作取消；过期结果按 `lease_token` 比对后丢弃（`02` §3.4） | Go 主动 |
| `INTERNAL` | true | 500 | 未分类内部错误；必须带 `trace_id` 才可诊断 | Python |

**约定**：
- 新增码必须先改本表再改代码，且同步 `contracts/ai-execution.schema.json` 的 `code` 枚举——
  两处不一致时 `check_contracts.py` 报错。
- `retryable=true` 不等于无限重试：次数由 Go 的 `max_attempts` + `next_retry_at` 指数退避封顶。
- `detail` 面向人，**面向机器的只有 code**；Go 不得对 `detail` 做字符串匹配。
- 本表的 422（`BUDGET_EXCEEDED`/`PARSE_FAILED`）只在**内部面** `/internal/v1/ai/*` 出现，
  与决策 K4 无关：K4 降级的是 FastAPI 对浏览器的请求体校验，Go 转发给浏览器时按 §2 折算。

## 2. 对浏览器的错误信封（Go 必须保持；K1/K4 落地后只剩一种形状）

| http | 信封形状 | 来源 | Go 侧实现要点 |
| --- | --- | --- | --- |
| 400/401/403/404/409/413/502 | `{"detail": "<字符串>"}` | FastAPI `HTTPException` | 统一由 `WriteError` 产生，别在各 handler 手拼 |
| 400（原 422） | `{"detail": "<字符串>"}` | `request_validation_error_handler`（决策 K4） | 由 422+数组降级而来：`loc` 拼字段名、`msg` 拼原因、多条 `"; "` 连接。Go 用 chi 时对结构校验失败直接发 400 + 一句话即可 |
| 429 | `{"detail": "Rate limit exceeded: <表达式>"}` | `rate_limit_exceeded_handler`（决策 K1） | 必须带 `X-RateLimit-{Limit,Remaining,Reset}` 与 `Retry-After`；Python 侧注意 handler **不能写成协程**，否则 `SlowAPIMiddleware` 会退回 slowapi 自带的 `{"error": ...}` handler |
| 405 | `{"detail": "Method Not Allowed"}` | Starlette | 已在 `server/internal/httpapi/envelope.go` 落地 |
| 404 路由未命中 | `{"detail": "Not Found"}` | Starlette 默认 | 同上，文案逐字对齐 |
| 500 未捕获异常 | `{"detail": "Internal Server Error"}` | FastAPI ServerErrorMiddleware | Go 的 `Recover` 中间件产出同形状 |

> 01 §6.1 记录的三个必须保持形状的语义里，本表只覆盖第 1 个（信封）；
> 第 2 个（无分页）与第 3 个（`rag_trace` 两种形状）写在 `contracts/openapi.yaml` 的对应 schema 注释里。
> 断言这批形状的用例：`tests/integration/test_error_envelope.py`（401/400）、
> `tests/integration/test_rate_limit_enforcement.py`（429 信封 + 表头）。

## 3. 已定案（原未决项）

| # | 事项 | 结论与落点 |
| --- | --- | --- |
| K1 | 429 统一为 `detail` | 已落地 `backend/core/exceptions.py`。前端零改动：实调代码从不读 `.error`，也不按 429 分支（见 01 §6.1 复核） |
| K4 | 422 降级为 400+字符串 | 已落地同上文件的 `request_validation_error_handler`；`openapi.yaml` 删掉 `FastAPIValidationError`/`RateLimitError` |

仍待拍的契约相关项见 `docs/progress.json` 的 `decisions_pending`（D1/D2/D3）。
