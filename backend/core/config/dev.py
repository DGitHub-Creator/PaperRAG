"""开发环境配置预设。"""

import os

os.setdefault("APP_ENV", "development")
os.setdefault("RATE_LIMIT", "")
os.setdefault("ALLOWED_ORIGINS", "*")
os.setdefault("USE_REDIS_JOB_MANAGER", "false")
os.setdefault("ENABLE_CACHE", "true")
os.setdefault("ENABLE_HYDE", "true")
