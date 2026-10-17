"""
健康检查模块 —— 提供 /health 和 /ready 端点用于 Kubernetes / Docker Compose 探针。

/health — 存活检查（Liveness）：服务进程是否活着。
/ready  — 就绪检查（Readiness）：依赖服务是否可访问。

/ready 的三项依赖检查并发执行（线程池），单项超时上限 READY_CHECK_TIMEOUT 秒，
总延迟不会超过该上限；检查在线程中运行，不阻塞事件循环。
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from starlette.status import HTTP_503_SERVICE_UNAVAILABLE

from backend.core.config import VERSION
from backend.core.database import SessionLocal
from backend.services.cache import cache as redis_cache

# 预热导入：pymilvus/grpc 模块链较重，冷磁盘或杀毒扫描下首次 import 可能耗时
# 数十秒。若留到就绪探针首次调用时才懒加载，这段耗时发生在探针线程内：
# HTTP 响应虽被 READY_CHECK_TIMEOUT 兜底，但线程要等 import+连接全部完成
# 才结束，事件循环默认线程池的回收（executor join）会被拖住。在应用导入期
# 预热可保证探针路径只做"连接"这一件事。
import backend.vectordb.milvus_client  # noqa: E402, F401

logger = logging.getLogger("api.health")

router = APIRouter(tags=["健康检查"])

#: 单项依赖检查的超时上限（秒）。超过即视为不可用。
READY_CHECK_TIMEOUT = 3.0


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
        logger.warning("数据库健康检查失败: %s", type(e).__name__)
        return False, "unavailable"
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
        logger.warning("Redis 健康检查失败: %s", type(e).__name__)
        return False, "unavailable"


def _check_milvus() -> tuple[bool, str]:
    """检查 Milvus 是否可连接。

    复用应用共享的 MilvusManager 单例，探测的是业务实际使用的连接，
    而非每次新建临时连接。建连与 RPC 均受 ``READY_CHECK_TIMEOUT`` 约束：
    未设超时时 gRPC 会无限重连，探测线程将阻塞并泄漏。

    Returns:
        (ok: bool, detail: str)
    """
    try:
        # 经模块属性访问依赖容器，保持 get_milvus_manager 可被测试 patch
        from backend.core import dependencies

        manager = dependencies.get_milvus_manager()
        client = manager._get_client(timeout=READY_CHECK_TIMEOUT)
        client.list_collections(timeout=READY_CHECK_TIMEOUT)
        return True, "connected"
    except Exception as e:
        logger.warning("Milvus 健康检查失败: %s", type(e).__name__)
        return False, "unavailable"


@router.get("/health")
async def health():
    """存活探针：仅返回进程是否活着。"""
    return {
        "status": "ok",
        "version": VERSION,
    }


async def _run_check(check) -> tuple[bool, str]:
    """在线程池中执行同步检查，带超时上限。

    Args:
        check: 无参同步函数，返回 (ok, detail)。

    Returns:
        (ok, detail)；超时时返回 (False, "timeout ...")。
    """
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(check), timeout=READY_CHECK_TIMEOUT
        )
    except asyncio.TimeoutError:
        return False, f"timeout after {READY_CHECK_TIMEOUT:.0f}s"
    except Exception as e:  # 防御：线程内未预期异常不应拖垮探针
        logger.warning("健康检查执行异常: %s", type(e).__name__)
        return False, "check failed"


@router.get("/ready")
async def readiness():
    """就绪探针：检查所有依赖服务的连接状态。

    若任一服务不可用，返回 503 状态码。
    各依赖并发检测，单项超时不影响整体响应时间上限。
    """
    (db_ok, db_detail), (redis_ok, redis_detail), (milvus_ok, milvus_detail) = (
        await asyncio.gather(
            _run_check(_check_db),
            _run_check(_check_redis),
            _run_check(_check_milvus),
        )
    )

    checks = {
        "database": {"status": "ok" if db_ok else "error", "detail": db_detail},
        "redis": {"status": "ok" if redis_ok else "error", "detail": redis_detail},
        "milvus": {"status": "ok" if milvus_ok else "error", "detail": milvus_detail},
    }

    all_ok = all(check["status"] == "ok" for check in checks.values())

    if not all_ok:
        raise HTTPException(
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "version": VERSION, "checks": checks},
        )

    return {
        "status": "ok",
        "version": VERSION,
        "checks": checks,
    }
