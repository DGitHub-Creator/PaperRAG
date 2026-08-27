"""Rate limiting utilities — shared limiter instance for app.py and routes.py.

存储策略：
  - Redis 可达时使用 REDIS_URL 作为共享存储（多 worker / 多副本一致计数）；
  - Redis 不可达（开发/测试环境）时回退进程内存存储，避免限流路径抛连接错误。
"""

import logging

from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger("core.rate_limit")


def _resolve_storage_uri() -> str | None:
    """探测 Redis 可达性；不可达时返回 None（内存回退）。"""
    try:
        from backend.core.config.database import REDIS_URL

        if not REDIS_URL:
            return None
        import redis

        client = redis.Redis.from_url(
            REDIS_URL, socket_connect_timeout=1, socket_timeout=1
        )
        client.ping()
        return REDIS_URL
    except Exception:
        logger.info("Redis 不可达，限流使用进程内存存储（单实例模式）")
        return None


_storage_uri = _resolve_storage_uri()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=_storage_uri,
    headers_enabled=True,  # 响应携带 X-RateLimit-* 头，便于前端与运维观察
    strategy="fixed-window",
)
