from unittest.mock import MagicMock

import pytest

from backend.vectordb.milvus_client import MilvusManager


def test_query_all_reads_past_server_offset_window_and_closes_iterator(monkeypatch):
    client = MagicMock()
    iterator = client.query_iterator.return_value
    iterator.next.side_effect = [[{"chunk_id": str(i)}] * 1000 for i in range(17)] + [[]]
    manager = MilvusManager()
    monkeypatch.setattr(manager, "_get_client", lambda: client)
    assert len(manager.query_all()) == 17000
    iterator.close.assert_called_once()
    client.query.assert_not_called()


def test_query_iterator_is_closed_on_failure(monkeypatch):
    client = MagicMock()
    client.query_iterator.return_value.next.side_effect = RuntimeError("服务错误")
    manager = MilvusManager()
    monkeypatch.setattr(manager, "_get_client", lambda: client)
    with pytest.raises(RuntimeError):
        manager.query_all()
    client.query_iterator.return_value.close.assert_called_once()


@pytest.mark.parametrize("method,args", [("hybrid_retrieve", ([0.1], {1: 0.2})), ("dense_retrieve", ([0.1],))])
def test_search_modes_return_the_same_entity_fields(monkeypatch, method, args):
    client = MagicMock()
    hits = [[{"id": 5, "distance": 0.9, "entity": {"text": "original", "filename": "paper.pdf", "chunk_id": "logical-id"}}]]
    client.search.return_value = hits
    client.hybrid_search.return_value = hits
    manager = MilvusManager()
    monkeypatch.setattr(manager, "_get_client", lambda: client)
    rows = getattr(manager, method)(*args)
    assert rows[0]["text"] == "original"
    assert rows[0]["chunk_id"] == "logical-id"
    assert rows[0]["score"] == 0.9


def test_non_idempotent_insert_is_not_automatically_retried(monkeypatch):
    client = MagicMock()
    client.insert.side_effect = ValueError("closed channel")
    manager = MilvusManager()
    monkeypatch.setattr(manager, "_get_client", lambda: client)
    reset = MagicMock()
    monkeypatch.setattr(manager, "_reset_client", reset)
    with pytest.raises(ValueError, match="closed channel"):
        manager.insert([{"text": "data"}])
    client.insert.assert_called_once()
    reset.assert_called_once_with(client)
