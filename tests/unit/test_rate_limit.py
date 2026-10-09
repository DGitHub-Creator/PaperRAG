"""Tests for rate limiting configuration."""

from unittest.mock import patch

from slowapi import Limiter
from starlette.requests import Request

from backend.core.rate_limit import (
    _parse_default_limits,
    default_limits,
    limiter,
    rate_limit_key,
)


def _request(client_ip="203.0.113.9", forwarded=None):
    headers = []
    if forwarded is not None:
        headers.append((b"x-forwarded-for", forwarded.encode()))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/v1/documents/query",
            "query_string": b"",
            "root_path": "",
            "headers": headers,
            "client": (client_ip, 1234),
            "server": ("testserver", 80),
        }
    )


class TestLimiterConfiguration:
    """Tests for slowapi limiter setup."""

    def test_limiter_exists(self):
        """Limiter should be a Limiter instance."""
        assert isinstance(limiter, Limiter)

    def test_limiter_key_func(self):
        """Limiter should use the proxy-aware key function, not the raw remote address."""
        assert limiter._key_func is rate_limit_key

    def test_limiter_default_limits_match_env(self):
        """default_limits 必须来自 RATE_LIMIT，且确实交给了 Limiter（E8 的"日志诚实"）。

        slowapi 会把规格字符串解析成 LimitGroup，因此这里比对数量而非原值。
        """
        assert len(limiter._default_limits) == len(default_limits)

    def test_default_limits_empty_when_rate_limit_unset(self):
        """测试环境未设置 RATE_LIMIT 时不应意外启用全局限流。"""
        assert default_limits == []
        assert limiter._default_limits == []

    def test_limiter_storage_available(self):
        """Limiter should have a storage backend."""
        assert limiter._storage is not None


class TestDefaultLimitsParsing:
    def test_parse_blank_is_disabled(self):
        assert _parse_default_limits("") == []
        assert _parse_default_limits("   ") == []

    def test_parse_spec(self):
        assert _parse_default_limits("60/minute") == ["60/minute"]
        assert _parse_default_limits(" 60/minute ") == ["60/minute"]


class TestProxyAwareKey:
    def test_forwarded_header_ignored_when_untrusted(self):
        """未开启 TRUST_PROXY_HEADERS 时，伪造的 X-Forwarded-For 不得影响限流键。"""
        with patch("backend.core.rate_limit.TRUST_PROXY_HEADERS", False):
            req = _request(forwarded="198.51.100.7, 10.0.0.1")
            assert rate_limit_key(req) == "203.0.113.9"

    def test_first_forwarded_hop_used_when_trusted(self):
        with patch("backend.core.rate_limit.TRUST_PROXY_HEADERS", True):
            req = _request(forwarded="198.51.100.7, 10.0.0.1")
            assert rate_limit_key(req) == "198.51.100.7"

    def test_trusted_proxy_without_header_falls_back(self):
        with patch("backend.core.rate_limit.TRUST_PROXY_HEADERS", True):
            assert rate_limit_key(_request()) == "203.0.113.9"
