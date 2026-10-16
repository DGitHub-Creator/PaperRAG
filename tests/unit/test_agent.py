"""对话存储的边界验证；并发、引用保留和跨服务删除在真库验收。"""

from unittest.mock import MagicMock

import pytest

from backend.services import conversation_storage
from backend.services.conversation_storage import ConversationStorage


@pytest.fixture
def db(monkeypatch):
    session = MagicMock()
    session.__enter__.return_value = session
    monkeypatch.setattr(conversation_storage, "SessionLocal", lambda: session)
    return session


def test_append_turn_uses_transaction_and_preserves_trace(db):
    db.execute.side_effect = [MagicMock(scalar_one_or_none=lambda: 1), MagicMock(scalar_one=lambda: 5)]
    trace = {"tool_used": True, "tool_name": "search_knowledge_base", "source_map": {"Source 1": {"chunk_id": "old"}}}
    ConversationStorage().append_turn("alice", "session", "question", "answer", trace)
    messages = db.add_all.call_args.args[0]
    assert [(row.message_type, row.content) for row in messages] == [("human", "question"), ("ai", "answer")]
    assert messages[1].rag_trace == trace
    db.begin.assert_called_once()
    db.__exit__.assert_called_once()


def test_missing_user_is_a_write_failure(db):
    db.execute.return_value.scalar_one_or_none.return_value = None
    with pytest.raises(ValueError, match="用户不存在"):
        ConversationStorage().append_turn("missing", "session", "question", "answer")
    db.add_all.assert_not_called()


def test_new_invalid_trace_is_rejected_before_database_write(db):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ConversationStorage().append_turn("alice", "session", "q", "a", {"query": "q"})
    db.begin.assert_not_called()
    db.execute.assert_not_called()


@pytest.mark.parametrize("method,args", [
    ("list_session_infos", ("alice",)),
    ("get_session_messages", ("alice", "session")),
    ("delete_session", ("alice", "session")),
])
def test_database_errors_propagate_and_release_session(db, method, args):
    db.execute.side_effect = RuntimeError("database unavailable")
    with pytest.raises(RuntimeError, match="database unavailable"):
        getattr(ConversationStorage(), method)(*args)
    db.__exit__.assert_called_once()


def test_delete_missing_or_other_user_returns_false(db):
    db.execute.return_value.rowcount = 0
    assert ConversationStorage().delete_session("alice", "other-session") is False


class TestToLangchainMessages:
    def test_human_message(self):
        from langchain_core.messages import HumanMessage

        from backend.services.conversation_storage import ConversationStorage

        result = ConversationStorage._to_langchain_messages(
            [{"type": "human", "content": "Hello"}]
        )
        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)
        assert result[0].content == "Hello"

    def test_ai_message(self):
        from langchain_core.messages import AIMessage

        from backend.services.conversation_storage import ConversationStorage

        result = ConversationStorage._to_langchain_messages(
            [{"type": "ai", "content": "Hi there"}]
        )
        assert len(result) == 1
        assert isinstance(result[0], AIMessage)

    def test_system_message(self):
        from langchain_core.messages import SystemMessage

        from backend.services.conversation_storage import ConversationStorage

        result = ConversationStorage._to_langchain_messages(
            [{"type": "system", "content": "Be helpful"}]
        )
        assert len(result) == 1
        assert isinstance(result[0], SystemMessage)

    def test_unknown_type_skipped(self):
        from backend.services.conversation_storage import ConversationStorage

        result = ConversationStorage._to_langchain_messages(
            [{"type": "unknown", "content": "???"}]
        )
        assert len(result) == 0
