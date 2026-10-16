"""WebSocket 端点 —— 流式对话。

本模块提供的 WebSocket 路由：
  - /api/v1/ws/chat: 流式对话（替代 SSE /api/v1/chat/stream）

认证通过 URL 查询参数 ?token=<JWT> 完成，
因为 WebSocket 协议不支持自定义 HTTP 请求头。
"""

import json
import asyncio

from limits import parse as parse_limit
from pydantic import ValidationError

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from backend.core.auth import get_user_from_bearer_token
from backend.core.database import SessionLocal
from backend.core.logging_config import get_logger
from backend.core.models import User
from backend.services.agent import chat_with_agent_stream
from backend.core.rate_limit import limiter
from backend.schemas.schemas import ChatRequest

logger = get_logger(__name__)
router = APIRouter()

_WS_LIMIT = parse_limit("10/minute")


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
    def authenticate():
        with SessionLocal() as db:
            return get_user_from_bearer_token(token, db)

    return await asyncio.to_thread(authenticate)


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
            try:
                body = ChatRequest.model_validate(await websocket.receive_json())
                if not body.message.strip():
                    raise ValueError("消息不能为空")
            except (json.JSONDecodeError, ValidationError, ValueError):
                await websocket.send_json({"type": "error", "content": "消息格式无效"})
                continue
            message, session_id = body.message, body.session_id or "default_session"
            if not await asyncio.to_thread(limiter.limiter.hit, _WS_LIMIT, username, "ws-chat"):
                await websocket.send_json({"type": "error", "content": "消息频率超限，请稍后再试"})
                continue

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
                    except json.JSONDecodeError as exc:
                        raise RuntimeError("内部流式事件不是合法 JSON") from exc
                elif chunk.strip() == "data: [DONE]":
                    await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        logger.info("WebSocket 断开: user=%s", username)
    except Exception:
        logger.exception("WebSocket 异常: user=%s", username)
        try:
            await websocket.send_json({"type": "error", "content": "服务器内部错误"})
        except Exception:
            logger.warning("可选操作失败: websocket_chat_endpoint", exc_info=True)
