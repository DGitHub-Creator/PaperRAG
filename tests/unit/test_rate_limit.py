"""Tests for rate limiting and usage statistics."""

from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.core.rate_limit import limiter
from backend.core.models import UsageLog


class TestLimiterConfiguration:
    """Tests for slowapi limiter setup."""

    def test_limiter_exists(self):
        """Limiter should be a Limiter instance."""
        assert isinstance(limiter, Limiter)

    def test_limiter_key_func(self):
        """Limiter should use remote address as key."""
        assert limiter._key_func is get_remote_address


class TestUsageLogModel:
    """Tests for UsageLog ORM model."""

    def test_tablename(self):
        """UsageLog should map to usage_logs table."""
        assert UsageLog.__tablename__ == "usage_logs"

    def test_has_required_columns(self):
        """UsageLog should have all required columns."""
        columns = {c.name for c in UsageLog.__table__.columns}
        expected = {
            "id", "user_id", "endpoint", "method",
            "status_code", "tokens_used", "latency_ms", "created_at",
        }
        assert expected.issubset(columns)
