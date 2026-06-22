from backend.core.stats import get_stats, record_request, reset_stats


def test_record_and_get_stats():
    reset_stats()
    record_request("/auth/login")
    record_request("/auth/login")
    record_request("/chat")
    stats = get_stats()
    assert len(stats) == 2
    login_stats = [s for s in stats if s["path"] == "/auth/login"][0]
    assert login_stats["count"] == 2
    chat_stats = [s for s in stats if s["path"] == "/chat"][0]
    assert chat_stats["count"] == 1


def test_reset_stats():
    record_request("/health")
    reset_stats()
    assert get_stats() == []


def test_stats_ordering():
    reset_stats()
    record_request("/b")
    record_request("/b")
    record_request("/a")
    stats = get_stats()
    assert stats[0]["count"] >= stats[1]["count"]
