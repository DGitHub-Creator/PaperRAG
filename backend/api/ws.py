"""WebSocket 端点 —— 流式对话与上传进度推送。

本模块提供两个 WebSocket 路由：
  - /ws/chat:      流式对话（替代 SSE /api/chat/stream）
  - /ws/upload/{job_id}: 上传任务进度推送

认证通过 URL 查询参数 ?token=<JWT> 完成，
因为 WebSocket 协议不支持自定义 HTTP 请求头。
"""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt

from backend.core.config import JWT_SECRET_KEY, JWT_ALGORITHM
from backend.core.logging_config import get_logger
from backend.services.agent import chat_with_agent_stream

logger = get_logger(__name__)
router = APIRouter()


async def get_user_from_ws_token(websocket: WebSocket) -> str | None:
    """从 WebSocket 查询参数中提取并验证 JWT，返回用户名。

    参数名: token（如 ws://host/ws/chat?token=xxx）

    Returns:
        用户名，验证失败返回 None。
    """
    token = websocket.query_params.get("token")
    if not token:
        logger.warning("WebSocket 未提供 token")
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        username: str | None = payload.get("sub")
        if not username:
            logger.warning("JWT 缺少 sub 字段")
            return None
        return username
    except JWTError:
        logger.warning("WebSocket JWT 无效或已过期")
        return None


@router.websocket("/ws/chat")
async def websocket_chat_endpoint(websocket: WebSocket):
    """流式对话 WebSocket 端点。

    认证方式: ws://host/ws/chat?token=<JWT>

    WebSocket 消息格式（客户端 → 服务端）:
        {"message": "用户问题", "session_id": "可选会话ID"}

    WebSocket 消息格式（服务端 → 客户端）:
        {"type": "content", "content": "文本块"}
        {"type": "rag_step", "step": {"icon": "...", "label": "...", "detail": "..."}}
        {"type": "trace", "rag_trace": {...}}
        {"type": "done"}
        {"type": "error", "content": "错误信息"}
    """
    username = await get_user_from_ws_token(websocket)
    if not username:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    logger.info("WebSocket 连接已建立: user=%s", username)

    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            session_id = data.get("session_id", "default_session")

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
