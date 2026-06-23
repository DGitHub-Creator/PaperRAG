"""依赖容器 —— 统一的懒加载单例管理器。

所有进程级唯一的重量级实例（embedding 模型、Milvus 客户端、LangGraph graph 等）
统一在此注册和获取，避免模块级导入时立即初始化。

用法:
    from backend.core.dependencies import get_embedding_service, reset_all
    svc = get_embedding_service()
    reset_all()  # 测试时重置所有单例
"""

import threading
from collections.abc import Callable
from typing import Any


class DependencyContainer:
    """线程安全的懒加载依赖容器。

    使用 double-checked locking 确保：
      - 实例只创建一次
      - 并发安全
      - 懒初始化（首次 get 才创建）
    """

    def __init__(self) -> None:
        self._instances: dict[str, Any] = {}
        self._lock = threading.Lock()

    def get_or_create(self, key: str, factory: Callable[[], Any]) -> Any:
        instance = self._instances.get(key)
        if instance is not None:
            return instance
        with self._lock:
            instance = self._instances.get(key)
            if instance is None:
                instance = factory()
                self._instances[key] = instance
        return instance

    def reset(self, key: str | None = None) -> None:
        if key is not None:
            self._instances.pop(key, None)
        else:
            self._instances.clear()


_container = DependencyContainer()


def get_embedding_service():
    from backend.rag.embedding import EmbeddingService
    return _container.get_or_create("embedding_service", EmbeddingService)


def get_milvus_manager():
    from backend.vectordb.milvus_client import MilvusManager
    return _container.get_or_create("milvus_manager", MilvusManager)


def get_parent_chunk_store():
    from backend.rag.parent_chunk_store import ParentChunkStore
    return _container.get_or_create("parent_chunk_store", ParentChunkStore)


def get_rag_graph():
    from backend.rag.rag_pipeline import build_rag_graph
    return _container.get_or_create("rag_graph", build_rag_graph)


def get_grader_model():
    from backend.core.llm import get_chat_model
    return _container.get_or_create("grader_model", lambda: get_chat_model(role="grade"))


def get_router_model():
    from backend.core.llm import get_chat_model
    return _container.get_or_create("router_model", lambda: get_chat_model(role="router"))


def get_stepback_model():
    from backend.core.llm import get_chat_model
    return _container.get_or_create("stepback_model", lambda: get_chat_model(role="stepback"))


def get_local_reranker():
    def _create():
        from sentence_transformers import CrossEncoder

        from backend.core.config import HF_HOME, RERANK_MODEL
        model_name = RERANK_MODEL or "BAAI/bge-reranker-v2-m3"
        return CrossEncoder(model_name, cache_folder=HF_HOME)
    return _container.get_or_create("local_reranker", _create)


def get_conversation_storage():
    from backend.services.conversation_storage import ConversationStorage
    return _container.get_or_create("conversation_storage", ConversationStorage)


def reset_all():
    """重置所有已创建的依赖实例（测试场景使用）。"""
    _container.reset()
