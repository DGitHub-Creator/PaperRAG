"""Agent 模块单元测试 —— ConversationStorage 消息持久化与缓存。"""

from unittest.mock import MagicMock, patch


class TestConversationStorageCacheKeys:
    def setup_method(self):
        from backend.services.agent import ConversationStorage
        self.store = ConversationStorage

    def test_messages_cache_key(self):
        key = self.store._messages_cache_key("alice", "sess1")
        assert key == "chat_messages:alice:sess1"

    def test_sessions_cache_key(self):
        key = self.store._sessions_cache_key("alice")
        assert key == "chat_sessions:alice"


class TestConversationStorageSave:
    def test_save_new_session(self):
        from backend.services.agent import ConversationStorage
        from langchain_core.messages import HumanMessage

        store = ConversationStorage()
        db = MagicMock()

        # query User → found
        user = MagicMock()
        user.id = 1
        # query ChatSession → None (new session)
        session_filter = MagicMock()
        session_filter.first.return_value = None
        user_filter = MagicMock()
        user_filter.first.return_value = user

        def query_side_effect(model):
            name = getattr(model, '__name__', '')
            if name == 'User':
                q = MagicMock()
                q.filter.return_value = user_filter
                return q
            if name == 'ChatSession':
                q = MagicMock()
                q.filter.return_value = session_filter
                return q
            # ChatMessage delete query
            q = MagicMock()
            q.filter.return_value = MagicMock()
            return q

        db.query.side_effect = query_side_effect
        db.add = MagicMock()
        db.flush = MagicMock()
        db.commit = MagicMock()
        db.close = MagicMock()

        with (
            patch("backend.services.agent.SessionLocal", return_value=db),
            patch.object(store, "_messages_cache_key", return_value="cache:k"),
            patch.object(store, "_sessions_cache_key", return_value="cache:sk"),
            patch("backend.services.agent.cache"),
        ):
            store.save(
                user_id="alice",
                session_id="sess1",
                messages=[HumanMessage(content="Hello")],
            )
            db.commit.assert_called_once()


class TestConversationStorageLoad:
    def test_load_from_redis(self):
        from backend.services.agent import ConversationStorage

        store = ConversationStorage()
        cache_mock = MagicMock()
        cache_mock.get_json.return_value = [{"type": "human", "content": "Hello"}]

        with (
            patch("backend.services.agent.cache", cache_mock),
            patch.object(store, "_messages_cache_key", return_value="cache:k"),
        ):
            result = store.load("alice", "sess1")
            assert len(result) == 1
            assert result[0].content == "Hello"

    def test_load_empty_session(self):
        from backend.services.agent import ConversationStorage

        store = ConversationStorage()
        cache_mock = MagicMock()
        cache_mock.get_json.return_value = None
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []
        db.close = MagicMock()

        with (
            patch("backend.services.agent.cache", cache_mock),
            patch("backend.services.agent.SessionLocal", return_value=db),
            patch.object(store, "_messages_cache_key", return_value="cache:k"),
        ):
            result = store.load("alice", "empty_sess")
            assert result == []


class TestConversationStorageList:
    def test_list_sessions(self):
        from backend.services.agent import ConversationStorage
        import backend.services.agent as agent_mod

        store = ConversationStorage()
        user = MagicMock()
        user.id = 1
        session_record = MagicMock()
        session_record.id = 100
        session_record.session_id = "sess1"
        session_record.updated_at = MagicMock()
        session_record.updated_at.isoformat.return_value = "2026-06-16T12:00:00"

        db = MagicMock()
        q_user = MagicMock()
        q_user.filter.return_value = MagicMock(first=MagicMock(return_value=user))

        q_session = MagicMock()
        q_session.filter.return_value = q_session
        q_session.order_by.return_value = MagicMock(all=MagicMock(return_value=[session_record]))

        q_msg = MagicMock()
        q_msg.filter.return_value = MagicMock(count=MagicMock(return_value=5))

        call_log = []
        def query_side_effect(*args):
            call_log.append(args)
            if args and args[0] is agent_mod.User:
                return q_user
            if args and args[0] is agent_mod.ChatSession:
                return q_session
            if args and args[0] is agent_mod.ChatMessage:
                return q_msg
            return MagicMock()

        db.query.side_effect = query_side_effect
        db.close = MagicMock()

        with (
            patch("backend.services.agent.SessionLocal", return_value=db),
            patch.object(store, "_sessions_cache_key", return_value="cache:sk"),
            patch("backend.services.agent.cache") as cache_mock,
        ):
            cache_mock.get_json.return_value = None
            infos = store.list_session_infos("alice")
            assert len(call_log) > 0, f"No query calls made. infos={infos}"
            assert len(infos) == 1, f"infos={infos}, calls={call_log}"
            assert infos[0]["session_id"] == "sess1"

    def test_delete_session_exists(self):
        from backend.services.agent import ConversationStorage

        store = ConversationStorage()
        db = MagicMock()
        session = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = session
        db.delete = MagicMock()

        with (
            patch("backend.services.agent.SessionLocal", return_value=db),
            patch.object(store, "_messages_cache_key", return_value="cache:k"),
            patch.object(store, "_sessions_cache_key", return_value="cache:sk"),
            patch("backend.services.agent.cache"),
        ):
            result = store.delete_session("alice", "sess1")
            assert result is True

    def test_delete_session_not_found(self):
        from backend.services.agent import ConversationStorage

        store = ConversationStorage()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with patch("backend.services.agent.SessionLocal", return_value=db):
            result = store.delete_session("alice", "nonexistent")
            assert result is False


class TestToLangchainMessages:
    def test_human_message(self):
        from backend.services.agent import ConversationStorage
        from langchain_core.messages import HumanMessage

        result = ConversationStorage._to_langchain_messages(
            [{"type": "human", "content": "Hello"}]
        )
        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)
        assert result[0].content == "Hello"

    def test_ai_message(self):
        from backend.services.agent import ConversationStorage
        from langchain_core.messages import AIMessage

        result = ConversationStorage._to_langchain_messages(
            [{"type": "ai", "content": "Hi there"}]
        )
        assert len(result) == 1
        assert isinstance(result[0], AIMessage)

    def test_system_message(self):
        from backend.services.agent import ConversationStorage
        from langchain_core.messages import SystemMessage

        result = ConversationStorage._to_langchain_messages(
            [{"type": "system", "content": "Be helpful"}]
        )
        assert len(result) == 1
        assert isinstance(result[0], SystemMessage)

    def test_unknown_type_skipped(self):
        from backend.services.agent import ConversationStorage

        result = ConversationStorage._to_langchain_messages(
            [{"type": "unknown", "content": "???"}]
        )
        assert len(result) == 0
