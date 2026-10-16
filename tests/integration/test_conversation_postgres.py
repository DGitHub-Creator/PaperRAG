"""仅在调用方创建的隔离 PostgreSQL 库运行，不使用开发业务库。"""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from backend.core.models import ChatMessage, ChatSession, User
from backend.services import conversation_storage


@pytest.fixture
def storage_db(monkeypatch, isolated_pg_factory):
    factory = isolated_pg_factory
    monkeypatch.setattr(conversation_storage, "SessionLocal", factory)
    username = "refactor_" + uuid4().hex[:16]
    with factory.begin() as db:
        user = User(username=username, password_hash="unusable-test-hash", role="user")
        db.add(user)
        db.flush()
        user_id = user.id
    try:
        yield conversation_storage.ConversationStorage(), factory, username, user_id
    finally:
        with factory.begin() as db:
            db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})


def test_concurrent_turns_preserve_every_message_and_old_citation(storage_db):
    storage, _, username, _ = storage_db
    trace = {"source_map": {"Source 1": {"chunk_id": "original"}}}
    storage.append_turn(username, "same-session", "old-question", "old-answer", trace)
    with ThreadPoolExecutor(max_workers=4) as workers:
        futures = [workers.submit(storage.append_turn, username, "same-session", f"q-{i}", f"a-{i}") for i in range(10)]
        for future in futures:
            future.result()
    messages = storage.get_session_messages(username, "same-session")
    assert len(messages) == 22
    assert messages[1]["rag_trace"] == trace
    for i in range(2, 22, 2):
        assert messages[i]["type"] == "human"
        assert messages[i + 1]["type"] == "ai"
        assert messages[i]["content"][2:] == messages[i + 1]["content"][2:]
    assert storage.list_session_infos(username)[0]["message_count"] == 22


def test_external_delete_is_visible_on_next_read_and_user_isolation_holds(storage_db):
    storage, factory, username, user_id = storage_db
    storage.append_turn(username, "same-session", "question", "answer")
    assert len(storage.load(username, "same-session")) == 2
    assert storage.get_session_messages("someone-else", "same-session") == []
    assert storage.delete_session("someone-else", "same-session") is False
    # 与 Go DeleteSessionForUser 相同的主键范围，绕过 Python 模拟另一个写入方。
    with factory.begin() as db:
        db.execute(text("DELETE FROM chat_sessions WHERE user_id = :uid AND session_id = :sid"), {"uid": user_id, "sid": "same-session"})
    assert storage.load(username, "same-session") == []
    assert storage.list_session_infos(username) == []


def test_failed_turn_rolls_back_both_messages_and_preserves_existing_history(storage_db):
    from sqlalchemy.exc import IntegrityError

    storage, factory, username, _ = storage_db
    storage.append_turn(username, "session", "old", "answer")
    with pytest.raises(IntegrityError):
        storage.append_turn(username, "session", "new", None)
    assert [row["content"] for row in storage.get_session_messages(username, "session")] == ["old", "answer"]
    with factory() as db:
        assert len(db.execute(select(ChatSession)).scalars().all()) >= 1
        assert len(db.execute(select(ChatMessage)).scalars().all()) >= 2
