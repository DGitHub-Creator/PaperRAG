"""Rate limiting utilities — shared limiter instance for app.py and routes.py.

存储策略：
  - Redis 可达时使用 REDIS_URL 作为共享存储（多 worker / 多副本一致计数）；
  - Redis 不可达（开发/测试环境）时回退进程内存存储，避免限流路径抛连接错误。

限流键策略：
  - 默认取直连来源 IP（request.client.host）；
  - 仅在 TRUST_PROXY_HEADERS 开启时才信任 X-Forwarded-For 并取首个地址。
    直连场景开启该开关会让客户端伪造请求头绕过限流。

`default_limits` 在模块导入时由 RATE_LIMIT 决定，改这个环境变量需要重启进程。
本模块不在导入期打日志：它经 app.py 的路由导入链最先加载，那时
`setup_root_logger()` 还没执行，INFO 会被丢弃。限流状态的日志统一在 app.py
建应用时输出，来源就是这里导出的三个量。
"""

from ipaddress import ip_address, ip_network

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from backend.core.config.auth import RATE_LIMIT, TRUST_PROXY_HEADERS, TRUSTED_PROXY_CIDRS


def _resolve_storage_uri() -> str | None:
    """探测 Redis 可达性；不可达时返回 None（内存回退）。"""
    try:
        from backend.core.config.database import REDIS_URL

        if not REDIS_URL:
            return None
        import redis

        with redis.Redis.from_url(REDIS_URL, socket_connect_timeout=1, socket_timeout=1) as client:
            client.ping()
        return REDIS_URL
    except Exception as exc:
        from backend.core.config.llm import APP_ENV
        if APP_ENV in {"prod", "production"}:
            raise RuntimeError("Redis 限流存储不可用，拒绝在生产环境降级") from exc
        return None


def _parse_default_limits(raw: str) -> list[str]:
    """把 RATE_LIMIT 解析成 slowapi 的 default_limits 列表，空值表示不启用。"""
    spec = raw.strip()
    return [spec] if spec else []


_trusted_networks = tuple(ip_network(value.strip(), strict=False) for value in TRUSTED_PROXY_CIDRS.split(",") if value.strip())


def rate_limit_key(request: Request) -> str:
    """只从已配置的可信直连代理接受转发链，并从右侧剥离可信跳数。"""
    remote = get_remote_address(request)
    if not TRUST_PROXY_HEADERS:
        return remote
    try:
        current = ip_address(remote)
        if not any(current in network for network in _trusted_networks):
            return remote
        for value in reversed(request.headers.get("X-Forwarded-For", "").split(",")):
            forwarded = ip_address(value.strip())
            current = forwarded
            if not any(current in network for network in _trusted_networks):
                break
        return str(current)
    except ValueError:
        return remote


storage_uri = _resolve_storage_uri()

default_limits = _parse_default_limits(RATE_LIMIT)

limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=default_limits,
    storage_uri=storage_uri,
    headers_enabled=True,  # 响应携带 X-RateLimit-* 头，便于前端与运维观察
    strategy="fixed-window",
)

storage_backend = "redis" if storage_uri else "进程内存"
key_source = "X-Forwarded-For 首跳" if TRUST_PROXY_HEADERS else "直连 IP"
