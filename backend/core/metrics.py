"""Prometheus 指标模块 —— 请求计数、延迟直方图、活跃连接。

标签基数控制：
  - endpoint 标签使用路由模板（如 /api/v1/documents/upload/jobs/{job_id}），
    而非原始请求路径 —— 避免带 ID 的路径造成标签基数爆炸；
  - 未匹配路由的请求（404/静态资源）统一归并为 "/unmatched"。
"""

import time

from prometheus_client import Counter, Gauge, Histogram, Info, generate_latest
from starlette.requests import Request
from starlette.responses import Response

from backend.core.config import VERSION

APP_INFO = Info("researchpilot", "ResearchPilot application information")
REQUEST_COUNT = Counter(
    "researchpilot_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "researchpilot_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)
ACTIVE_REQUESTS = Gauge(
    "researchpilot_active_requests",
    "Number of currently active requests",
)


def init_metrics():
    APP_INFO.info({"version": VERSION})


async def metrics_endpoint(request: Request) -> Response:
    return Response(generate_latest(), media_type="text/plain")


def _template_path(request: Request) -> str:
    """取路由模板路径；无匹配路由时返回占位符（限制标签基数）。"""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if path:
        return path
    # 静态文件挂载（StaticFiles）无模板 → 按一级前缀归并
    raw = request.url.path
    if raw.startswith("/assets/"):
        return "/assets/{file}"
    return "/unmatched"


async def metrics_middleware(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)

    method = request.method

    ACTIVE_REQUESTS.inc()
    start = time.perf_counter()
    try:
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        status = str(response.status_code)
        # 路由匹配发生在 call_next 内部，完成后 scope["route"] 才可用
        endpoint = _template_path(request)
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(elapsed)
        return response
    except Exception:
        elapsed = time.perf_counter() - start
        endpoint = _template_path(request)
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status="500").inc()
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(elapsed)
        raise
    finally:
        ACTIVE_REQUESTS.dec()
