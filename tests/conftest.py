"""Shared test fixtures for PaperRAG test suite.

Provides isolated fixtures that don't require real infrastructure.
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
