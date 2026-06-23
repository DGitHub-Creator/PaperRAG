"""对话存储模块 —— 管理用户对话会话的持久化存储（PostgreSQL + Redis 缓存）。

负责用户对话会话的完整生命周期管理：
  - 保存对话：将消息序列化后写入 PostgreSQL，同时更新 Redis 缓存。
  - 加载对话：优先从 Redis 读取，未命中则回源 PostgreSQL 并回填缓存。
  - 列出会话：返回当前用户的所有会话摘要信息。
  - 删除会话：从 PostgreSQL 删除并清除相关 Redis 缓存。

缓存键格式：
  - 消息缓存：chat_messages:{user_id}:{session_id}
  - 会话列表缓存：chat_sessions:{user_id}
"""

from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.core.database import SessionLocal
from backend.core.logging_config import get_logger
from backend.core.models import ChatMessage, ChatSession, User
from backend.services.cache import cache

logger = get_logger(__name__)


class ConversationStorage:
    """对话存储（PostgreSQL + Redis）。"""

    @staticmethod
    def _messages_cache_key(user_id: str, session_id: str) -> str:
        return f"chat_messages:{user_id}:{session_id}"

    @staticmethod
    def _sessions_cache_key(user_id: str) -> str:
        return f"chat_sessions:{user_id}"

    @staticmethod
    def _to_langchain_messages(records: list[dict]) -> list:
        messages = []
        for msg_data in records:
            msg_type = msg_data.get("type")
            content = msg_data.get("content", "")
            if msg_type == "human":
                messages.append(HumanMessage(content=content))
            elif msg_type == "ai":
                messages.append(AIMessage(content=content))
            elif msg_type == "system":
                messages.append(SystemMessage(content=content))
        return messages

    def save(
        self,
        user_id: str,
        session_id: str,
        messages: list,
        metadata: dict = None,
        extra_message_data: list = None,
    ) -> None:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == user_id).first()
            if not user:
                logger.warning("用户 %s 不存在，无法保存对话", user_id)
                return

            session = (
                db.query(ChatSession)
                .filter(ChatSession.user_id == user.id, ChatSession.session_id == session_id)
                .first()
            )
            if not session:
                session = ChatSession(
                    user_id=user.id, session_id=session_id, metadata_json=metadata or {}
                )
                db.add(session)
                db.flush()
            else:
                session.metadata_json = metadata or {}

            db.query(ChatMessage).filter(ChatMessage.session_ref_id == session.id).delete(
                synchronize_session=False
            )

            serialized = []
            now = datetime.utcnow()
            for idx, msg in enumerate(messages):
                rag_trace = None
                if extra_message_data and idx < len(extra_message_data):
                    extra = extra_message_data[idx] or {}
                    rag_trace = extra.get("rag_trace")

                db.add(
                    ChatMessage(
                        session_ref_id=session.id,
                        message_type=msg.type,
                        content=str(msg.content),
                        timestamp=now,
                        rag_trace=rag_trace,
                    )
                )
                serialized.append(
                    {
                        "type": msg.type,
                        "content": str(msg.content),
                        "timestamp": now.isoformat(),
                        "rag_trace": rag_trace,
                    }
                )

            session.updated_at = now
            db.commit()

            cache.set_json(self._messages_cache_key(user_id, session_id), serialized)
            cache.delete(self._sessions_cache_key(user_id))

            logger.debug("对话已保存: user=%s, session=%s, messages=%d", user_id, session_id, len(messages))
        except Exception:
            logger.exception("保存对话失败: user=%s, session=%s", user_id, session_id)
            db.rollback()
        finally:
            db.close()

    def load(self, user_id: str, session_id: str) -> list:
        cached = cache.get_json(self._messages_cache_key(user_id, session_id))
        if cached is not None:
            logger.debug("从缓存加载对话: user=%s, session=%s", user_id, session_id)
            return self._to_langchain_messages(cached)

        records = self.get_session_messages(user_id, session_id)
        cache.set_json(self._messages_cache_key(user_id, session_id), records)
        return self._to_langchain_messages(records)

    def list_sessions(self, user_id: str) -> list:
        return [item["session_id"] for item in self.list_session_infos(user_id)]

    def list_session_infos(self, user_id: str) -> list[dict]:
        cached = cache.get_json(self._sessions_cache_key(user_id))
        if cached is not None:
            return cached

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == user_id).first()
            if not user:
                return []

            sessions = (
                db.query(ChatSession)
                .filter(ChatSession.user_id == user.id)
                .order_by(ChatSession.updated_at.desc())
                .all()
            )
            result = []
            for s in sessions:
                count = (
                    db.query(ChatMessage)
                    .filter(ChatMessage.session_ref_id == s.id)
                    .count()
                )
                result.append(
                    {
                        "session_id": s.session_id,
                        "updated_at": s.updated_at.isoformat(),
                        "message_count": count,
                    }
                )
            cache.set_json(self._sessions_cache_key(user_id), result)
            return result
        except Exception:
            logger.exception("获取会话列表失败: user=%s", user_id)
            return []
        finally:
            db.close()

    def get_session_messages(self, user_id: str, session_id: str) -> list[dict]:
        cached = cache.get_json(self._messages_cache_key(user_id, session_id))
        if cached is not None:
            return cached

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == user_id).first()
            if not user:
                return []
            session = (
                db.query(ChatSession)
                .filter(
                    ChatSession.user_id == user.id, ChatSession.session_id == session_id
                )
                .first()
            )
            if not session:
                return []

            rows = (
                db.query(ChatMessage)
                .filter(ChatMessage.session_ref_id == session.id)
                .order_by(ChatMessage.id.asc())
                .all()
            )
            result = [
                {
                    "type": row.message_type,
                    "content": row.content,
                    "timestamp": row.timestamp.isoformat(),
                    "rag_trace": row.rag_trace,
                }
                for row in rows
            ]
            cache.set_json(self._messages_cache_key(user_id, session_id), result)
            return result
        except Exception:
            logger.exception("获取会话消息失败: user=%s, session=%s", user_id, session_id)
            return []
        finally:
            db.close()

    def delete_session(self, user_id: str, session_id: str) -> bool:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == user_id).first()
            if not user:
                return False
            session = (
                db.query(ChatSession)
                .filter(
                    ChatSession.user_id == user.id, ChatSession.session_id == session_id
                )
                .first()
            )
            if not session:
                return False

            db.delete(session)
            db.commit()

            cache.delete(self._messages_cache_key(user_id, session_id))
            cache.delete(self._sessions_cache_key(user_id))

            logger.info("会话已删除: user=%s, session=%s", user_id, session_id)
            return True
        except Exception:
            logger.exception("删除会话失败: user=%s, session=%s", user_id, session_id)
            db.rollback()
            return False
        finally:
            db.close()
