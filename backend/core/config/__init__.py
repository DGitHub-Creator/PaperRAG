"""PaperRAG 集中配置 —— 统一管理所有模块的配置读取。

环境分层：
  - config/dev.py:  开发环境预设（宽松 CORS、禁用限流、单 worker）
  - config/prod.py: 生产环境预设（Redis 任务管理、限流、安全校验）
  - 本模块:         基础配置（所有环境共享）

用法：
  1. 直接使用环境变量（推荐）：export LLM_API_KEY=xxx
  2. 导入环境预设：import backend.core.config.dev 或 import backend.core.config.prod
  3. 常量从本模块导入：from backend.core.config import LLM_API_KEY

向后兼容：所有配置常量从子模块重新导出到此命名空间。
新代码推荐直接从子模块导入（如 from backend.core.config.llm import LLM_API_KEY）。
"""

import logging

from backend.core.config.paths import (  # noqa: F401
    DATA_DIR,
    HF_HOME,
    INGESTED_STATE_PATH,
    LOG_DIR,
    MODEL_CACHE_DIR,
    ROOT_DIR,
    UPLOAD_DIR,
    ensure_runtime_directories,
)
from backend.core.config.llm import (  # noqa: F401
    APP_ENV,
    ARK_API_KEY,
    BASE_URL,
    FAST_MODEL,
    GRADE_MODEL,
    LLM_API_KEY,
    LLM_MODEL,
    LLM_PROVIDER,
    LLM_TIMEOUT_SECONDS,
    MAX_LLM_CALLS_PER_QUERY,
    MODEL,
    VERSION,
)
from backend.core.config.embedding import (  # noqa: F401
    DENSE_EMBEDDING_DIM,
    EMBEDDING_DEVICE,
    EMBEDDING_MODEL,
    LOCAL_RERANKER,
    RERANK_API_KEY,
    RERANK_BINDING_HOST,
    RERANK_MODEL,
)
from backend.core.config.database import (  # noqa: F401
    DATABASE_URL,
    DB_MAX_OVERFLOW,
    DB_POOL_SIZE,
    MILVUS_COLLECTION,
    MILVUS_HOST,
    MILVUS_PORT,
    REDIS_CACHE_TTL,
    REDIS_KEY_PREFIX,
    REDIS_URL,
    USE_REDIS_JOB_MANAGER,
)
from backend.core.config.retrieval import (  # noqa: F401
    AUTO_MERGE_ENABLED,
    AUTO_MERGE_THRESHOLD,
    CACHE_MAX_SIZE,
    CACHE_SIM_THRESHOLD,
    CACHE_TTL_SECONDS,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    ENABLE_ACADEMIC_CLEANING,
    ENABLE_CACHE,
    ENABLE_CONTEXT_EXPANSION,
    ENABLE_HYDE,
    ENABLE_STRUCTURAL_CHUNKING,
    EXPAND_MAX_TOTAL_CHUNKS,
    EXPAND_NEXT_PARENT,
    EXPAND_PREV_PARENT,
    LEAF_RETRIEVE_LEVEL,
    MAX_RAG_RETRIES,
    PARSE_MAX_WORKERS,
    RETRIEVAL_COARSE_K,
    RERANK_TOP_N,
    RRF_K,
)
from backend.core.config.auth import (  # noqa: F401
    ADMIN_INVITE_CODE,
    ALLOWED_ORIGINS,
    JWT_ALGORITHM,
    JWT_EXPIRE_MINUTES,
    JWT_REFRESH_EXPIRE_DAYS,
    JWT_SECRET_KEY,
    MIN_PASSWORD_LENGTH,
    PASSWORD_PBKDF2_ROUNDS,
    RATE_LIMIT,
)
from backend.core.config.paths import BM25_STATE_PATH  # noqa: F401

# ── 工具配置 ──────────────────────────────────────────────────────
import os as _os

AMAP_WEATHER_API = _os.getenv("AMAP_WEATHER_API", "https://restapi.amap.com/v3/weather/weatherInfo")
AMAP_API_KEY = _os.getenv("AMAP_API_KEY", "")

MAX_UPLOAD_SIZE_MB = int(_os.getenv("MAX_UPLOAD_SIZE_MB", "100"))
"""上传文件最大大小（MB），默认 100MB。"""

logger = logging.getLogger(__name__)


def is_production() -> bool:
    return APP_ENV in {"prod", "production"}


def validate_config() -> None:
    """启动时校验必填配置，缺失则 fail-fast。"""
    from backend.core.config.llm import LLM_API_KEY, LLM_MODEL  # noqa: F811

    issues = []
    if not LLM_API_KEY:
        issues.append("LLM_API_KEY is not set")
    if not LLM_MODEL:
        issues.append("LLM_MODEL is not set")

    if issues:
        raise RuntimeError(f"Missing required configuration: {'; '.join(issues)}")


def validate_runtime_security() -> None:
    """Validate security-sensitive runtime settings."""
    issues = []
    if JWT_SECRET_KEY == "replace-with-strong-random-secret":
        issues.append("JWT_SECRET_KEY is still using the default placeholder")
    if ADMIN_INVITE_CODE == "paperrag-admin-2026":
        issues.append("ADMIN_INVITE_CODE is still using the default value")
    if ALLOWED_ORIGINS == ["*"]:
        issues.append("ALLOWED_ORIGINS allows every origin")
    if is_production() and not USE_REDIS_JOB_MANAGER:
        issues.append("USE_REDIS_JOB_MANAGER should be enabled for production job recovery")

    if not issues:
        return

    message = "; ".join(issues)
    if is_production():
        raise RuntimeError(f"Unsafe production configuration: {message}")
    logger.warning("Development configuration warning: %s", message)
