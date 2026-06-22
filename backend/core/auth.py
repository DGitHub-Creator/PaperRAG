"""
认证模块 —— 用户注册、登录、JWT 令牌管理与权限校验。

本模块负责:
  - PBKDF2-SHA256 密码哈希与验证（兼容旧版 passlib/bcrypt 哈希）
  - JWT 令牌的创建与解码
  - FastAPI 依赖注入：获取当前用户、要求管理员权限
  - 角色解析（普通用户 / 管理员）

所有配置值统一从 backend.core.config 导入，避免分散的 os.getenv 调用。
日志通过 backend.core.logging_config.get_logger 获取标准化 logger。
数据库会话 get_db 从 backend.core.database 导入（统一管理数据库连接）。
User ORM 模型从 backend.core.models 导入。

使用方式（FastAPI 路由中）:
    from backend.core.auth import get_current_user, require_admin

    @router.get("/protected")
    def protected_route(current_user = Depends(get_current_user)):
        ...
"""

import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

# 统一配置
from backend.core.config import (
    ADMIN_INVITE_CODE,
    JWT_ALGORITHM,
    JWT_EXPIRE_MINUTES,
    JWT_REFRESH_EXPIRE_DAYS,
    JWT_SECRET_KEY,
    PASSWORD_PBKDF2_ROUNDS,
)

# 数据库会话（get_db 统一在 database.py 中维护，各模块共用）
from backend.core.database import get_db

# 标准化日志
from backend.core.logging_config import get_logger

# ORM 模型
from backend.core.models import User

logger = get_logger(__name__)

# ── OAuth2 密码流配置 ────────────────────────────────────────────────
# tokenUrl 对应前端登录接口 POST /auth/login
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ══════════════════════════════════════════════════════════════════════
# 密码哈希与验证
# ══════════════════════════════════════════════════════════════════════


def verify_password(plain_password: str, password_hash: str) -> bool:
    """验证明文密码是否与数据库中的哈希值匹配。

    支持两种哈希格式:
      1. 新版 pbkdf2_sha256$<rounds>$<salt_b64>$<digest_b64>
         —— 使用 hashlib.pbkdf2_hmac (SHA256) 计算，无第三方依赖。
      2. 旧版 passlib/bcrypt 哈希（以 $2 或 $bcrypt 开头）
         —— 向后兼容，在已安装 passlib 的前提下自动识别。

    Args:
        plain_password: 用户输入的明文密码。
        password_hash: 数据库中存储的密码哈希字符串。

    Returns:
        True 表示密码匹配，False 表示不匹配或验证过程出错。
    """
    # 基本校验：空密码或空哈希直接拒绝
    if not plain_password or not password_hash:
        return False

    # ── 新版格式: pbkdf2_sha256$<rounds>$<salt_b64>$<digest_b64> ──
    if password_hash.startswith("pbkdf2_sha256$"):
        try:
            # 按 $ 分割，格式固定为 4 段
            _, rounds, salt_b64, digest_b64 = password_hash.split("$", 3)
            # Base64 解码盐值和期望的摘要
            salt = base64.b64decode(salt_b64.encode("ascii"))
            expected = base64.b64decode(digest_b64.encode("ascii"))
            # 使用相同的参数重新计算 PBKDF2-SHA256
            calculated = hashlib.pbkdf2_hmac(
                "sha256",
                plain_password.encode("utf-8"),
                salt,
                int(rounds),
            )
            # 使用 hmac.compare_digest 防止时序攻击
            return hmac.compare_digest(calculated, expected)
        except Exception:
            logger.warning("PBKDF2 密码验证时发生异常，返回 False")
            return False

    # ── 向后兼容: passlib/bcrypt 旧版哈希 ──
    # 仅在已安装 passlib 时生效；如果未安装则跳过此分支
    if password_hash.startswith("$2") or password_hash.startswith("$bcrypt"):
        try:
            from passlib.context import CryptContext

            legacy_context = CryptContext(schemes=["bcrypt_sha256", "bcrypt"], deprecated="auto")
            return legacy_context.verify(plain_password, password_hash)
        except Exception:
            logger.warning("Passlib/bcrypt 密码验证时发生异常，返回 False")
            return False

    # 未识别的哈希格式
    return False


def get_password_hash(password: str) -> str:
    """对明文密码进行 PBKDF2-SHA256 哈希，返回存储格式的字符串。

    哈希格式:
        pbkdf2_sha256$<rounds>$<base64_salt>$<base64_digest>

    Args:
        password: 用户输入的明文密码。

    Returns:
        格式化的哈希字符串，可直接存入数据库 password_hash 字段。

    Raises:
        ValueError: 如果 password 为空字符串或 None。
    """
    if not password:
        raise ValueError("密码不能为空")

    # 生成 16 字节随机盐值
    salt = os.urandom(16)
    # 使用 PBKDF2-SHA256 进行多轮哈希
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_PBKDF2_ROUNDS,
    )
    # 盐值和摘要分别 Base64 编码，拼接为存储字符串
    salt_b64 = base64.b64encode(salt).decode("ascii")
    digest_b64 = base64.b64encode(digest).decode("ascii")
    return f"pbkdf2_sha256${PASSWORD_PBKDF2_ROUNDS}${salt_b64}${digest_b64}"


# ══════════════════════════════════════════════════════════════════════
# JWT 令牌创建与验证
# ══════════════════════════════════════════════════════════════════════


