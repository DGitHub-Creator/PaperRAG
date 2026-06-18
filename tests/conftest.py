"""
测试共享 fixtures —— Mock 数据库、Mock Milvus、Test Client。

重要：必须先 patch langchain_huggingface 再 import 任何 backend 模块，
因为 backend.rag.embedding 的模块级代码会实例化 HuggingFaceEmbeddings。
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def _patch_database():
    """Mock database engine to avoid PostgreSQL connection at import time."""
    with patch("backend.core.database.engine"), \
         patch("backend.core.database.SessionLocal"):
        yield


# ── 在 import backend 模块之前拦截 HuggingFace 模型加载 ──
# langchain_huggingface.HuggingFaceEmbeddings 是 backend 的依赖，必须在
# import backend.rag.embedding 之前 patch，避免模型下载阻塞。
_hf_patcher = patch("langchain_huggingface.HuggingFaceEmbeddings", autospec=True)
_mock_hf_cls = _hf_patcher.start()
_mock_hf_instance = MagicMock()
_mock_hf_instance.embed_query.return_value = [0.1] * 1024
_mock_hf_instance.embed_documents.return_value = [[0.1] * 1024]
_mock_hf_cls.return_value = _mock_hf_instance

# 至此 patch 已生效，可以安全 import backend 模块
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def mock_embedding_service():
    """Mock EmbeddingService via the dependency container."""
    mock = MagicMock()
    mock.get_embeddings.return_value = [[0.1] * 1024]
    mock.get_sparse_embedding.return_value = {0: 0.5, 1: 0.3}
    with patch("backend.core.dependencies.get_embedding_service", return_value=mock):
        yield mock


@pytest.fixture
def mock_milvus_manager():
    """Mock MilvusManager via the dependency container."""
    instance = MagicMock()
    instance.init_collection = MagicMock()
    instance.hybrid_retrieve.return_value = [
        {
            "id": 1,
            "text": "This is a test document about secure multiparty computation.",
            "filename": "test.pdf",
            "page_number": 1,
            "chunk_id": "chunk_1",
            "parent_chunk_id": "parent_1",
            "root_chunk_id": "root_1",
            "chunk_level": 3,
            "score": 0.95,
            "parent_idx": 0,
            "child_idx": 0,
            "num_children": 0,
        }
    ]
    instance.dense_retrieve.return_value = []
    instance.query_all.return_value = []
    instance.insert.return_value = None
    instance.delete.return_value = None
    with patch("backend.core.dependencies.get_milvus_manager", return_value=instance):
        yield instance


@pytest.fixture
def mock_parent_chunk_store():
    """Mock ParentChunkStore via the dependency container."""
    instance = MagicMock()
    instance.get_documents_by_ids.return_value = []
    instance.delete_by_filename.return_value = None
    with patch("backend.core.dependencies.get_parent_chunk_store", return_value=instance):
        yield instance


@pytest.fixture
def mock_llm():
    """Mock LLM 调用，返回固定结构化输出。"""
    with patch("langchain.chat_models.init_chat_model") as mock:
        model_instance = MagicMock()
        model_instance.with_structured_output.return_value = model_instance
        model_instance.invoke.return_value = MagicMock(
            binary_score="yes",
            strategy="step_back",
            content="Mock summary",
        )
        mock.return_value = model_instance
        yield mock


@pytest.fixture
def app():
    """创建 FastAPI 测试应用实例。"""
    from backend.app import create_app

    return create_app()


@pytest.fixture
def client(app):
    """FastAPI TestClient（拦截启动时的数据库初始化）。"""
    # app.py 中的 _startup_init_db 使用 from backend.core.database import init_db，
    # 因此需要在 app 自己的命名空间中 patch。
    with patch("backend.app.init_db"):
        with TestClient(app) as c:
            yield c


@pytest.fixture()
def mock_redis():
    """Provide a mock Redis client that stores data in a dict."""
    store = {}

    client = MagicMock()
    client.get.side_effect = lambda k: store.get(k)
    client.setex.side_effect = lambda k, ttl, v: store.__setitem__(k, v)
    client.delete.side_effect = lambda k: store.pop(k, None)
    client.keys.side_effect = lambda p: [k for k in store if k.startswith(p.replace("*", ""))]
    client.ping.return_value = True
    return client


@pytest.fixture()
def mock_milvus():
    """Provide a mock Milvus client."""
    client = MagicMock()
    client.list_collections.return_value = []
    client.search.return_value = []
    return client