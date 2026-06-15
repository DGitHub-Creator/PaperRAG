"""PaperRAG 集中配置 —— 所有常量、路径、模型参数均在此定义。

环境变量可覆盖硬编码默认值，方便部署切换。
统一管理所有模块的配置读取，避免分散在各文件中的 os.getenv 调用。
"""

import os
import sys
from pathlib import Path

# ── 项目元信息 ────────────────────────────────────────────────────
VERSION = "0.1.0"
"""应用版本号，用于健康检查和 API 响应。"""

# ── 项目路径 ──────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
UPLOAD_DIR = DATA_DIR / "documents"
LOG_DIR = ROOT_DIR / "logs"

MODEL_CACHE_DIR = ROOT_DIR / "models"
"""HuggingFace 模型缓存目录（默认项目根目录下的 models/）。

sentence_transformers / transformers 会优先从此目录加载模型缓存，
避免每次启动从 HuggingFace Hub 重新下载。

可通过 HF_HOME 环境变量覆盖。"""
HF_HOME = os.getenv("HF_HOME", str(MODEL_CACHE_DIR))

for _dir in (DATA_DIR, UPLOAD_DIR, LOG_DIR, MODEL_CACHE_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# ── LLM 模型配置（统一前缀，向后兼容旧变量）─────────────────────────
ARK_API_KEY = os.getenv("ARK_API_KEY", "")
MODEL = os.getenv("MODEL", "")
GRADE_MODEL = os.getenv("GRADE_MODEL", "gpt-4.1")
FAST_MODEL = os.getenv("FAST_MODEL", "")
BASE_URL = os.getenv("BASE_URL", "")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", os.getenv("MODEL_PROVIDER", "openai"))
"""LLM 提供商标识，如 openai / deepseek / anthropic / ollama 等。"""
LLM_API_KEY = os.getenv("LLM_API_KEY", "") or ARK_API_KEY
"""LLM API Key。默认为空，fallback 到 ARK_API_KEY。"""
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "") or BASE_URL
"""LLM API 基础 URL。fallback 到 BASE_URL。"""
LLM_MODEL = os.getenv("LLM_MODEL", "") or MODEL
"""默认 LLM 模型名。用于 agent、router、stepback。fallback 到 MODEL。"""
LLM_GRADE_MODEL = os.getenv("LLM_GRADE_MODEL", "") or GRADE_MODEL
"""评分专用模型名，通常为更强模型。fallback 到 GRADE_MODEL。"""

# ── 嵌入模型配置 ──────────────────────────────────────────────────
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")
DENSE_EMBEDDING_DIM = int(os.getenv("DENSE_EMBEDDING_DIM", "1024"))

# ── Rerank 配置（双轨：Jina API + 本地 BGE-Reranker）────────────────
RERANK_MODEL = os.getenv("RERANK_MODEL", "")
RERANK_BINDING_HOST = os.getenv("RERANK_BINDING_HOST", "")
RERANK_API_KEY = os.getenv("RERANK_API_KEY", "")
LOCAL_RERANKER = os.getenv("LOCAL_RERANKER", "false").lower() == "true"

# ── Milvus 向量库 ─────────────────────────────────────────────────
MILVUS_HOST = os.getenv("MILVUS_HOST", "127.0.0.1")
MILVUS_PORT = os.getenv("MILVUS_PORT", "19530")
MILVUS_COLLECTION = os.getenv("MILVUS_COLLECTION", "embeddings_collection")

# ── 数据库 / Redis ────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/langchain_app",
)
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
"""数据库连接池大小，默认 10。"""
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
"""数据库连接池最大溢出数，默认 20。"""
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "paperrag")
REDIS_CACHE_TTL = int(os.getenv("REDIS_CACHE_TTL_SECONDS", "300"))
USE_REDIS_JOB_MANAGER = os.getenv("USE_REDIS_JOB_MANAGER", "false").lower() == "true"
"""是否使用 Redis 任务管理器（替代进程内存，支持多 worker）。"""

