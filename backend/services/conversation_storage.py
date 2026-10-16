"""PostgreSQL 对话存储：按轮追加，不缓存跨服务共同修改的会话。"""

from datetime import UTC, datetime

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from backend.core.database import SessionLocal
from backend.core.models import ChatMessage, ChatSession, User


class ConversationStorage:
    @staticmethod
    def _to_langchain_messages(records: list[dict]) -> list:
        types = {"human": HumanMessage, "ai": AIMessage, "system": SystemMessage}
        return [types[row["type"]](content=row.get("content", "")) for row in records if row.get("type") in types]

    def append_turn(self, user_id: str, session_id: str, question: str, answer: str, rag_trace: dict | None = None) -> None:
        """事务内追加一轮；唯一键 UPSERT 串行化同一会话的并发写，保留旧消息与引用。"""
        with SessionLocal() as db, db.begin():
            user = db.execute(select(User.id).where(User.username == user_id)).scalar_one_or_none()
            if user is None:
                raise ValueError("用户不存在，无法保存对话")
            # 旧表是 naive UTC，只在现有列的边界去掉时区，不重解释历史时间。
            now = datetime.now(UTC).replace(tzinfo=None)
            statement = insert(ChatSession).values(
                user_id=user, session_id=session_id, metadata_json={}, created_at=now, updated_at=now,
            ).on_conflict_do_update(
                constraint="uq_user_session", set_={"updated_at": now},
            ).returning(ChatSession.id)
            session_ref_id = db.execute(statement).scalar_one()
            db.add_all([
                ChatMessage(session_ref_id=session_ref_id, message_type="human", content=question, timestamp=now),
                ChatMessage(session_ref_id=session_ref_id, message_type="ai", content=answer, timestamp=now, rag_trace=rag_trace),
            ])

    def load(self, user_id: str, session_id: str) -> list:
        return self._to_langchain_messages(self.get_session_messages(user_id, session_id))

    def list_sessions(self, user_id: str) -> list[str]:
        return [row["session_id"] for row in self.list_session_infos(user_id)]

    def list_session_infos(self, user_id: str) -> list[dict]:
        # 一次聚合代替每会话一次 COUNT，空会话也必须出现在列表中。
        statement = (
            select(ChatSession.session_id, ChatSession.updated_at, func.count(ChatMessage.id))
            .join(User, User.id == ChatSession.user_id)
            .outerjoin(ChatMessage, ChatMessage.session_ref_id == ChatSession.id)
            .where(User.username == user_id)
            .group_by(ChatSession.id)
            .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
        )
        with SessionLocal() as db:
            return [
                {"session_id": sid, "updated_at": updated.isoformat(), "message_count": count}
                for sid, updated, count in db.execute(statement).all()
            ]

    def get_session_messages(self, user_id: str, session_id: str) -> list[dict]:
        statement = (
            select(ChatMessage.message_type, ChatMessage.content, ChatMessage.timestamp, ChatMessage.rag_trace)
            .join(ChatSession, ChatSession.id == ChatMessage.session_ref_id)
            .join(User, User.id == ChatSession.user_id)
            .where(User.username == user_id, ChatSession.session_id == session_id)
            .order_by(ChatMessage.id)
        )
        with SessionLocal() as db:
            return [
                {"type": kind, "content": content, "timestamp": timestamp.isoformat(), "rag_trace": trace}
                for kind, content, timestamp, trace in db.execute(statement).all()
            ]

    def delete_session(self, user_id: str, session_id: str) -> bool:
        statement = delete(ChatSession).where(
            ChatSession.user_id.in_(select(User.id).where(User.username == user_id)),
            ChatSession.session_id == session_id,
        )
        with SessionLocal() as db, db.begin():
            return db.execute(statement).rowcount > 0
