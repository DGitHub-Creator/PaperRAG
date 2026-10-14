"""Chat HTTP routes."""

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from backend.core.auth import get_current_user
from backend.core.logging_config import get_logger
from backend.core.models import User
from backend.core.rate_limit import limiter
from backend.schemas.schemas import ChatRequest, ChatResponse
from backend.services.agent import chat_with_agent, chat_with_agent_stream

router = APIRouter()
logger = get_logger(__name__)


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat_endpoint(
    request: Request,
    response: Response,
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    # `request`/`response` 归 slowapi 注入，请求体因此叫 `body`（形状有机检，见 auth.py 那条注释）
    try:
        session_id = body.session_id or "default_session"
        resp = chat_with_agent(body.message, current_user.username, session_id)
        if isinstance(resp, dict):
            return ChatResponse(**resp)
        return ChatResponse(response=resp)
    except Exception as e:
        message = str(e)
        match = re.search(r"Error code:\s*(\d{3})", message)
        if match:
            code = int(match.group(1))
            if code == 429:
                raise HTTPException(
                    status_code=429,
                    detail=(
                        "Upstream model service is rate-limited or out of quota (429).\n"
                        f"Original error: {message}"
                    ),
                )
            if code in (401, 403):
                raise HTTPException(status_code=code, detail=message)
            raise HTTPException(status_code=code, detail=message)
        logger.exception("Synchronous chat failed: user=%s", current_user.username)
        raise HTTPException(status_code=500, detail=message)


@router.post("/chat/stream")
@limiter.limit("20/minute")
async def chat_stream_endpoint(
    request: Request,
    response: Response,
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    # 直接返回 StreamingResponse 时 FastAPI 不再合并注入那个 response 的头，
    # 所以这条面上的 X-RateLimit-* 不会出现——429 拦截本身照常生效（它在进函数体之前）。
    async def event_generator():
        try:
            session_id = body.session_id or "default_session"
            async for chunk in chat_with_agent_stream(
                body.message, current_user.username, session_id
            ):
                yield chunk
        except Exception as e:
            logger.exception("Streaming chat failed: user=%s", current_user.username)
            error_data = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
