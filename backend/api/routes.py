"""API 路由模块 —— 统一路由注册入口。

各端点已拆分到独立模块：
  - documents.py: 文档上传、删除、列表、增量导入
  - cache.py: 缓存管理
  - stats.py: API 使用统计

本模块保留 router 用于向后兼容，新代码请直接导入子模块。
"""

from fastapi import APIRouter

from backend.api.cache import router as cache_router
from backend.api.documents import router as documents_router
from backend.api.stats import router as stats_router

router = APIRouter()

router.include_router(documents_router)
router.include_router(cache_router)
router.include_router(stats_router)
