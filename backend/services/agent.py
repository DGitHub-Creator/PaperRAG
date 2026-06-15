"""
智能体模块 —— 对话管理、Agent 创建、同步/流式对话接口。

本模块是 PaperRAG 的对话核心，负责：
  1. 管理用户对话会话的持久化存储（PostgreSQL + Redis 缓存）
  2. 创建和配置 LangChain Agent 实例（含工具绑定与系统提示词）
  3. 提供同步对话接口（chat_with_agent）
  4. 提供流式对话接口（chat_with_agent_stream），通过 asyncio.Queue
     实现 Agent 输出与 RAG 检索步骤的统一事件流

架构说明：
  - ConversationStorage 将对话消息存储到 PostgreSQL，同时写入 Redis 缓存。
    加载时优先读 Redis，未命中时回源 PostgreSQL 并回填缓存。
  - Agent 实例在模块加载时创建，使用 init_chat_model 配置 LLM，
    绑定 search_knowledge_base 和 get_current_weather 两个工具。
  - 流式接口使用 asyncio.Queue 作为统一输出管道，RAG 步骤通过
    跨线程安全的 call_soon_threadsafe 实时推入同一队列。
"""

import asyncio
import json
from datetime import datetime

from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage, AIMessageChunk, SystemMessage

from backend.core.config import ARK_API_KEY, MODEL, BASE_URL
from backend.core.database import SessionLocal
from backend.core.logging_config import get_logger
from backend.core.models import User, ChatSession, ChatMessage
from backend.services.cache import cache
from backend.services.tools import (
    get_current_weather,
    search_knowledge_base,
    get_last_rag_context,
    reset_tool_call_guards,
    set_rag_step_queue,
)

logger = get_logger(__name__)


class ConversationStorage:
    """对话存储（PostgreSQL + Redis）。

    负责用户对话会话的完整生命周期管理：
      - 保存对话：将消息序列化后写入 PostgreSQL，同时更新 Redis 缓存。
      - 加载对话：优先从 Redis 读取，未命中则回源 PostgreSQL 并回填缓存。
      - 列出会话：返回当前用户的所有会话摘要信息。
      - 删除会话：从 PostgreSQL 删除并清除相关 Redis 缓存。

    缓存键格式：
      - 消息缓存：chat_messages:{user_id}:{session_id}
      - 会话列表缓存：chat_sessions:{user_id}
    """

    @staticmethod
    def _messages_cache_key(user_id: str, session_id: str) -> str:
        """生成消息列表的 Redis 缓存键。

        Args:
            user_id: 用户名。
            session_id: 会话 ID。

        Returns:
            Redis 缓存键字符串，格式为 "chat_messages:{user_id}:{session_id}"。
        """
        return f"chat_messages:{user_id}:{session_id}"

    @staticmethod
    def _sessions_cache_key(user_id: str) -> str:
        """生成用户会话列表的 Redis 缓存键。

        Args:
            user_id: 用户名。

        Returns:
            Redis 缓存键字符串，格式为 "chat_sessions:{user_id}"。
        """
        return f"chat_sessions:{user_id}"

    @staticmethod
    def _to_langchain_messages(records: list[dict]) -> list:
        """将数据库/缓存中的消息字典列表转换为 LangChain Message 对象列表。

        根据消息类型字段 'type' 映射到对应的 LangChain 消息类：
          - "human"  -> HumanMessage
          - "ai"     -> AIMessage
          - "system" -> SystemMessage

        Args:
            records: 从数据库或 Redis 中读取的消息字典列表，
                     每个字典包含 'type' 和 'content' 字段。

        Returns:
            LangChain Message 对象（HumanMessage / AIMessage / SystemMessage）构成的列表。
        """
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
        """保存完整对话到 PostgreSQL 并更新 Redis 缓存。

        操作步骤：
          1. 查找或创建对应的 User 和 ChatSession 记录。
          2. 清除该会话的旧消息，写入新消息列表。
          3. 同步更新 Redis 缓存（消息缓存 + 清除会话列表缓存）。

        Args:
            user_id: 用户名。
            session_id: 会话 ID。
            messages: LangChain Message 对象列表。
            metadata: 可选的会话元数据（JSON 可序列化字典）。
            extra_message_data: 可选列表，与 messages 一一对应，
                                每个元素可包含 'rag_trace' 等额外信息。
        """
        db = SessionLocal()
        try:
            # 查找或创建用户
            user = db.query(User).filter(User.username == user_id).first()
            if not user:
                logger.warning("用户 %s 不存在，无法保存对话", user_id)
                return

            # 查找或创建会话
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

            # 清除旧消息
            db.query(ChatMessage).filter(ChatMessage.session_ref_id == session.id).delete(
                synchronize_session=False
            )

            # 写入新消息
            serialized = []
            now = datetime.utcnow()
            for idx, msg in enumerate(messages):
                # 提取额外的 RAG trace 信息
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

            # 更新 Redis 缓存
            cache.set_json(self._messages_cache_key(user_id, session_id), serialized)
            cache.delete(self._sessions_cache_key(user_id))

            logger.debug("对话已保存: user=%s, session=%s, messages=%d", user_id, session_id, len(messages))
        except Exception:
            logger.exception("保存对话失败: user=%s, session=%s", user_id, session_id)
            db.rollback()
        finally:
            db.close()

    def load(self, user_id: str, session_id: str) -> list:
        """加载指定会话的完整对话历史。

        优先从 Redis 读取，未命中时回源 PostgreSQL 并回填缓存。

        Args:
            user_id: 用户名。
            session_id: 会话 ID。

        Returns:
            LangChain Message 对象列表。
        """
        # 优先从 Redis 缓存读取
        cached = cache.get_json(self._messages_cache_key(user_id, session_id))
        if cached is not None:
            logger.debug("从缓存加载对话: user=%s, session=%s", user_id, session_id)
            return self._to_langchain_messages(cached)

        # 回源数据库
        records = self.get_session_messages(user_id, session_id)
        cache.set_json(self._messages_cache_key(user_id, session_id), records)
        return self._to_langchain_messages(records)

    def list_sessions(self, user_id: str) -> list:
        """列出用户的所有会话 ID。

        Args:
            user_id: 用户名。

        Returns:
            会话 ID 字符串列表。
        """
        return [item["session_id"] for item in self.list_session_infos(user_id)]

    def list_session_infos(self, user_id: str) -> list[dict]:
        """获取用户的所有会话摘要信息（含消息计数和更新时间）。

        优先从 Redis 读取，未命中则查询 PostgreSQL 并缓存结果。

        Args:
            user_id: 用户名。

        Returns:
            字典列表，每个字典包含 session_id、updated_at、message_count。
        """
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
        """从数据库查询指定会话的所有消息（字典格式）。

        结果也会缓存到 Redis。

        Args:
            user_id: 用户名。
            session_id: 会话 ID。

        Returns:
            消息字典列表，每个字典包含 type、content、timestamp、rag_trace。
        """
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
        """删除指定用户的会话及其所有消息。

        同时清除 Redis 中的消息缓存和会话列表缓存。

        Args:
            user_id: 用户名。
            session_id: 会话 ID。

        Returns:
            True 表示成功删除，False 表示会话不存在。
        """
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

            # 清除缓存
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


