"""ai-core 的内部执行面（仅内网，Go 是唯一调用方）。

与对浏览器的 `/api/v1` 完全分开：这里的请求/响应形状由
`contracts/ai-execution.schema.json` 规定，错误码由 `contracts/error-codes.md` §1 规定，
鉴权用静态服务令牌而不是用户 JWT。
"""

from backend.internal_api.router import router as internal_router

__all__ = ["internal_router"]
