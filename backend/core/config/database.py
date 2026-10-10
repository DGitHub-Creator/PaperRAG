"""数据库与缓存配置。"""

import os

from backend.core.config.llm import APP_ENV

MILVUS_HOST = os.getenv("MILVUS_HOST", "127.0.0.1")
MILVUS_PORT = os.getenv("MILVUS_PORT", "19530")
MILVUS_COLLECTION = os.getenv("MILVUS_COLLECTION", "embeddings_collection")
MILVUS_CONNECT_TIMEOUT = float(os.getenv("MILVUS_CONNECT_TIMEOUT", "10"))
"""Milvus 建立连接（gRPC channel ready）的超时上限（秒）。

不设上限时 gRPC 会无限重连，Milvus 宕机期间每次探测都会泄漏一个
永久阻塞的线程并占满事件循环默认线程池，因此必须有界。
"""

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/langchain_app",
)
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "researchpilot")
REDIS_CACHE_TTL = int(os.getenv("REDIS_CACHE_TTL_SECONDS", "300"))
USE_REDIS_JOB_MANAGER = os.getenv(
    "USE_REDIS_JOB_MANAGER",
    "true" if APP_ENV in {"prod", "production"} else "false",
).lower() == "true"
