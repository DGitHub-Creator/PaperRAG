"""数据库与缓存配置。"""

import os

from backend.core.config.llm import APP_ENV
from backend.core.config.paths import DATA_DIR

MILVUS_HOST = os.getenv("MILVUS_HOST", "127.0.0.1")
MILVUS_PORT = os.getenv("MILVUS_PORT", "19530")
MILVUS_COLLECTION = os.getenv("MILVUS_COLLECTION", "embeddings_collection")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/langchain_app",
)
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "paperrag")
REDIS_CACHE_TTL = int(os.getenv("REDIS_CACHE_TTL_SECONDS", "300"))
USE_REDIS_JOB_MANAGER = os.getenv(
    "USE_REDIS_JOB_MANAGER",
    "true" if APP_ENV in {"prod", "production"} else "false",
).lower() == "true"
