"""
ORM 模型定义 —— 数据库表结构与关联关系。

本模块定义四个核心模型:
  - User:           用户表（用户名、密码哈希、角色）
  - ChatSession:    对话会话表（按用户+会话ID唯一约束）
  - ChatMessage:    对话消息表（人类/AI/系统消息及 RAG 追溯信息）
  - ParentChunk:    父级文档分块表（用于 Auto-merging 检索策略）

所有模型继承自 backend.core.database.Base，遵循 SQLAlchemy 2.0 Mapped 风格。
日志通过 backend.core.logging_config.get_logger 获取标准化 logger。

表结构说明:
  - users 与 chat_sessions 是一对多关系（一个用户可有多个会话）
  - chat_sessions 与 chat_messages 是一对多关系（一个会话包含多条消息）
  - parent_chunks 独立存储，通过 chunk_id 与 Milvus 向量库中的分块关联
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from backend.core.logging_config import get_logger

logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════════════
# User —— 用户表
# ══════════════════════════════════════════════════════════════════════

class User(Base):
    """用户模型 —— 存储登录凭据与角色信息。

    密码使用 PBKDF2-SHA256 哈希存储（格式: pbkdf2_sha256$<rounds>$<salt>$<digest>）。
    角色分为 "user"（普通用户）和 "admin"（管理员），由注册时的邀请码决定。
    """

    __tablename__ = "users"

    # 主键：自增整数 ID
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # 用户名：全局唯一，用于登录和 JWT sub 字段
    username: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    # 密码哈希：PBKDF2-SHA256 格式字符串，最长 255 字符
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # 角色：user 或 admin，默认 user
    role: Mapped[str] = mapped_column(
        String(20), default="user", nullable=False
    )
    # 账户创建时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # 关联：一个用户拥有多个对话会话（级联删除）
    sessions = relationship(
        "ChatSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"


# ══════════════════════════════════════════════════════════════════════
# ChatSession —— 对话会话表
# ══════════════════════════════════════════════════════════════════════

class ChatSession(Base):
    """对话会话模型 —— 记录用户与 AI 的多轮对话会话。

    通过 (user_id, session_id) 联合唯一约束确保同一用户的 session_id 不重复。
    metadata_json 存储前端传来的会话元数据（如标题、标签等自由格式 JSON）。
    updated_at 在每次消息变更时更新，用于排序和展示最近活跃的会话。
    """

    __tablename__ = "chat_sessions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "session_id", name="uq_user_session"
        ),
    )

    # 主键：自增整数 ID
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # 外键 → users.id，删除用户时级联删除其所有会话
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 会话标识符：前端生成的唯一 session ID（如 UUID）
    session_id: Mapped[str] = mapped_column(
        String(120), nullable=False, index=True
    )
    # 会话元数据：JSON 自由格式，存储标题、标签、模型参数等
    metadata_json: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False
    )
    # 最后更新时间：每次新增或修改消息时更新
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    # 会话创建时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # 关联回 User 模型（多对一）
    user = relationship("User", back_populates="sessions")
    # 关联：一个会话包含多条消息（级联删除）
    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ChatSession(id={self.id}, session_id='{self.session_id}', user_id={self.user_id})>"


# ══════════════════════════════════════════════════════════════════════
# ChatMessage —— 对话消息表
# ══════════════════════════════════════════════════════════════════════

class ChatMessage(Base):
    """对话消息模型 —— 存储单条对话消息（人类/AI/系统）。

    message_type 取值:
      - "human":   用户发送的消息
      - "ai":      AI 生成的回复
      - "system":  系统级消息（如预设指令）

    rag_trace 记录 RAG 检索追溯信息（JSON 格式），包含:
      - 检索到的文档分块 ID 列表
      - 各分块的相似度分数
      - 检索策略标识（hybrid/dense/keyword 等）
    """

    __tablename__ = "chat_messages"

    # 主键：自增整数 ID
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # 外键 → chat_sessions.id，删除会话时级联删除其所有消息
    session_ref_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 消息类型：human / ai / system
    message_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    # 消息正文：存储完整文本内容
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 消息时间戳
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    # RAG 检索追溯信息：JSON 字段，可为 null（非 RAG 消息）
    rag_trace: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 关联回 ChatSession 模型（多对一）
    session = relationship("ChatSession", back_populates="messages")

    def __repr__(self) -> str:
        return (
            f"<ChatMessage(id={self.id}, type='{self.message_type}', "
            f"session_ref_id={self.session_ref_id})>"
        )


# ══════════════════════════════════════════════════════════════════════
# ParentChunk —— 父级文档分块表
# ══════════════════════════════════════════════════════════════════════

class ParentChunk(Base):
    """父级文档分块模型 —— 存储文档的层级化分块信息。

    用于 Auto-merging 检索策略:
      - 文档首先被切割为不同层级的分块（level 0 = 叶节点，level 1 = 父节点，...）。
      - 检索时从小分块（叶节点）召回，当同一父块下的召回数超过阈值时，
        自动将子分块替换为父分块（更大的上下文窗口）。
      - 该表存储父块的全量文本，Milvus 向量库存储所有层级分块的向量，
        通过 chunk_id 进行关联。

    chunk_level 层级示例:
      0  → 最细粒度子分块（如 200 tokens）
      1  → 合并后的父分块（如 600 tokens）
      2  → 根级分块（如 2000 tokens）

    parent_chunk_id 和 root_chunk_id 构建树状层级关系，
    chunk_idx 用于同级别分块排序。
    """

    __tablename__ = "parent_chunks"

    # 主键：全局唯一的分块 ID（UUID 或 hash）
    chunk_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    # 分块文本内容（完整文本，不限长度）
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # 所属文件名（建立索引，方便按文件筛选/删除分块）
    filename: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    # 文件类型（如 pdf、txt、md 等）
    file_type: Mapped[str] = mapped_column(
        String(50), default="", nullable=False
    )
    # 文件在服务器上的完整路径
    file_path: Mapped[str] = mapped_column(
        String(1024), default="", nullable=False
    )
    # PDF 页码（非 PDF 文件为 0）
    page_number: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    # 直属父分块 ID（空字符串表示根节点）
    parent_chunk_id: Mapped[str] = mapped_column(
        String(512), default="", nullable=False
    )
    # 最顶层根分块 ID（用于快速定位整棵分块树）
    root_chunk_id: Mapped[str] = mapped_column(
        String(512), default="", nullable=False
    )
    # 分块层级: 0 = 叶节点, 1 = 父节点, 2+ = 更上层
    chunk_level: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    # 同层级内的顺序索引（用于保持原文顺序）
    chunk_idx: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    # 最后更新时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<ParentChunk(chunk_id='{self.chunk_id[:16]}...', "
            f"filename='{self.filename}', level={self.chunk_level}, idx={self.chunk_idx})>"
        )
