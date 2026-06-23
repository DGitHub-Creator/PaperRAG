"""缓存管理路由 —— 清空语义缓存和 Redis 缓存。"""

from fastapi import APIRouter, Depends, HTTPException

from backend.core.auth import require_admin
from backend.core.logging_config import get_logger
from backend.core.models import User
from backend.services.cache import cache as redis_cache

logger = get_logger(__name__)

router = APIRouter()


@router.post("/cache/clear")
async def clear_cache(_: User = Depends(require_admin)):
    try:
        semantic = redis_cache.get_semantic()
        n = semantic.invalidate()
        logger.info("缓存已手动清空: 移除 %d 条记录", n)
        return {"message": f"缓存已清空，移除 {n} 条记录"}
    except Exception as e:
        logger.exception("清空缓存失败")
        raise HTTPException(status_code=500, detail=f"清空缓存失败: {str(e)}")