def create_agent_instance():
    """创建 LangChain Agent 实例。

    使用 init_chat_model 初始化 LLM（配置来自 backend.core.config），
    通过 create_agent 绑定工具和系统提示词。

    绑定的工具：
      - get_current_weather: 查询天气信息（高德地图 API）
      - search_knowledge_base: 混合检索知识库（密集 + 稀疏向量）

    系统提示词约定：
      - Agent 扮演可爱的猫猫助手。
      - 仅在用户询问文档/知识问题时调用 search_knowledge_base。
      - 每轮最多调用一次知识检索工具。
      - 收到检索结果后必须立即输出最终回答，不得重复调用。
      - 如果检索内容不足，诚实告知"不知道"。

    Returns:
        tuple[Agent, ChatModel]: (agent 实例, 底层 LLM 模型实例)。
    """
    model = init_chat_model(
        model=MODEL,
        model_provider="openai",
        api_key=ARK_API_KEY,
        base_url=BASE_URL,
        temperature=0.3,
        stream_usage=True,
    )

    agent = create_agent(
        model=model,
        tools=[get_current_weather, search_knowledge_base],
        system_prompt=(
            "You are a cute cat bot that loves to help users. "
            "When responding, you may use tools to assist. "
            "Use search_knowledge_base when users ask document/knowledge questions. "
            "Do not call the same tool repeatedly in one turn. At most one knowledge tool call per turn. "
            "Once you call search_knowledge_base and receive its result, you MUST immediately produce the Final Answer based on that result. "
            "After receiving search_knowledge_base result, you MUST NOT call any tool again (including get_current_weather or search_knowledge_base). "
            "If the retrieved context is insufficient, answer honestly that you don't know instead of making up facts. "
            "If tool results include a Step-back Question/Answer, use that general principle to reason and answer, "
            "but do not reveal chain-of-thought. "
            "If you don't know the answer, admit it honestly."
        ),
    )

    logger.info("Agent 实例已创建: model=%s, base_url=%s", MODEL, BASE_URL)
    return agent, model


