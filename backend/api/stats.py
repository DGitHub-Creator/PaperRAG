"""统计与运维路由 —— API 使用统计端点。"""

from fastapi import APIRouter, Depends

from backend.core.auth import require_admin
from backend.core.logging_config import get_logger
from backend.core.models import User
from backend.core.stats import get_stats, reset_stats

logger = get_logger(__name__)

router = APIRouter()


@router.get("/stats/usage")
async def usage_stats(_: User = Depends(require_admin)):
    return get_stats()


@router.delete("/stats/usage")
async def reset_usage_stats(_: User = Depends(require_admin)):
    reset_stats()
    return {"message": "统计已重置"}
