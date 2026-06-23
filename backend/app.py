"""PaperRAG FastAPI 应用入口 —— CORS、静态文件、数据库初始化、路由挂载。

启动方式:
    uv run uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
    python backend/app.py
"""

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from backend.api.auth import router as auth_router
from backend.api.chat import router as chat_router
from backend.api.health import router as health_router
from backend.api.routes import router as api_router
from backend.api.sessions import router as sessions_router
from backend.api.ws import router as ws_router
from backend.core.config import (
    ALLOWED_ORIGINS,
    RATE_LIMIT,
    ensure_runtime_directories,
    validate_config,
    validate_runtime_security,
)
from backend.core.database import init_db
from backend.core.exceptions import PaperRAGError, paper_rag_error_handler, unhandled_error_handler
from backend.core.logging_config import setup_root_logger
from backend.core.metrics import init_metrics, metrics_endpoint, metrics_middleware
from backend.core.rate_limit import limiter
from backend.core.stats import record_request

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
    app = FastAPI(title="PaperRAG - 学术论文 RAG 知识库平台")

    # ── 速率限制 ───────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    if RATE_LIMIT:
        logger.info("全局速率限制已启用: %s", RATE_LIMIT)
    else:
        logger.warning("速率限制已禁用（RATE_LIMIT 未设置）")

    # ── 统一异常处理 ─────────────────────────────────────────────
    app.add_exception_handler(PaperRAGError, paper_rag_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    # ── 启动事件: 数据库初始化 ──────────────────────────────────
    @app.on_event("startup")
    async def _startup_init_db():
        """应用启动时自动建表（如不存在）。"""
        logger.info("正在初始化数据库...")
        ensure_runtime_directories()
        validate_config()
        validate_runtime_security()
        init_db()
        init_metrics()
        logger.info("数据库初始化完成")

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
logger.info("PaperRAG 应用已就绪")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
    )