# 模块级 Agent 和模型实例（进程内单例）
agent, model = create_agent_instance()

# 模块级对话存储实例
storage = ConversationStorage()


def summarize_old_messages(model, messages: list) -> str:
    """将旧消息列表总结为一段简要摘要。

    当对话历史超过 50 条时触发，取前 40 条生成摘要，
    后续以 SystemMessage 形式注入以保持上下文窗口可控。

    Args:
        model: LLM 模型实例，用于调用总结。
        messages: 需要总结的 LangChain Message 列表。

    Returns:
        摘要文本字符串，包含用户信息、重要事实和待办事项。
    """
    old_conversation = "\n".join(
        [
            f"{'用户' if msg.type == 'human' else 'AI'}: {msg.content}"
            for msg in messages
        ]
    )

    summary_prompt = f"""请总结以下对话的关键信息：

{old_conversation}
总结（包含用户信息、重要事实、待办事项）："""

    summary = model.invoke(summary_prompt).content
    return summary


def chat_with_agent(
    user_text: str, user_id: str = "default_user", session_id: str = "default_session"
) -> dict:
    """使用 Agent 处理用户消息并返回同步响应。

    核心流程：
      1. 加载对话历史，清理残留的 RAG 上下文和工具调用计数。
      2. 若历史长度超过 50 条，对前 40 条做摘要压缩。
      3. 将用户消息追加到消息列表，调用 agent.invoke。
      4. 提取响应内容，获取 RAG trace。
      5. 保存完整对话到存储。

    Args:
        user_text: 用户输入的文本消息。
        user_id: 用户名，默认 "default_user"。
        session_id: 会话 ID，默认 "default_session"。

    Returns:
        字典，包含:
          - response (str): Agent 的文本响应。
          - rag_trace (dict | None): RAG 检索追踪信息（如有）。
    """
    messages = storage.load(user_id, session_id)

    # 清理可能残留的 RAG 上下文，避免跨请求污染
    get_last_rag_context(clear=True)
    reset_tool_call_guards()

    # 长对话摘要压缩
    if len(messages) > 50:
        summary = summarize_old_messages(model, messages[:40])
        messages = [
            SystemMessage(content=f"之前的对话摘要：\n{summary}")
        ] + messages[40:]

    # 追加用户消息并调用 Agent
    messages.append(HumanMessage(content=user_text))
    logger.debug("调用 Agent: user=%s, session=%s, history_len=%d", user_id, session_id, len(messages))

    result = agent.invoke(
        {"messages": messages},
        config={"recursion_limit": 8},
    )

    # 提取响应内容
    response_content = ""
    if isinstance(result, dict):
        if "output" in result:
            response_content = result["output"]
        elif "messages" in result and result["messages"]:
            msg = result["messages"][-1]
            response_content = getattr(msg, "content", str(msg))
        else:
            response_content = str(result)
    elif hasattr(result, "content"):
        response_content = result.content
    else:
        response_content = str(result)

    messages.append(AIMessage(content=response_content))

    # 获取 RAG 追踪信息
    rag_context = get_last_rag_context(clear=True)
    rag_trace = rag_context.get("rag_trace") if rag_context else None

    # 保存对话（含 RAG trace 关联在最后一条消息上）
    extra_message_data = [None] * (len(messages) - 1) + [{"rag_trace": rag_trace}]
    storage.save(user_id, session_id, messages, extra_message_data=extra_message_data)

    return {
        "response": response_content,
        "rag_trace": rag_trace,
    }


