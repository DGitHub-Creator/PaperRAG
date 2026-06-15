"""
健康检查模块 —— 提供 /health 和 /ready 端点用于 Kubernetes / Docker Compose 探针。

/health — 存活检查（Liveness）：服务进程是否活着。
/ready  — 就绪检查（Readiness）：依赖服务是否可访问。
"""

from fastapi import APIRouter
from sqlalchemy import text

from backend.core.config import VERSION
from backend.core.database import SessionLocal
from backend.core.logging_config import get_logger
from backend.services.cache import cache as redis_cache

logger = get_logger(__name__)

router = APIRouter(tags=["健康检查"])


def _check_db() -> tuple[bool, str]:
    """检查 PostgreSQL 是否可连接。

    Returns:
        (ok: bool, detail: str)
    """
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return True, "connected"
    except Exception as e:
        logger.warning("数据库健康检查失败: %s", e)
        return False, f"disconnected: {e}"
    finally:
        db.close()


def _check_redis() -> tuple[bool, str]:
    """检查 Redis 是否可连接。

    Returns:
        (ok: bool, detail: str)
    """
    try:
        client = redis_cache._get_client()
        client.ping()
        return True, "connected"
    except Exception as e:
        logger.warning("Redis 健康检查失败: %s", e)
        return False, f"disconnected: {e}"


def _check_milvus() -> tuple[bool, str]:
    """检查 Milvus 是否可连接。

    Returns:
        (ok: bool, detail: str)
    """
    try:
        from backend.vectordb.milvus_client import MilvusManager

        m = MilvusManager()
        client = m._get_client()
        client.list_collections()
        return True, "connected"
    except Exception as e:
        logger.warning("Milvus 健康检查失败: %s", e)
        return False, f"disconnected: {e}"


@router.get("/health")
async def health():
    """存活探针：仅返回进程是否活着。"""
    return {
        "status": "ok",
        "version": VERSION,
    }


@router.get("/ready")
async def readiness():
    """就绪探针：检查所有依赖服务的连接状态。

    若任一服务不可用，返回 503 状态码。
    各依赖独立检测，不因一个失败而跳过其他。
    """
    db_ok, db_detail = _check_db()
    redis_ok, redis_detail = _check_redis()
    milvus_ok, milvus_detail = _check_milvus()

    checks = {
        "database": {"status": "ok" if db_ok else "error", "detail": db_detail},
        "redis": {"status": "ok" if redis_ok else "error", "detail": redis_detail},
        "milvus": {"status": "ok" if milvus_ok else "error", "detail": milvus_detail},
    }

    all_ok = all(check["status"] == "ok" for check in checks.values())

    if not all_ok:
        from fastapi import HTTPException
        from starlette.status import HTTP_503_SERVICE_UNAVAILABLE

        raise HTTPException(
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "version": VERSION, "checks": checks},
        )

    return {
        "status": "ok",
        "version": VERSION,
        "checks": checks,
    }
