"""ResearchPilot FastAPI 应用入口 —— CORS、静态文件、数据库初始化、路由挂载。

启动方式:
    uv run python scripts/dev.py serve
    python backend/app.py
"""

import logging
from contextlib import asynccontextmanager
import os
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from backend.api.auth import router as auth_router
from backend.api.chat import router as chat_router
from backend.api.health import router as health_router
from backend.api.routes import router as api_router
from backend.api.sessions import router as sessions_router
from backend.api.ws import router as ws_router
from backend.internal_api import internal_router
from backend.internal_api.router import recover_executions
from backend.core.config import (
    ALLOWED_ORIGINS,
    ensure_runtime_directories,
    validate_config,
    validate_runtime_security,
)
from backend.core.database import init_db
from backend.core.exceptions import (
    ResearchPilotError,
    research_pilot_error_handler,
    rate_limit_exceeded_handler,
    request_validation_error_handler,
    unhandled_error_handler,
)
from backend.core.logging_config import request_trace_id, setup_root_logger
from backend.core.metrics import init_metrics, metrics_endpoint, metrics_middleware
from backend.core.rate_limit import default_limits, key_source, limiter, storage_backend
from backend.core.stats import record_request
from backend.services.document_jobs import recover_document_jobs, recover_pending_documents

# ── 初始化日志系统 ──────────────────────────────────────────────────
# 在应用启动前配置根 logger，后续所有模块的 logger 自动继承 handler
setup_root_logger()
logger = logging.getLogger("app")

# ── 路径常量 ──────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。

    配置项:
        - CORS: 从 ALLOWED_ORIGINS 环境变量读取，默认全开（开发模式）
        - 静态文件: 挂载 frontend/ 目录到根路径
        - 路由: 注册 Health Router + API Router（auth、chat、sessions、documents）
        - 启动事件: 自动初始化数据库表

    Returns:
        配置完成的 FastAPI 实例。
    """
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ensure_runtime_directories()
        validate_config()
        validate_runtime_security()
        await run_in_threadpool(init_db)
        await run_in_threadpool(recover_pending_documents)
        await run_in_threadpool(recover_document_jobs)
        await run_in_threadpool(recover_executions)
        init_metrics()
        logger.info("数据库初始化完成")
        yield

    app = FastAPI(title="ResearchPilot - 自主科研平台", lifespan=lifespan)

    # ── 错误信封（决策 K1/K4：全仓只留 {"detail": "..."} 一种形状）──
    # 422 的数组 detail 由 pydantic 决定形状，Go 复刻不起，故降级为 400 + 字符串。
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)

    # ── 速率限制 ───────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    # 日志取自构造 limiter 时真正用到的量，避免"日志说开了、其实没配"
    if default_limits:
        logger.info(
            "全局限流已启用: %s（存储=%s，计数键=%s）",
            ", ".join(default_limits),
            storage_backend,
            key_source,
        )
    else:
        logger.warning(
            "全局限流未启用（RATE_LIMIT 为空），仅路由级 @limiter.limit 生效（存储=%s，计数键=%s）",
            storage_backend,
            key_source,
        )

    # ── 统一异常处理 ─────────────────────────────────────────────
    app.add_exception_handler(ResearchPilotError, research_pilot_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    # ── CORS 中间件（生产环境通过 ALLOWED_ORIGINS 环境变量限制）─
    origins = ALLOWED_ORIGINS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if origins != ["*"]:
        logger.info("CORS 已限制来源: %s", origins)
    else:
        logger.warning("CORS 允许所有来源（仅推荐开发环境使用）")

    # ── 请求统计中间件 ─────────────────────────────────────────
    @app.middleware("http")
    async def _stats_middleware(request: Request, call_next):
        record_request(request.url.path)
        response = await call_next(request)
        return response

    # ── 开发环境无缓存中间件 ────────────────────────────────────
    @app.middleware("http")
    async def _no_cache(request, call_next):
        """对前端静态资源禁用缓存，保证开发时即时生效。"""
        response = await call_next(request)
        path = request.url.path or ""
        if path == "/" or path.endswith((".html", ".js", ".css")):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    # ── Prometheus 指标中间件 ───────────────────────────────────
    @app.middleware("http")
    async def _metrics_middleware(request: Request, call_next):
        return await metrics_middleware(request, call_next)

    @app.middleware("http")
    async def _trace_middleware(request: Request, call_next):
        trace_id = request.headers.get("X-Trace-Id") or uuid4().hex
        token = request_trace_id.set(trace_id)
        try:
            response = await call_next(request)
            response.headers["X-Trace-Id"] = trace_id
            return response
        finally:
            # 归还当前请求的上下文，线程池/下游任务继承独立副本。
            request_trace_id.reset(token)

    # ── 注册路由 ────────────────────────────────────────────────
    # 健康检查和指标端点（根路径，不加前缀）
    app.include_router(health_router)
    app.add_api_route("/metrics", metrics_endpoint, methods=["GET"])
    # API 路由统一加 /api/v1 前缀
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(sessions_router, prefix="/api/v1")
    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(ws_router, prefix="/api/v1")
    # 内部执行面：路径自带 /internal/v1/ai 前缀，不对浏览器暴露，也不进 openapi.yaml
    app.include_router(internal_router)

    # ── 挂载前端静态文件 ────────────────────────────────────────
    # 生产优先: dist/ → 开发备选: frontend/
    dist_dir = FRONTEND_DIR / "dist"
    static_dir = (
        dist_dir if dist_dir.exists() and (dist_dir / "index.html").exists() else FRONTEND_DIR
    )
    if static_dir.exists():
        app.mount(
            "/",
            StaticFiles(directory=str(static_dir), html=True),
            name="static",
        )
        logger.info("前端静态文件挂载: %s (dist=%s)", static_dir, dist_dir.exists())

    return app


# ── 模块级 app 实例（uvicorn 入口）─────────────────────────────────
app = create_app()
logger.info("ResearchPilot 应用已就绪")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        proxy_headers=False,
    )
