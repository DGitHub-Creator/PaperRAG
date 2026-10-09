"""PaperRAG 集中配置 —— 统一管理所有模块的配置读取。

环境分层由 ``APP_ENV`` 决定，预设在本模块顶部一次性应用：
  - development（默认）：不启用全局限流，其余取各子模块的安全默认值。
  - production：额外把 ``RATE_LIMIT`` 预设为 60/minute。
所有预设都用 ``setdefault``，显式环境变量始终优先。

用法：
  1. 直接使用环境变量：export LLM_API_KEY=xxx
  2. 常量从本模块导入：from backend.core.config import LLM_API_KEY

向后兼容：所有配置常量从子模块重新导出到此命名空间。
"""

import logging
import os

# .env 必须在任何 os.getenv 之前载入：子配置模块都在 import 期读环境变量。
# 原先 load_dotenv() 挂在 app 的 startup 事件里，那时本模块早已导入完毕，
# .env 对配置层实际无效（只对进程内后续直接读 os.environ 的代码生效）。
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv 未安装时退回纯环境变量

# APP_ENV 只依赖 os，可先于环境预设导入；其余子模块必须在预设之后导入，
# 因为它们在 import 期就读取 os.environ。
from backend.core.config.llm import APP_ENV


def env_presets(app_env: str) -> dict[str, str]:
    """该环境需要补齐的默认环境变量；显式设置的变量始终优先。

    开发环境不启用全局限流（RATE_LIMIT 的代码默认值即为空）。各子模块已有的
    安全默认值（USE_REDIS_JOB_MANAGER 按 APP_ENV 推导、ENABLE_CACHE/ENABLE_HYDE
    为 true、MAX_UPLOAD_SIZE_MB 为 100）不在此重复。
    """
    if app_env in {"prod", "production"}:
        return {"RATE_LIMIT": "60/minute"}
    return {}


for _preset_key, _preset_value in env_presets(APP_ENV).items():
    os.environ.setdefault(_preset_key, _preset_value)

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
    LLM_COST_PER_1K_TOKENS,
    LLM_TIMEOUT_SECONDS,
    MAX_COST_PER_QUERY,
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
    MILVUS_CONNECT_TIMEOUT,
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
    AICORE_INTERNAL_TOKEN,
    ALLOWED_ORIGINS,
    JWT_ALGORITHM,
    JWT_EXPIRE_MINUTES,
    JWT_REFRESH_EXPIRE_DAYS,
    JWT_SECRET_KEY,
    MIN_PASSWORD_LENGTH,
    PASSWORD_PBKDF2_ROUNDS,
    RATE_LIMIT,
    TRUST_PROXY_HEADERS,
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
    """Validate security-sensitive runtime settings.

    ``JWT_SECRET_KEY`` 缺失在**所有**环境下都拒绝启动：令牌签名密钥没有安全的
    兜底值可用（空密钥 python-jose 会静默接受，比可猜测的默认值更危险）。
    其余项在生产环境拒绝启动，在开发环境只告警。
    """
    if not JWT_SECRET_KEY:
        raise RuntimeError(
            "JWT_SECRET_KEY 未配置，拒绝启动。生成一个强随机值后重试: "
            'python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )

    issues = []
    if JWT_SECRET_KEY == "replace-with-strong-random-secret":
        issues.append("JWT_SECRET_KEY is still using the default placeholder")
    if ADMIN_INVITE_CODE == "paperrag-admin-2026":
        issues.append("ADMIN_INVITE_CODE is still using the leaked default value")
    if ALLOWED_ORIGINS == ["*"]:
        issues.append("ALLOWED_ORIGINS allows every origin")
    if is_production() and not USE_REDIS_JOB_MANAGER:
        issues.append("USE_REDIS_JOB_MANAGER should be enabled for production job recovery")
    if is_production() and not AICORE_INTERNAL_TOKEN:
        issues.append("AICORE_INTERNAL_TOKEN 未配置，/internal/v1/ai 会拒绝一切请求（02 §3.5）")

    if not issues:
        if not ADMIN_INVITE_CODE:
            logger.info("ADMIN_INVITE_CODE 未配置，注册接口不能创建管理员账户")
        return

    message = "; ".join(issues)
    if is_production():
        raise RuntimeError(f"Unsafe production configuration: {message}")
    logger.warning("Development configuration warning: %s", message)
