"""认证模块单元测试 —— 密码哈希、JWT 令牌、用户验证、权限校验。"""


from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from jose import jwt

from backend.core.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    get_current_user,
    get_password_hash,
    get_user_from_bearer_token,
    require_admin,
    resolve_role,
    verify_password,
)

TEST_SECRET = "test-secret-for-testing"


def _patch_auth():
    """Apply common monkeypatches for JWT token tests."""
    return patch.multiple(
        "backend.core.auth",
        JWT_SECRET_KEY=TEST_SECRET,
        JWT_ALGORITHM="HS256",
        JWT_EXPIRE_MINUTES=1440,
        JWT_REFRESH_EXPIRE_DAYS=30,
    )


# ── 密码哈希 ──────────────────────────────────────────────────────────


class TestPasswordHashing:
    def test_hash_and_verify(self):
        pw = "MySecureP@ss123"
        h = get_password_hash(pw)
        assert h.startswith("pbkdf2_sha256$")
        assert verify_password(pw, h)
        assert not verify_password("wrong-password", h)

    def test_empty_password_raises(self):
        with pytest.raises(ValueError):
            get_password_hash("")

    def test_verify_rejects_empty(self):
        assert not verify_password("", "pbkdf2_sha256$1$a$b")
        assert not verify_password("pw", "")
        assert not verify_password("", "")

    def test_verify_unknown_format(self):
        assert not verify_password("pw", "unknown$format")
        assert not verify_password("pw", "$2abc")  # bcrypt-ish but short/corrupt

    def test_verify_corrupt_pbkdf2(self):
        assert not verify_password("pw", "pbkdf2_sha256$bad")
        assert not verify_password("pw", "pbkdf2_sha256$a$b$c$d")


# ── JWT 令牌 ─────────────────────────────────────────────────────────


class TestJWTTokens:
    def test_create_access_token(self):
        with _patch_auth():
            token = create_access_token("alice", "user")
            payload = jwt.decode(token, TEST_SECRET, algorithms=["HS256"])
            assert payload["sub"] == "alice"
            assert payload["role"] == "user"
            assert payload["exp"] is not None
            assert payload["type"] == "access"

    def test_create_refresh_token(self):
        with _patch_auth():
            token = create_refresh_token("alice", "user")
            payload = jwt.decode(token, TEST_SECRET, algorithms=["HS256"])
            assert payload["sub"] == "alice"
            assert payload["role"] == "user"
            assert payload["type"] == "refresh"
            assert "exp" in payload

    def test_access_vs_refresh_different(self):
        with _patch_auth():
            access = create_access_token("alice", "user")
            refresh = create_refresh_token("alice", "user")
            assert access != refresh
            a_payload = jwt.decode(access, TEST_SECRET, algorithms=["HS256"])
            r_payload = jwt.decode(refresh, TEST_SECRET, algorithms=["HS256"])
            assert a_payload["type"] == "access"
            assert r_payload["type"] == "refresh"

    def test_admin_token_has_admin_role(self):
        with _patch_auth():
            token = create_access_token("admin1", "admin")
            payload = jwt.decode(token, TEST_SECRET, algorithms=["HS256"])
            assert payload["role"] == "admin"


# ── 用户验证 ─────────────────────────────────────────────────────────


class TestAuthenticateUser:
    def test_user_not_found(self):
        db = MagicMock()
        db.query().filter().first.return_value = None
        result = authenticate_user(db, "nobody", "pw")
        assert result is None

    def test_wrong_password(self):
        user = MagicMock()
        user.username = "alice"
        with patch("backend.core.auth.verify_password", return_value=False):
            db = MagicMock()
            db.query().filter().first.return_value = user
            result = authenticate_user(db, "alice", "wrong")
            assert result is None

    def test_success(self):
        user = MagicMock()
        user.username = "alice"
        with patch("backend.core.auth.verify_password", return_value=True):
            db = MagicMock()
            db.query().filter().first.return_value = user
            result = authenticate_user(db, "alice", "correct")
            assert result is user


# ── 当前用户依赖注入 ────────────────────────────────────────────────


class TestGetCurrentUser:
    def test_valid_token(self):
        with _patch_auth():
            token = create_access_token("alice", "user")
            db = MagicMock()
            user = MagicMock()
            user.username = "alice"
            db.query().filter().first.return_value = user
            result = get_current_user(token=token, db=db)
            assert result is user

    def test_invalid_token_raises(self):
        with _patch_auth():
            with pytest.raises(HTTPException) as exc:
                get_current_user(token="invalid-token", db=MagicMock())
            assert exc.value.status_code == 401

    def test_expired_token_raises(self):
        with patch.multiple(
            "backend.core.auth",
            JWT_SECRET_KEY=TEST_SECRET,
            JWT_ALGORITHM="HS256",
            JWT_EXPIRE_MINUTES=-1,
        ):
            token = create_access_token("alice", "user")
            with pytest.raises(HTTPException) as exc:
                get_current_user(token=token, db=MagicMock())
            assert exc.value.status_code == 401

    def test_user_deleted_after_token_issued(self):
        with _patch_auth():
            token = create_access_token("alice", "user")
            db = MagicMock()
            db.query().filter().first.return_value = None
            with pytest.raises(HTTPException) as exc:
                get_current_user(token=token, db=db)
            assert exc.value.status_code == 401


