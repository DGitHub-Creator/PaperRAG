"""Rate limiting utilities — shared limiter instance for app.py and routes.py."""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=[])
