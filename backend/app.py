"""PaperRAG FastAPI 应用入口 —— CORS、静态文件、数据库初始化、路由挂载。

启动方式:
    uv run uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
    python backend/app.py
"""

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.health import router as health_router
from backend.api.routes import router as api_router
from backend.api.ws import router as ws_router
from backend.core.config import ALLOWED_ORIGINS
from backend.core.database import init_db
from backend.core.logging_config import setup_root_logger

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

    # ── 启动事件: 数据库初始化 ──────────────────────────────────
    @app.on_event("startup")
    async def _startup_init_db():
        """应用启动时自动建表（如不存在）。"""
        logger.info("正在初始化数据库...")
        init_db()
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

    # ── 注册路由 ────────────────────────────────────────────────
    # 健康检查优先注册，避免被静态文件挂载覆盖
    app.include_router(health_router)
    app.include_router(api_router)
    app.include_router(ws_router)

    # ── 挂载前端静态文件 ────────────────────────────────────────
    if FRONTEND_DIR.exists():
        app.mount(
            "/",
            StaticFiles(directory=str(FRONTEND_DIR), html=True),
            name="static",
        )
        logger.info("前端静态文件挂载: %s", FRONTEND_DIR)

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
