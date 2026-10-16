"""认证与安全配置。

密钥类配置**不提供可猜测的默认值**：缺失即为空字符串，由
``validate_runtime_security()`` 在启动时判定并拒绝启动。
环境相关的宽松预设（限流、CORS 等）统一在 ``config/__init__.py`` 的
环境预设段处理，不在这里分支。
"""

import os

_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = ["*"] if _raw_origins == "*" else [o.strip() for o in _raw_origins.split(",")]

RATE_LIMIT = os.getenv("RATE_LIMIT", "")
"""全局限流规格（如 "60/minute"）。空字符串表示不启用全局限流。
仅在 ``Limiter(default_limits=...)`` 构造时被消费，因此改一次重启一次。"""

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
JWT_REFRESH_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "30"))
ADMIN_INVITE_CODE = os.getenv("ADMIN_INVITE_CODE", "")
"""空字符串表示禁止通过注册接口创建 admin（resolve_role 会显式报错）。"""

AICORE_INTERNAL_TOKEN = os.getenv("AICORE_INTERNAL_TOKEN", "")
"""Go → ai-core 的服务间静态令牌（02 §3.5）。空值不是「不鉴权」：内部执行面据此拒绝一切请求。"""

PASSWORD_PBKDF2_ROUNDS = int(os.getenv("PASSWORD_PBKDF2_ROUNDS", "310000"))
MIN_PASSWORD_LENGTH = int(os.getenv("MIN_PASSWORD_LENGTH", "8"))

TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
"""仅在服务确实部署在可信反向代理之后时才开启：开启后限流键取
X-Forwarded-For 的首个地址。直连场景开启会让客户端伪造该头绕过限流。"""

TRUSTED_PROXY_CIDRS = os.getenv("TRUSTED_PROXY_CIDRS", "")
