from backend.core.rate_limit import limiter


def test_limiter_created():
    assert limiter is not None
    assert limiter._default_limits == []


def test_limiter_storage():
    storage = limiter._storage
    assert storage is not None
