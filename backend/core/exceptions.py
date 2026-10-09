"""统一异常定义 —— 业务异常层级与全局错误处理。"""

import time

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from backend.core.logging_config import get_logger

logger = get_logger(__name__)


class PaperRAGError(Exception):
    """应用基础异常。"""
    status_code = 500
    detail = "Internal server error"

    def __init__(self, detail: str | None = None):
        self.detail = detail or self.detail
        super().__init__(self.detail)


class ConfigError(PaperRAGError):
    """配置错误。"""
    status_code = 500
    detail = "Configuration error"


class DocumentError(PaperRAGError):
    """文档处理错误。"""
    status_code = 400
    detail = "Document processing error"


class DocumentNotFoundError(DocumentError):
    """文档不存在。"""
    status_code = 404
    detail = "Document not found"


class UnsupportedDocumentError(DocumentError):
    """不支持的文档格式。"""
    status_code = 400
    detail = "Unsupported document type"


class UploadSizeExceededError(DocumentError):
    """上传文件大小超限。"""
    status_code = 413
    detail = "Upload file size exceeded"


class AgentError(PaperRAGError):
    """Agent 处理错误。"""
    status_code = 500
    detail = "Agent processing error"


class RetrievalError(PaperRAGError):
    """检索错误。"""
    status_code = 500
    detail = "Retrieval error"


async def paper_rag_error_handler(request: Request, exc: PaperRAGError) -> JSONResponse:
    logger.warning("Business error: %s %s - %s", request.method, request.url.path, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """请求结构校验失败降级为 400 + 字符串 detail（决策 K4）。

    FastAPI 默认发 422 + `detail: [...]`，数组元素带 `ctx`/`url` 这类由 pydantic
    决定的形状，Go 要逐字复刻就得复刻整套 pydantic 错误目录；而前端只把 detail
    当字符串显示。契约因此锁 400 + 字符串（contracts/error-codes.md §2），
    Go 与 Python 用同一句话就能互验。
    """
    parts = []
    for err in exc.errors():
        field = ".".join(str(seg) for seg in err.get("loc", ())[1:]) or "请求体"
        parts.append(f"{field}: {err.get('msg', 'invalid value')}")
    detail = "; ".join(parts) or "Invalid request payload"
    logger.warning("Validation error: %s %s - %s", request.method, request.url.path, detail)
    return JSONResponse(status_code=400, content={"detail": detail})


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """429 也走 detail 信封（决策 K1），并在这里重建 `X-RateLimit-*` 头。

    必须写成**同步**函数：`SlowAPIMiddleware` 走的是 `sync_check_limits()`，它一遇到
    协程 handler 就悄悄退回 slowapi 自带的 `_rate_limit_exceeded_handler`（发
    `{"error": ...}`）——异步版本的自定义 handler 根本不会被调用。同理，命中限流时
    middleware 直接返回本函数的响应，不会执行 `_inject_headers()`，所以响应头只能在
    这里自己拼：窗口数据走 `limits` 的公开接口，slowapi 那边只读它的开关字段。
    """
    response = JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
    )
    _inject_rate_limit_headers(request, response)
    return response


def _inject_rate_limit_headers(request: Request, response: JSONResponse) -> None:
    """从 `request.state.view_rate_limit`（slowapi 存的 (RateLimitItem, 键参数) 元组）重建表头。"""
    current = getattr(request.state, "view_rate_limit", None)
    limiter = getattr(request.app.state, "limiter", None)
    # 读的是 slowapi 自己 `_inject_headers()` 用的同一个开关，只取值，不调它的私有函数
    if current is None or limiter is None or not getattr(limiter, "_headers_enabled", False):
        return
    try:
        item, identifiers = current
        reset_at, remaining = limiter.limiter.get_window_stats(item, *identifiers)
        reset_in = 1 + reset_at
    except Exception:  # 表头是附加信息，取不到也不能把 429 变成 500
        logger.debug("限流响应头重建失败", exc_info=True)
        return
    response.headers.setdefault("X-RateLimit-Limit", str(item.amount))
    response.headers.setdefault("X-RateLimit-Remaining", str(remaining))
    response.headers.setdefault("X-RateLimit-Reset", str(int(reset_in)))
    response.headers.setdefault("Retry-After", str(max(0, int(reset_in - time.time()))))
