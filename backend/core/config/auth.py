"""认证与安全配置。"""

import os

_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = ["*"] if _raw_origins == "*" else [o.strip() for o in _raw_origins.split(",")]

RATE_LIMIT = os.getenv("RATE_LIMIT", "60/minute")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "replace-with-strong-random-secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))
JWT_REFRESH_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "30"))
ADMIN_INVITE_CODE = os.getenv("ADMIN_INVITE_CODE", "paperrag-admin-2026")
PASSWORD_PBKDF2_ROUNDS = int(os.getenv("PASSWORD_PBKDF2_ROUNDS", "310000"))
MIN_PASSWORD_LENGTH = int(os.getenv("MIN_PASSWORD_LENGTH", "8"))
