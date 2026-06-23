"""WebSocket 端点单元测试 —— 令牌验证、速率限制。"""

import time
from unittest.mock import MagicMock, patch, AsyncMock


class TestGetUserFromWsToken:
    def test_missing_token(self):
        from backend.api.ws import get_user_from_ws_token
        ws = MagicMock()
        ws.query_params = {}
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(get_user_from_ws_token(ws))
        assert result is None

    def test_invalid_token(self):
        from backend.api.ws import get_user_from_ws_token
        ws = MagicMock()
        ws.query_params = {"token": "invalid-token"}
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(get_user_from_ws_token(ws))
        assert result is None

    def test_valid_token(self):
        from backend.api.ws import get_user_from_ws_token
        from backend.core.auth import create_access_token
        token = create_access_token("testuser", "user")
        ws = MagicMock()
        ws.query_params = {"token": token}
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(get_user_from_ws_token(ws))
        assert result == "testuser"


class TestWebSocketRateLimit:
    def test_rate_limit_tracking(self):
        from backend.api.ws import _ws_msg_counts, _WS_RATE_LIMIT, _WS_RATE_WINDOW
        _ws_msg_counts.clear()
        username = "test_user_rate"
        now = time.time()
        for i in range(_WS_RATE_LIMIT):
            _ws_msg_counts[username].append(now)
        assert len(_ws_msg_counts[username]) == _WS_RATE_LIMIT

    def test_rate_limit_window_expiry(self):
        from backend.api.ws import _ws_msg_counts, _WS_RATE_WINDOW
        _ws_msg_counts.clear()
        username = "test_user_expiry"
        old_time = time.time() - _WS_RATE_WINDOW - 1
        _ws_msg_counts[username] = [old_time, old_time]
        now = time.time()
        _ws_msg_counts[username] = [
            t for t in _ws_msg_counts[username] if now - t < _WS_RATE_WINDOW
        ]
        assert len(_ws_msg_counts[username]) == 0
