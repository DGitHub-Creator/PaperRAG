"""检索参数配置。"""

import os

RETRIEVAL_COARSE_K = int(os.getenv("COARSE_K", "30"))
RERANK_TOP_N = int(os.getenv("RERANK_TOP_N", "5"))
AUTO_MERGE_ENABLED = os.getenv("AUTO_MERGE_ENABLED", "true").lower() != "false"
AUTO_MERGE_THRESHOLD = int(os.getenv("AUTO_MERGE_THRESHOLD", "2"))
LEAF_RETRIEVE_LEVEL = int(os.getenv("LEAF_RETRIEVE_LEVEL", "3"))
RRF_K = float(os.getenv("RRF_K", "60"))

ENABLE_CONTEXT_EXPANSION = os.getenv("ENABLE_CONTEXT_EXPANSION", "true").lower() != "false"
EXPAND_PREV_PARENT = int(os.getenv("EXPAND_PREV_PARENT", "1"))
EXPAND_NEXT_PARENT = int(os.getenv("EXPAND_NEXT_PARENT", "1"))
EXPAND_MAX_TOTAL_CHUNKS = int(os.getenv("EXPAND_MAX_TOTAL_CHUNKS", "30"))

MAX_RAG_RETRIES = int(os.getenv("MAX_RAG_RETRIES", "3"))
ENABLE_HYDE = os.getenv("ENABLE_HYDE", "true").lower() != "false"

ENABLE_CACHE = os.getenv("ENABLE_CACHE", "true").lower() != "false"
CACHE_MAX_SIZE = int(os.getenv("CACHE_MAX_SIZE", "500"))
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "604800"))
CACHE_SIM_THRESHOLD = float(os.getenv("CACHE_SIM_THRESHOLD", "0.92"))
