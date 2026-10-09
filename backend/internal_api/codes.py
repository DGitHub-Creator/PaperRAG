"""内部错误码表（`contracts/error-codes.md` §1 的 Python 侧）。

Go 的重试器只读 `retryable`，不解析 `detail`，所以每个码的 `retryable` 与 HTTP 映射必须固定。
`tests/unit/test_internal_error_codes.py` 把本表与契约表逐码比对——改表必须先改契约，
两边不一致时 CI 变红。
"""

from dataclasses import dataclass

from backend.internal_api.schemas import ErrorCode


@dataclass(frozen=True)
class ErrorSpec:
    code: ErrorCode
    retryable: bool
    http: int


ERROR_CODES: dict[str, ErrorSpec] = {
    "INVALID_PAYLOAD": ErrorSpec("INVALID_PAYLOAD", False, 400),
    "UNSUPPORTED_TASK_TYPE": ErrorSpec("UNSUPPORTED_TASK_TYPE", False, 400),
    "BUDGET_EXCEEDED": ErrorSpec("BUDGET_EXCEEDED", False, 422),
    "MODEL_TIMEOUT": ErrorSpec("MODEL_TIMEOUT", True, 504),
    "MODEL_RATE_LIMIT": ErrorSpec("MODEL_RATE_LIMIT", True, 429),
    "PARSE_FAILED": ErrorSpec("PARSE_FAILED", False, 422),
    "INDEX_UNAVAILABLE": ErrorSpec("INDEX_UNAVAILABLE", True, 503),
    "CANCELLED": ErrorSpec("CANCELLED", False, 409),
    "INTERNAL": ErrorSpec("INTERNAL", True, 500),
}


def spec_for(code: ErrorCode) -> ErrorSpec:
    return ERROR_CODES[code]
