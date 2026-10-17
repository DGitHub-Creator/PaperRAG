"""WebSocket 端点单元测试 —— 令牌验证、速率限制。"""

import pytest
from unittest.mock import MagicMock, patch

# 与 tests/unit/test_auth.py 同一个约定：单测的密钥由用例自己给。
# 这条不是形式主义——从前这里读的是**开发机的 `.env`**，于是 CI（没有 .env）上
# `create_access_token` 走到 pyjwt 就抛 `InvalidKeyError: HMAC key must not be empty.`，
# 一个纯单测因为"借用了机器本地的密钥"而红。
TEST_SECRET = "unit-test-secret-key"


def _db_returning(user):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    db.__enter__.return_value = db
    return db


@pytest.mark.asyncio
class TestGetUserFromWsToken:
    async def test_missing_token(self):
        from backend.api.ws import get_user_from_ws_token

        ws = MagicMock()
        ws.query_params = {}
        result = await get_user_from_ws_token(ws)
        assert result is None

    async def test_invalid_token(self):
        from backend.api.ws import get_user_from_ws_token

        ws = MagicMock()
        ws.query_params = {"token": "invalid-token"}
        result = await get_user_from_ws_token(ws)
        assert result is None

    async def test_valid_token_returns_db_user(self):
        """认证结果是数据库用户记录，不再只是令牌里的 sub 字符串。"""
        from backend.api.ws import get_user_from_ws_token
        from backend.core.auth import create_access_token, create_refresh_token

        user = MagicMock()
        user.username = "testuser"
        # patch 必须同时罩住"签"与"验"：只罩签发，取回令牌时密钥又变回空值，
        # 失败的表象会是"令牌无效"而不是"没配密钥"，看不出根因。
        with patch.multiple(
            "backend.core.auth", JWT_SECRET_KEY=TEST_SECRET, JWT_ALGORITHM="HS256"
        ):
            token = create_access_token("testuser", "user")
            refresh_token = create_refresh_token("testuser", "user")

            with patch("backend.api.ws.SessionLocal", return_value=_db_returning(user)):
                ws = MagicMock()
                ws.query_params = {"token": token}
                result = await get_user_from_ws_token(ws)
            assert result is user

            # refresh token 不能用于建立 WebSocket 会话
            ws.query_params = {"token": refresh_token}
            result = await get_user_from_ws_token(ws)
            assert result is None

            # 令牌有效但用户已被删除
            gone = _db_returning(None)
            with patch("backend.api.ws.SessionLocal", return_value=gone):
                ws.query_params = {"token": token}
                result = await get_user_from_ws_token(ws)
                assert result is None
