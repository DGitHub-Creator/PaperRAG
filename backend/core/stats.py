"""Usage statistics — lightweight in-memory request counters."""

from collections import defaultdict
from datetime import UTC, datetime
from threading import Lock

_stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "last_accessed": ""})
_lock = Lock()


def record_request(path: str) -> None:
    """Record an API request for the given path."""
    with _lock:
        entry = _stats[path]
        entry["count"] += 1
        entry["last_accessed"] = datetime.now(UTC).isoformat()


def get_stats() -> dict:
    """Return a snapshot of usage stats (ordered by count descending)."""
    with _lock:
        sorted_items = sorted(_stats.items(), key=lambda x: x[1]["count"], reverse=True)
        return [{"path": path, **data} for path, data in sorted_items]


def reset_stats() -> None:
    """Clear all recorded stats."""
    with _lock:
        _stats.clear()
