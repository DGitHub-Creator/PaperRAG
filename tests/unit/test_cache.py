"""Tests for backend.services.cache — SemanticCache (in-memory, no Redis required)."""

import time
from unittest.mock import patch

import pytest

from backend.services.cache import SemanticCache


class TestSemanticCacheNormalize:
    """Tests for query normalization."""

    def test_lowercase(self):
        assert SemanticCache._normalize("Hello World") == "hello world"

    def test_strip_punctuation(self):
        assert SemanticCache._normalize("what is MPC?") == "what is mpc"

    def test_compress_whitespace(self):
        assert SemanticCache._normalize("hello   world") == "hello world"

    def test_strip_edges(self):
        assert SemanticCache._normalize("  hello  ") == "hello"


class TestSemanticCacheExactMatch:
    """Tests for Level 1 exact matching."""

    def test_store_and_lookup(self):
        cache = SemanticCache()
        cache.store("what is MPC", {"answer": "secure computation"})
        result = cache.lookup("what is MPC")
        assert result == {"answer": "secure computation"}

    def test_case_insensitive(self):
        cache = SemanticCache()
        cache.store("What Is MPC", {"answer": "test"})
        result = cache.lookup("what is mpc")
        assert result == {"answer": "test"}

    def test_punctuation_insensitive(self):
        cache = SemanticCache()
        cache.store("what is MPC?", {"answer": "test"})
        result = cache.lookup("what is MPC")
        assert result == {"answer": "test"}

    def test_miss_returns_none(self):
        cache = SemanticCache()
        assert cache.lookup("nonexistent query") is None

    def test_disabled_cache_returns_none(self):
        with patch("backend.services.cache.ENABLE_CACHE", False):
            cache = SemanticCache()
            cache.store("query", {"answer": "test"})
            assert cache.lookup("query") is None

    def test_ttl_expiry(self):
        cache = SemanticCache()
        cache._ttl = 0  # Expire immediately
        cache.store("query", {"answer": "test"})
        time.sleep(0.01)
        assert cache.lookup("query") is None

    def test_invalidate_specific(self):
        cache = SemanticCache()
        cache.store("query1", {"answer": "a"})
        cache.store("query2", {"answer": "b"})
        removed = cache.invalidate("query1")
        assert removed >= 1
        assert cache.lookup("query1") is None
        assert cache.lookup("query2") == {"answer": "b"}

    def test_invalidate_all(self):
        cache = SemanticCache()
        cache.store("q1", {"a": 1})
        cache.store("q2", {"a": 2})
        removed = cache.invalidate(None)
        assert removed == 2
        assert cache.lookup("q1") is None
        assert cache.lookup("q2") is None

    def test_capacity_limit(self):
        cache = SemanticCache()
        cache._max_size = 3
        for i in range(5):
            cache.store(f"query_{i}", {"i": i})
        assert len(cache._exact) <= 3


class TestSemanticCacheSemanticMatch:
    """Tests for Level 2 semantic matching."""

    def test_semantic_hit(self):
        """Similar queries should match via embedding similarity."""
        def fake_embed(query):
            # Return nearly identical vectors for similar queries
            if "mpc" in query.lower():
                return [1.0, 0.0, 0.0]
            return [0.0, 1.0, 0.0]

        cache = SemanticCache(embedding_fn=fake_embed)
        cache.store("what is MPC", {"answer": "secure computation"})

        # Different phrasing but same concept
        result = cache.lookup("tell me about MPC")
        assert result == {"answer": "secure computation"}

    def test_semantic_miss(self):
        """Dissimilar queries should not match."""
        def fake_embed(query):
            if "mpc" in query.lower():
                return [1.0, 0.0, 0.0]
            return [0.0, 0.0, 1.0]

        cache = SemanticCache(embedding_fn=fake_embed)
        cache.store("what is MPC", {"answer": "test"})

        result = cache.lookup("weather in Beijing")
        assert result is None

    def test_no_embed_fn_skips_semantic(self):
        """Without embedding_fn, semantic layer is skipped."""
        cache = SemanticCache(embedding_fn=None)
        cache.store("query", {"answer": "test"})
        # Exact match still works
        assert cache.lookup("query") == {"answer": "test"}
        # But different phrasing won't
        assert cache.lookup("different phrasing") is None