def create_access_token(username: str, role: str) -> str:
    """为指定用户创建一个新的 JWT 访问令牌。

    JWT payload 包含:
      - sub: 用户名（subject）
      - role: 用户角色（"user" 或 "admin"）
      - exp: 过期时间戳（UTC）

    Args:
        username: 用户名，对应数据库 users.username。
        role: 用户角色，用于后续权限校验。

    Returns:
        编码后的 JWT 字符串（Bearer Token），可直接返回给前端。
    """
    expire = datetime.now(UTC) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {
        "sub": username,
        "role": role,
        "exp": expire,
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    logger.debug(f"已为用户 '{username}' (角色: {role}) 创建 JWT，过期时间: {expire.isoformat()}")
    return token


def create_refresh_token(username: str, role: str) -> str:
    """创建一个新的 JWT Refresh Token（长有效期）。

    JWT payload 包含:
      - sub: 用户名
      - role: 用户角色
      - type: "refresh" （与 access token 区分）
      - exp: 过期时间戳（UTC, 默认 30 天）

    Args:
        username: 用户名。
        role: 用户角色。

    Returns:
        编码后的 Refresh Token 字符串。
    """
    expire = datetime.now(UTC) + timedelta(days=JWT_REFRESH_EXPIRE_DAYS)
    payload = {
        "sub": username,
        "role": role,
        "type": "refresh",
        "exp": expire,
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    logger.debug(f"已为用户 '{username}' 创建 Refresh Token，过期时间: {expire.isoformat()}")
    return token


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    """验证用户名和密码，成功则返回 User 对象，失败返回 None。

    先按用户名查库，找不到用户直接返回 None；
    找到用户后调用 verify_password 比对密码。

    Args:
        db: SQLAlchemy 数据库会话。
        username: 登录用户名。
        password: 登录明文密码。

    Returns:
        认证成功返回 User ORM 实例，失败返回 None。
    """
    user = db.query(User).filter(User.username == username).first()
    if not user:
        logger.info(f"登录失败: 用户 '{username}' 不存在")
        return None
    if not verify_password(password, user.password_hash):
        logger.info(f"登录失败: 用户 '{username}' 密码错误")
        return None
    logger.info(f"用户 '{username}' 认证成功")
    return user


# ══════════════════════════════════════════════════════════════════════
# FastAPI 依赖注入：获取当前用户 / 权限校验
# ══════════════════════════════════════════════════════════════════════


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI 依赖注入: 从请求的 Authorization 头中提取 JWT 并解析当前用户。

    流程:
      1. 从 Authorization: Bearer <token> 头中提取 token。
      2. 使用 JWT_SECRET_KEY 解码，提取 payload 中的 sub（用户名）。
      3. 根据用户名查询数据库，返回完整的 User 对象。
      4. token 无效、过期、或用户不存在时，抛出 401 Unauthorized。

    Args:
        token: FastAPI 自动从请求头提取的 Bearer Token。
        db: FastAPI 依赖注入的数据库会话。

    Returns:
        当前登录用户的 User ORM 实例。

    Raises:
        HTTPException(401): token 无效、过期或用户不存在。
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效或过期的认证令牌",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # ── 解码 JWT ──
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        username: str | None = payload.get("sub")
        if not username:
            logger.warning("JWT 有效但缺少 'sub' 字段")
            raise credentials_exception
    except JWTError:
        logger.warning("JWT 解码失败或已过期")
        raise credentials_exception

    # ── 查询数据库中的用户 ──
    user = db.query(User).filter(User.username == username).first()
    if not user:
        logger.warning(f"JWT 中的用户 '{username}' 在数据库中不存在")
        raise credentials_exception

    logger.debug(f"当前用户: '{user.username}' (角色: {user.role})")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """FastAPI 依赖注入: 要求当前用户具有 admin 角色。

    必须在 get_current_user 之后使用（通过 Depends 链自动解析）。

    用法示例:
        @router.delete("/admin/only")
        def admin_endpoint(admin: User = Depends(require_admin)):
            ...

    Args:
        current_user: 由 get_current_user 依赖注入解析的当前用户。

    Returns:
        当前管理员用户（已验证角色为 "admin"）。

    Raises:
        HTTPException(403): 当前用户角色不是 "admin"。
    """
    if current_user.role != "admin":
        logger.warning(
            f"权限拒绝: 用户 '{current_user.username}' (角色: {current_user.role}) 尝试访问管理接口"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理员权限不足",
        )
    return current_user


# ══════════════════════════════════════════════════════════════════════
# 角色解析
# ══════════════════════════════════════════════════════════════════════


def resolve_role(requested_role: str | None, admin_code: str | None) -> str:
    """解析注册/邀请时请求的角色。

    规则:
      - 未指定角色或指定非 "admin" 角色 → 返回 "user"。
      - 指定 "admin" 角色时:
          * 如果系统配置了 ADMIN_INVITE_CODE，且用户提交的 admin_code 匹配 → 返回 "admin"。
          * 否则抛出 403 Forbidden（管理员邀请码错误）。

    Args:
        requested_role: 用户请求的角色名称（可为 None，默认为 "user"）。
        admin_code: 用户提交的管理员邀请码（可为 None）。

    Returns:
        "user" 或 "admin"。

    Raises:
        HTTPException(403): 请求管理员角色但邀请码不匹配。
    """
    role = (requested_role or "user").strip().lower()
    if role != "admin":
        return "user"

    # 请求管理员角色 → 验证邀请码
    if ADMIN_INVITE_CODE and admin_code == ADMIN_INVITE_CODE:
        logger.info("管理员邀请码验证通过，分配 admin 角色")
        return "admin"

    logger.warning(f"管理员邀请码验证失败: 收到 '{admin_code}'")
    raise HTTPException(status_code=403, detail="管理员邀请码错误")
