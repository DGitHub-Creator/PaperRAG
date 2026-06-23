"""统一异常定义 —— 业务异常层级与全局错误处理。"""

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

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
