"""嵌入模型配置。"""

import os

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")
DENSE_EMBEDDING_DIM = int(os.getenv("DENSE_EMBEDDING_DIM", "1024"))

RERANK_MODEL = os.getenv("RERANK_MODEL", "")
RERANK_BINDING_HOST = os.getenv("RERANK_BINDING_HOST", "")
RERANK_API_KEY = os.getenv("RERANK_API_KEY", "")
LOCAL_RERANKER = os.getenv("LOCAL_RERANKER", "false").lower() == "true"
