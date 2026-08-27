"""Tests for rate limiting configuration."""

from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.core.rate_limit import limiter


class TestLimiterConfiguration:
    """Tests for slowapi limiter setup."""

    def test_limiter_exists(self):
        """Limiter should be a Limiter instance."""
        assert isinstance(limiter, Limiter)

    def test_limiter_key_func(self):
        """Limiter should use remote address as key."""
        assert limiter._key_func is get_remote_address

    def test_limiter_default_limits(self):
        """Default limits should be empty (limits applied per-route)."""
        assert limiter._default_limits == []

    def test_limiter_storage_available(self):
        """Limiter should have a storage backend."""
        assert limiter._storage is not None
