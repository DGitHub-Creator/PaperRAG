"""Prometheus 指标模块 —— 请求计数、延迟直方图、活跃连接。"""

import time

from prometheus_client import Counter, Gauge, Histogram, Info, generate_latest
from starlette.requests import Request
from starlette.responses import Response

from backend.core.config import VERSION

APP_INFO = Info("paperrag", "PaperRAG application information")
REQUEST_COUNT = Counter(
    "paperrag_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "paperrag_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)
ACTIVE_REQUESTS = Gauge(
    "paperrag_active_requests",
    "Number of currently active requests",
)


def init_metrics():
    APP_INFO.info({"version": VERSION})


async def metrics_endpoint(request: Request) -> Response:
    return Response(generate_latest(), media_type="text/plain")


async def metrics_middleware(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)

    method = request.method
    path = request.url.path

    ACTIVE_REQUESTS.inc()
    start = time.perf_counter()
    try:
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        status = str(response.status_code)
        REQUEST_COUNT.labels(method=method, endpoint=path, status=status).inc()
        REQUEST_LATENCY.labels(method=method, endpoint=path).observe(elapsed)
        return response
    except Exception:
        elapsed = time.perf_counter() - start
        REQUEST_COUNT.labels(method=method, endpoint=path, status="500").inc()
        REQUEST_LATENCY.labels(method=method, endpoint=path).observe(elapsed)
        raise
    finally:
        ACTIVE_REQUESTS.dec()
