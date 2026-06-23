"""智能体服务层 —— 统一的 Agent 对话接口。

本模块提供 PaperRAG 的对话核心接口，所有 Agent 相关的对外暴露均通过此模块。

底层实现已统一到 backend.agent.core（LangGraph Agent with Intent Router），
本模块仅负责向后兼容的接口封装。

导出：
  - ConversationStorage: 对话持久化存储（从 conversation_storage.py 重新导出）
  - chat_with_agent: 同步对话接口
  - chat_with_agent_stream: 流式对话接口（AsyncGenerator）
"""

from backend.services.conversation_storage import ConversationStorage

__all__ = [
    "ConversationStorage",
    "chat_with_agent",
    "chat_with_agent_stream",
]


def chat_with_agent(
    user_text: str, user_id: str = "default_user", session_id: str = "default_session"
) -> dict:
    from backend.agent.core import run_agent
    return run_agent(user_text, user_id, session_id)


async def chat_with_agent_stream(
    user_text: str, user_id: str = "default_user", session_id: str = "default_session"
):
    from backend.agent.core import run_agent_stream
    async for event in run_agent_stream(user_text, user_id, session_id):
        yield event