async def chat_with_agent_stream(
    user_text: str, user_id: str = "default_user", session_id: str = "default_session"
):
    """使用 Agent 处理用户消息并流式返回响应（AsyncGenerator）。

    架构说明 —— 统一输出队列模型：
      使用 asyncio.Queue 作为统一事件管道，所有输出（文本 chunk / RAG 步骤）
      都汇入该队列，由主循环统一 yield 为 SSE 事件。

      这样设计的原因是：
        - Agent 的 astream 是异步的，产出文本 chunk。
        - RAG 检索步骤（emit_rag_step）在工具执行期间通过
          call_soon_threadsafe 跨线程推入同一队列。
        - 不需要等 Agent 产出下一个 chunk 才能看到 RAG 步骤。

    事件格式（SSE）：
        data: {"type": "rag_step", "step": {...}}
        data: {"type": "content", "content": "..."}
        data: {"type": "trace", "rag_trace": {...}}
        data: [DONE]

    Args:
        user_text: 用户输入的文本消息。
        user_id: 用户名，默认 "default_user"。
        session_id: 会话 ID，默认 "default_session"。

    Yields:
        SSE 格式的字符串，如 "data: {...}\n\n"。
    """
    messages = storage.load(user_id, session_id)

    # 清理可能残留的 RAG 上下文
    get_last_rag_context(clear=True)
    reset_tool_call_guards()

    # 统一输出队列：所有事件（content / rag_step）都汇入这里
    output_queue: asyncio.Queue = asyncio.Queue()

    class _RagStepProxy:
        """代理对象：将 emit_rag_step 的原始 step dict 包装后放入统一输出队列。

        本代理实现 put_nowait 方法，使得 emit_rag_step 内部通过
        call_soon_threadsafe 调用时，step 数据被包装为统一事件格式
        {"type": "rag_step", "step": ...} 放入队列。
        """
        def put_nowait(self, step: dict) -> None:
            output_queue.put_nowait({"type": "rag_step", "step": step})

    # 注入 RAG 步骤队列代理，使工具执行期间的 RAG 步骤能实时推送
    set_rag_step_queue(_RagStepProxy())

    # 长对话摘要压缩
    if len(messages) > 50:
        summary = summarize_old_messages(model, messages[:40])
        messages = [
            SystemMessage(content=f"之前的对话摘要：\n{summary}")
        ] + messages[40:]

    messages.append(HumanMessage(content=user_text))

    full_response = ""

    async def _agent_worker():
        """后台任务：运行 agent.astream 并将内容 chunk 推入输出队列。

        遍历 Agent 的异步消息流，过滤掉工具调用 chunk（tool_call_chunks），
        将实际文本内容推入统一输出队列。完成后推入 None 作为哨兵。
        """
        nonlocal full_response
        try:
            async for msg, metadata in agent.astream(
                {"messages": messages},
                stream_mode="messages",
                config={"recursion_limit": 8},
            ):
                # 跳过非 AIMessageChunk（如 ToolMessage）和工具调用块
                if not isinstance(msg, AIMessageChunk):
                    continue
                if getattr(msg, "tool_call_chunks", None):
                    continue

                # 提取文本内容（可能是 str 或 list[dict] 格式）
                content = ""
                if isinstance(msg.content, str):
                    content = msg.content
                elif isinstance(msg.content, list):
                    for block in msg.content:
                        if isinstance(block, str):
                            content += block
                        elif isinstance(block, dict) and block.get("type") == "text":
                            content += block.get("text", "")

                if content:
                    full_response += content
                    await output_queue.put({"type": "content", "content": content})
        except Exception as e:
            logger.exception("Agent 流式工作线程异常")
            await output_queue.put({"type": "error", "content": str(e)})
        finally:
            # 哨兵：通知主循环 Agent 已完成
            await output_queue.put(None)

    # 启动后台 Agent 任务
    agent_task = asyncio.create_task(_agent_worker())

    try:
        # 主循环：持续从统一队列取事件并 yield SSE
        # RAG 步骤在工具执行期间通过 call_soon_threadsafe 实时入队
        while True:
            event = await output_queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    except GeneratorExit:
        # 客户端断开连接（AbortController）时，FastAPI 抛出 GeneratorExit
        # 必须取消后台 Agent 任务以避免资源泄漏
        agent_task.cancel()
        try:
            await agent_task
        except asyncio.CancelledError:
            pass  # 任务已成功取消
        raise  # 重新抛出 GeneratorExit 以便 FastAPI 正确处理关闭
    finally:
        # 正常结束或异常退出时清理 RAG 步骤队列引用
        set_rag_step_queue(None)
        if not agent_task.done():
            agent_task.cancel()

    # 获取 RAG trace（检索追踪信息）
    rag_context = get_last_rag_context(clear=True)
    rag_trace = rag_context.get("rag_trace") if rag_context else None

    # 发送 RAG trace 信息
    if rag_trace:
        yield f"data: {json.dumps({'type': 'trace', 'rag_trace': rag_trace}, ensure_ascii=False)}\n\n"

    # 发送结束信号
    yield "data: [DONE]\n\n"

    # 保存完整对话到持久化存储
    messages.append(AIMessage(content=full_response))
    extra_message_data = [None] * (len(messages) - 1) + [{"rag_trace": rag_trace}]
    storage.save(user_id, session_id, messages, extra_message_data=extra_message_data)

    logger.info("流式对话完成: user=%s, session=%s, response_len=%d", user_id, session_id, len(full_response))
