"""WebSocket 端点 —— 流式对话。

本模块提供的 WebSocket 路由：
  - /api/v1/ws/chat: 流式对话（替代 SSE /api/v1/chat/stream）

认证通过 URL 查询参数 ?token=<JWT> 完成，
因为 WebSocket 协议不支持自定义 HTTP 请求头。
"""

import json
import time
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from backend.core.auth import get_user_from_bearer_token
from backend.core.database import SessionLocal
from backend.core.logging_config import get_logger
from backend.core.models import User
from backend.services.agent import chat_with_agent_stream

logger = get_logger(__name__)
router = APIRouter()

_WS_RATE_LIMIT = 10
_WS_RATE_WINDOW = 60.0
_ws_msg_counts: dict[str, list[float]] = defaultdict(list)


async def get_user_from_ws_token(websocket: WebSocket) -> User | None:
    """从 WebSocket 查询参数中的 JWT 认证用户，失败返回 None。

    参数名: token（如 ws://host/api/v1/ws/chat?token=xxx）

    与 HTTP 侧共用 ``get_user_from_bearer_token``：同样要求令牌类型正确、
    未过期，并回查数据库确认用户存在；角色以数据库记录为准而非令牌声明。

    Returns:
        通过认证的 User 实例，认证失败返回 None。
    """
    token = websocket.query_params.get("token")
    if not token:
        logger.warning("WebSocket 未提供 token")
        return None
    db = SessionLocal()
    try:
        return get_user_from_bearer_token(token, db)
    finally:
        db.close()


@router.websocket("/ws/chat")
async def websocket_chat_endpoint(websocket: WebSocket):
    """流式对话 WebSocket 端点。

    认证方式: ws://host/api/v1/ws/chat?token=<JWT>

    WebSocket 消息格式（客户端 → 服务端）:
        {"message": "用户问题", "session_id": "可选会话ID"}

    WebSocket 消息格式（服务端 → 客户端）:
        {"type": "content", "content": "文本块"}
        {"type": "rag_step", "step": {"icon": "...", "label": "...", "detail": "..."}}
        {"type": "trace", "rag_trace": {...}}
        {"type": "done"}
        {"type": "error", "content": "错误信息"}
    """
    user = await get_user_from_ws_token(websocket)
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    username = user.username

    await websocket.accept()
    logger.info("WebSocket 连接已建立: user=%s", username)

    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            session_id = data.get("session_id", "default_session")

            now = time.time()
            _ws_msg_counts[username] = [
                t for t in _ws_msg_counts[username] if now - t < _WS_RATE_WINDOW
            ]
            if len(_ws_msg_counts[username]) >= _WS_RATE_LIMIT:
                await websocket.send_json({"type": "error", "content": "消息频率超限，请稍后再试"})
                continue
            _ws_msg_counts[username].append(now)

            # 使用已有的 SSE 流式函数，将事件转发到 WebSocket
            async for chunk in chat_with_agent_stream(
                message, username, session_id
            ):
                # chunk 格式为 "data: <json>\n\n" 或 "data: [DONE]\n\n"
                if chunk.startswith("data: ") and chunk.strip() != "data: [DONE]":
                    json_str = chunk[len("data: "):].strip()
                    try:
                        event = json.loads(json_str)
                        await websocket.send_json(event)
                    except json.JSONDecodeError:
                        pass
                elif chunk.strip() == "data: [DONE]":
                    await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        logger.info("WebSocket 断开: user=%s", username)
    except Exception:
        logger.exception("WebSocket 异常: user=%s", username)
        try:
            await websocket.send_json({"type": "error", "content": "服务器内部错误"})
        except Exception:
            pass
