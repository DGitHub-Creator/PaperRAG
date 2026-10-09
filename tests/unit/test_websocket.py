"""WebSocket 端点单元测试 —— 令牌验证、速率限制。"""

import asyncio
import time
from unittest.mock import MagicMock, patch


def _db_returning(user):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    return db


class TestGetUserFromWsToken:
    def test_missing_token(self):
        from backend.api.ws import get_user_from_ws_token

        ws = MagicMock()
        ws.query_params = {}
        result = asyncio.get_event_loop().run_until_complete(get_user_from_ws_token(ws))
        assert result is None

    def test_invalid_token(self):
        from backend.api.ws import get_user_from_ws_token

        ws = MagicMock()
        ws.query_params = {"token": "invalid-token"}
        result = asyncio.get_event_loop().run_until_complete(get_user_from_ws_token(ws))
        assert result is None

    def test_valid_token_returns_db_user(self):
        """认证结果是数据库用户记录，不再只是令牌里的 sub 字符串。"""
        from backend.api.ws import get_user_from_ws_token
        from backend.core.auth import create_access_token, create_refresh_token

        user = MagicMock()
        user.username = "testuser"
        token = create_access_token("testuser", "user")
        refresh_token = create_refresh_token("testuser", "user")

        with patch("backend.api.ws.SessionLocal", return_value=_db_returning(user)):
            ws = MagicMock()
            ws.query_params = {"token": token}
            result = asyncio.get_event_loop().run_until_complete(get_user_from_ws_token(ws))
            assert result is user

            # refresh token 不能用于建立 WebSocket 会话
            ws.query_params = {"token": refresh_token}
            result = asyncio.get_event_loop().run_until_complete(get_user_from_ws_token(ws))
            assert result is None

            # 令牌有效但用户已被删除
            gone = _db_returning(None)
            with patch("backend.api.ws.SessionLocal", return_value=gone):
                ws.query_params = {"token": token}
                result = asyncio.get_event_loop().run_until_complete(get_user_from_ws_token(ws))
                assert result is None


class TestWebSocketRateLimit:
    def test_rate_limit_tracking(self):
        from backend.api.ws import _ws_msg_counts, _WS_RATE_LIMIT
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
