"""服务间静态令牌校验（02 §3.5）。

对内部面发的不是用户 JWT 而是 `Authorization: Bearer $AICORE_INTERNAL_TOKEN`。
两条不能想当然的地方：

- **令牌未配置时一律拒绝**，不是"没配就当开放"。这一面能驱动解析与写入向量库，
  误配的默认开放比拒绝服务贵得多；compose 里 ai-core 不发布宿主端口是第二道防线，不是第一道。
- 比较用 `hmac.compare_digest`，不用 `==`：令牌是秘密，长度可变的短路比较是可侧信的。
"""

import hmac

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.core import config

_bearer = HTTPBearer(auto_error=False)


def internal_token_matches(provided: str, expected: str) -> bool:
    if not expected:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


async def require_internal_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """校验失败统一 401 + 字符串 detail，与对浏览器的信封形状一致（contracts/error-codes.md §2）。"""
    expected = getattr(config, "AICORE_INTERNAL_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=401, detail="AICORE_INTERNAL_TOKEN 未配置，内部执行面拒绝服务")
    if credentials is None or not internal_token_matches(credentials.credentials, expected):
        raise HTTPException(status_code=401, detail="内部令牌无效")