# ── CORS 与安全 ──────────────────────────────────────────────────
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = (
    ["*"]
    if _raw_origins == "*"
    else [o.strip() for o in _raw_origins.split(",")]
)
"""CORS 允许的来源。逗号分隔列表，或 * 表示全部允许（开发模式）。"""

# ── 认证配置 ──────────────────────────────────────────────────────
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "replace-with-strong-random-secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))
ADMIN_INVITE_CODE = os.getenv("ADMIN_INVITE_CODE", "paperrag-admin-2026")
PASSWORD_PBKDF2_ROUNDS = int(os.getenv("PASSWORD_PBKDF2_ROUNDS", "310000"))
MIN_PASSWORD_LENGTH = int(os.getenv("MIN_PASSWORD_LENGTH", "8"))
"""密码最小长度，默认 8。设为 0 可禁用检查（开发环境）。"""

# ── BM25 稀疏统计 ─────────────────────────────────────────────────
BM25_STATE_PATH = os.getenv("BM25_STATE_PATH", str(DATA_DIR / "bm25_state.json"))

# ── 文档解析配置 ──────────────────────────────────────────────────
PARSE_MAX_WORKERS = int(os.getenv("PARSE_MAX_WORKERS", "4"))
ENABLE_ACADEMIC_CLEANING = os.getenv("ENABLE_ACADEMIC_CLEANING", "true").lower() != "false"
ENABLE_STRUCTURAL_CHUNKING = os.getenv("ENABLE_STRUCTURAL_CHUNKING", "true").lower() != "false"
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))

# ── 检索参数 ──────────────────────────────────────────────────────
RETRIEVAL_COARSE_K = int(os.getenv("COARSE_K", "30"))
RERANK_TOP_N = int(os.getenv("RERANK_TOP_N", "5"))
AUTO_MERGE_ENABLED = os.getenv("AUTO_MERGE_ENABLED", "true").lower() != "false"
AUTO_MERGE_THRESHOLD = int(os.getenv("AUTO_MERGE_THRESHOLD", "2"))
LEAF_RETRIEVE_LEVEL = int(os.getenv("LEAF_RETRIEVE_LEVEL", "3"))
RRF_K = float(os.getenv("RRF_K", "60"))

# ── 上下文扩展配置 ────────────────────────────────────────────────
ENABLE_CONTEXT_EXPANSION = os.getenv("ENABLE_CONTEXT_EXPANSION", "true").lower() != "false"
EXPAND_PREV_PARENT = int(os.getenv("EXPAND_PREV_PARENT", "1"))
EXPAND_NEXT_PARENT = int(os.getenv("EXPAND_NEXT_PARENT", "1"))
EXPAND_MAX_TOTAL_CHUNKS = int(os.getenv("EXPAND_MAX_TOTAL_CHUNKS", "30"))

# ── 多轮检索 ────────────────────────────────────────────────────────
MAX_RAG_RETRIES = int(os.getenv("MAX_RAG_RETRIES", "3"))
"""RAG 多轮检索最大重试次数（grade → rewrite → retrieve 循环），默认 3 次。"""

# ── HyDE 配置 ─────────────────────────────────────────────────────
ENABLE_HYDE = os.getenv("ENABLE_HYDE", "true").lower() != "false"

# ── 语义缓存配置 ──────────────────────────────────────────────────
ENABLE_CACHE = os.getenv("ENABLE_CACHE", "true").lower() != "false"
CACHE_MAX_SIZE = int(os.getenv("CACHE_MAX_SIZE", "500"))
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "604800"))
CACHE_SIM_THRESHOLD = float(os.getenv("CACHE_SIM_THRESHOLD", "0.92"))

# ── 增量导入状态追踪 ──────────────────────────────────────────────
INGESTED_STATE_PATH = DATA_DIR / "ingested.json"

# ── 工具配置 ──────────────────────────────────────────────────────
AMAP_WEATHER_API = os.getenv("AMAP_WEATHER_API", "https://restapi.amap.com/v3/weather/weatherInfo")
AMAP_API_KEY = os.getenv("AMAP_API_KEY", "")
