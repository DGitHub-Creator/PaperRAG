"""生产环境配置预设。

在应用启动时 import 此模块可自动设置生产环境推荐默认值。
实际配置仍以环境变量为准，此处仅提供安全合理的 fallback。

用法：
    import backend.core.config.prod  # 在最早期 import，设置生产默认值
    from backend.core.config import LLM_API_KEY, JWT_SECRET_KEY  # 正常使用
"""

import os

os.setdefault("APP_ENV", "production")
os.setdefault("RATE_LIMIT", "60/minute")
os.setdefault("USE_REDIS_JOB_MANAGER", "true")
os.setdefault("ENABLE_CACHE", "true")
os.setdefault("ENABLE_HYDE", "true")
os.setdefault("MAX_UPLOAD_SIZE_MB", "100")
