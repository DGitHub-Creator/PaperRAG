"""Tests for backend.core.auth — password hashing, JWT, and role resolution."""

import time

import pytest
from fastapi import HTTPException

from backend.core.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    resolve_role,
)


class TestPasswordHashing:
    """Tests for PBKDF2-SHA256 password hashing."""

    def test_hash_and_verify(self):
        """Hash a password and verify it matches."""
        password = "SecurePass123!"
        hash_str = get_password_hash(password)
        assert verify_password(password, hash_str) is True

    def test_wrong_password_fails(self):
        """Wrong password should not verify."""
        hash_str = get_password_hash("correct_password")
        assert verify_password("wrong_password", hash_str) is False

    def test_empty_password_raises(self):
        """Empty password should raise ValueError."""
        with pytest.raises(ValueError, match="密码不能为空"):
            get_password_hash("")

    def test_empty_plaintext_returns_false(self):
        """Empty plaintext should return False, not raise."""
        hash_str = get_password_hash("test")
        assert verify_password("", hash_str) is False

    def test_empty_hash_returns_false(self):
        """Empty hash should return False."""
        assert verify_password("test", "") is False

    def test_hash_format(self):
        """Hash should start with pbkdf2_sha256$."""
        hash_str = get_password_hash("test")
        assert hash_str.startswith("pbkdf2_sha256$")

    def test_different_hashes_for_same_password(self):
        """Each hash should be unique (random salt)."""
        h1 = get_password_hash("same_password")
        h2 = get_password_hash("same_password")
        assert h1 != h2
        # But both should verify
        assert verify_password("same_password", h1)
        assert verify_password("same_password", h2)

    def test_unicode_password(self):
        """Unicode passwords should work."""
        password = "密码测试🔑"
        hash_str = get_password_hash(password)
        assert verify_password(password, hash_str) is True


class TestJWT:
    """Tests for JWT token creation and decoding."""

    def test_create_token_contains_claims(self):
        """Token should contain sub and role claims."""
        from jose import jwt
        from backend.core.config import JWT_SECRET_KEY, JWT_ALGORITHM

        token = create_access_token("testuser", "admin")
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        assert payload["sub"] == "testuser"
        assert payload["role"] == "admin"

    def test_token_has_expiry(self):
        """Token should have an exp claim in the future."""
        from jose import jwt
        from backend.core.config import JWT_SECRET_KEY, JWT_ALGORITHM

        token = create_access_token("user1", "user")
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        assert "exp" in payload
        assert payload["exp"] > time.time()

    def test_invalid_token_raises(self):
        """Decoding an invalid token should raise JWTError."""
        from jose import jwt, JWTError
        from backend.core.config import JWT_SECRET_KEY, JWT_ALGORITHM

        with pytest.raises(JWTError):
            jwt.decode("invalid.token.here", JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


class TestResolveRole:
    """Tests for role resolution logic."""

    def test_default_role_is_user(self):
        """No role specified should default to 'user'."""
        assert resolve_role(None, None) == "user"

    def test_user_role(self):
        """Explicit 'user' role should return 'user'."""
        assert resolve_role("user", None) == "user"

    def test_admin_with_valid_code(self):
        """Admin role with correct invite code should return 'admin'."""
        from backend.core.config import ADMIN_INVITE_CODE
        assert resolve_role("admin", ADMIN_INVITE_CODE) == "admin"

    def test_admin_with_wrong_code_raises(self):
        """Admin role with wrong invite code should raise 403."""
        with pytest.raises(HTTPException) as exc_info:
            resolve_role("admin", "wrong_code")
        assert exc_info.value.status_code == 403

    def test_admin_without_code_raises(self):
        """Admin role without invite code should raise 403."""
        with pytest.raises(HTTPException) as exc_info:
            resolve_role("admin", None)
        assert exc_info.value.status_code == 403
