"""E8 —— 全局限流是否真的拦截请求。

审计发现 `RATE_LIMIT` 此前只影响启动日志，并未进入 `Limiter`。这几个用例用
与生产完全相同的接线方式（default_limits + SlowAPIMiddleware + 同一个限流键
函数）起一个最小应用，验证配置确实会把超阈值请求打成 429。
"""

from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.testclient import TestClient

from backend.core.rate_limit import _parse_default_limits, rate_limit_key


def _app_with_rate_limit(rate_limit: str) -> FastAPI:
    limiter = Limiter(
        key_func=rate_limit_key,
        default_limits=_parse_default_limits(rate_limit),
        storage_uri="memory://",
        headers_enabled=True,
        strategy="fixed-window",
    )
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    @app.get("/api/v1/ping")
    async def ping():
        return {"ok": True}

    return app


def test_global_default_limit_blocks_requests_over_threshold():
    client = TestClient(_app_with_rate_limit("2/minute"))
    assert client.get("/api/v1/ping").status_code == 200
    assert client.get("/api/v1/ping").status_code == 200
    assert client.get("/api/v1/ping").status_code == 429


def test_empty_rate_limit_keeps_routes_unthrottled():
    client = TestClient(_app_with_rate_limit(""))
    for _ in range(10):
        assert client.get("/api/v1/ping").status_code == 200


def test_rate_limit_headers_present_when_enabled():
    client = TestClient(_app_with_rate_limit("5/minute"))
    response = client.get("/api/v1/ping")
    assert "x-ratelimit-limit" in {k.lower() for k in response.headers.keys()}