# ── 令牌类型校验（E7: refresh token 不能当 access token）─────────────


class TestTokenTypeEnforcement:
    def _db_with_user(self):
        user = MagicMock()
        user.username = "alice"
        user.role = "user"
        db = MagicMock()
        db.query().filter().first.return_value = user
        return db

    def test_token_type_refresh_rejected_by_http_dep(self):
        with _patch_auth():
            refresh = create_refresh_token("alice", "user")
            with pytest.raises(HTTPException) as exc:
                get_current_user(token=refresh, db=self._db_with_user())
            assert exc.value.status_code == 401

    def test_token_type_refresh_rejected_by_bearer_helper(self):
        """WebSocket 与 HTTP 共用同一个解析函数，语义必须一致。"""
        with _patch_auth():
            refresh = create_refresh_token("alice", "user")
            assert get_user_from_bearer_token(refresh, self._db_with_user()) is None

    def test_token_type_legacy_access_accepted(self):
        """改动前签发的 access token 不带 type，需继续可用。"""
        legacy = jwt.encode(
            {"sub": "alice", "role": "user", "exp": datetime.now(UTC) + timedelta(minutes=5)},
            TEST_SECRET,
            algorithm="HS256",
        )
        with patch.multiple("backend.core.auth", JWT_SECRET_KEY=TEST_SECRET, JWT_ALGORITHM="HS256"):
            assert get_user_from_bearer_token(legacy, self._db_with_user()) is not None

    def test_token_type_unknown_value_rejected(self):
        with patch.multiple("backend.core.auth", JWT_SECRET_KEY=TEST_SECRET, JWT_ALGORITHM="HS256"):
            weird = jwt.encode(
                {
                    "sub": "alice",
                    "type": "session",
                    "exp": datetime.now(UTC) + timedelta(minutes=5),
                },
                TEST_SECRET,
                algorithm="HS256",
            )
            assert get_user_from_bearer_token(weird, self._db_with_user()) is None


# ── 管理员权限校验 ───────────────────────────────────────────────────

class TestRequireAdmin:
    def test_admin_user_passes(self):
        user = MagicMock()
        user.role = "admin"
        result = require_admin(user)
        assert result is user

    def test_non_admin_raises(self):
        user = MagicMock()
        user.role = "user"
        with pytest.raises(HTTPException) as exc:
            require_admin(user)
        assert exc.value.status_code == 403


# ── 角色解析 ─────────────────────────────────────────────────────────


class TestResolveRole:
    def test_default_user(self):
        assert resolve_role(None, None) == "user"
        assert resolve_role("", None) == "user"
        assert resolve_role("user", None) == "user"

    def test_admin_with_valid_code(self):
        with patch("backend.core.auth.ADMIN_INVITE_CODE", "secret"):
            assert resolve_role("admin", "secret") == "admin"

    def test_admin_with_wrong_code(self):
        with patch("backend.core.auth.ADMIN_INVITE_CODE", "secret"):
            with pytest.raises(HTTPException) as exc:
                resolve_role("admin", "wrong")
            assert exc.value.status_code == 403

    def test_admin_blocked_when_invite_code_unset(self):
        """ADMIN_INVITE_CODE 不再有默认值：未配置即关闭管理员注册通道。"""
        with patch("backend.core.auth.ADMIN_INVITE_CODE", ""):
            with pytest.raises(HTTPException) as exc:
                resolve_role("admin", "guessed-code")
            assert exc.value.status_code == 403
            assert "未配置" in exc.value.detail

    def test_unset_invite_code_does_not_affect_normal_users(self):
        with patch("backend.core.auth.ADMIN_INVITE_CODE", ""):
            assert resolve_role("user", None) == "user"
            assert resolve_role(None, None) == "user"

    def test_invite_code_not_echoed_in_logs(self):
        """失败日志不得回显提交的邀请码。"""
        with (
            patch("backend.core.auth.ADMIN_INVITE_CODE", "secret"),
            patch("backend.core.auth.logger") as mock_logger,
        ):
            with pytest.raises(HTTPException):
                resolve_role("admin", "guessed-code")
        for call in mock_logger.warning.call_args_list:
            assert "guessed-code" not in str(call)
